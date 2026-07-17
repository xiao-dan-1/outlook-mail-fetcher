from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .accounts import AccountFormatError, load_accounts
from .imap_client import (
    DEFAULT_IMAP_HOST,
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_TIMEOUT,
    fetch_messages,
    mock_messages,
)
from .oauth import DEFAULT_SCOPE, TOKEN_ENDPOINT
from .storage import DEFAULT_DB_PATH, MailStore


def _add_common_options(
    parser: argparse.ArgumentParser,
    *,
    suppress_defaults: bool = False,
) -> None:
    db_default = argparse.SUPPRESS if suppress_defaults else str(DEFAULT_DB_PATH)
    parser.add_argument("--db", default=db_default, help="SQLite database path.")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS if suppress_defaults else False,
        help="Enable verbose debug logging.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Receive Outlook mail into a local searchable store.")
    parser.add_argument("--version", action="version", version=f"Outlook Mail Fetcher {__version__}")
    _add_common_options(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-accounts", help="Parse and validate account file.")
    _add_common_options(inspect_parser, suppress_defaults=True)
    inspect_parser.add_argument("account_file", help="Account file path.")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch mail into local SQLite store.")
    _add_common_options(fetch_parser, suppress_defaults=True)
    fetch_parser.add_argument("account_file", help="Account file path.")
    fetch_parser.add_argument("--mailbox", default="INBOX", help="Mailbox name.")
    fetch_parser.add_argument("--limit", type=int, default=20, help="Messages per account.")
    fetch_parser.add_argument("--account", help="Only fetch one account email.")
    fetch_parser.add_argument("--mock", action="store_true", help="Use local mock messages.")
    fetch_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when one account fails.",
    )
    fetch_parser.add_argument("--imap-host", default=DEFAULT_IMAP_HOST, help="IMAP server host.")
    fetch_parser.add_argument("--imap-port", type=int, default=DEFAULT_IMAP_PORT, help="IMAP SSL port.")
    fetch_parser.add_argument("--imap-timeout", type=int, default=DEFAULT_IMAP_TIMEOUT, help="IMAP timeout seconds.")
    fetch_parser.add_argument("--token-endpoint", default=TOKEN_ENDPOINT, help="OAuth2 token endpoint.")
    fetch_parser.add_argument("--scope", default=DEFAULT_SCOPE, help="OAuth2 refresh scope.")
    fetch_parser.add_argument("--token-timeout", type=int, default=30, help="OAuth2 timeout seconds.")

    search_parser = subparsers.add_parser("search", help="Search local stored mail.")
    _add_common_options(search_parser, suppress_defaults=True)
    search_parser.add_argument("--query", "-q", required=True, help="Keyword to search.")
    search_parser.add_argument("--account", help="Only search one account.")
    search_parser.add_argument("--limit", type=int, default=20, help="Maximum result count.")

    show_parser = subparsers.add_parser("show", help="Show one stored mail by id.")
    _add_common_options(show_parser, suppress_defaults=True)
    show_parser.add_argument("email_id", type=int, help="Stored email id.")
    show_parser.add_argument("--raw", action="store_true", help="Print raw RFC822 message.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.command == "inspect-accounts":
            return inspect_accounts(args.account_file)
        if args.command == "fetch":
            return fetch(args)
        if args.command == "search":
            return search(args)
        if args.command == "show":
            return show(args)
    except AccountFormatError as exc:
        print(f"account format error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if args.debug:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error("unknown command")
    return 2


def inspect_accounts(account_file: str) -> int:
    accounts = load_accounts(account_file)
    print(f"accounts: {len(accounts)}")
    for account in accounts:
        print(
            f"line={account.source_line} email={account.email} "
            f"password={account.masked_password} client_id={account.client_id} "
            f"refresh_token={account.masked_refresh_token}"
        )
    return 0


def fetch(args: argparse.Namespace) -> int:
    accounts = load_accounts(args.account_file)
    if args.account:
        accounts = [account for account in accounts if account.email.lower() == args.account.lower()]
        if not accounts:
            print(f"account not found: {args.account}", file=sys.stderr)
            return 1

    store = MailStore(args.db)
    store.initialize()

    total_seen = 0
    total_inserted = 0
    failures: list[tuple[str, str]] = []
    for account in accounts:
        logging.info("fetching %s mailbox=%s limit=%s", account.email, args.mailbox, args.limit)
        try:
            records = (
                mock_messages(account, mailbox=args.mailbox, limit=args.limit)
                if args.mock
                else fetch_messages(
                    account,
                    mailbox=args.mailbox,
                    limit=args.limit,
                    host=args.imap_host,
                    port=args.imap_port,
                    imap_timeout=args.imap_timeout,
                    token_endpoint=args.token_endpoint,
                    scope=args.scope,
                    token_timeout=args.token_timeout,
                    debug=args.debug,
                )
            )
            inserted = store.save_many(records)
            total_seen += len(records)
            total_inserted += inserted
            print(f"{account.email}: fetched={len(records)} inserted={inserted}")
        except Exception as exc:
            message = str(exc)
            failures.append((account.email, message))
            print(f"{account.email}: failed={message}", file=sys.stderr)
            if args.stop_on_error:
                raise

    print(
        f"done: accounts={len(accounts)} fetched={total_seen} inserted={total_inserted} "
        f"failed={len(failures)} db={store.path}"
    )
    if failures:
        print("failures:", file=sys.stderr)
        for email, message in failures:
            print(f"- {email}: {message}", file=sys.stderr)
        return 1
    return 0


def search(args: argparse.Namespace) -> int:
    store = MailStore(args.db)
    store.initialize()
    results = store.search(args.query, account_email=args.account, limit=args.limit)
    print(f"results: {len(results)}")
    for email in results:
        print(
            f"[{email.id}] {email.sent_at or '-'} {email.account_email} "
            f"from={email.sender} subject={email.subject}"
        )
    return 0


def show(args: argparse.Namespace) -> int:
    store = MailStore(args.db)
    store.initialize()

    if args.raw:
        raw = store.get_raw_message(args.email_id)
        if raw is None:
            print(f"email not found: {args.email_id}", file=sys.stderr)
            return 1
        print(raw.decode("utf-8", errors="replace"))
        return 0

    email = store.get(args.email_id)
    if email is None:
        print(f"email not found: {args.email_id}", file=sys.stderr)
        return 1
    print(f"id: {email.id}")
    print(f"account: {email.account_email}")
    print(f"mailbox: {email.mailbox}")
    print(f"uid: {email.uid}")
    print(f"message_id: {email.message_id or '-'}")
    print(f"sent_at: {email.sent_at or '-'}")
    print(f"from: {email.sender}")
    print(f"to: {email.recipients}")
    print(f"subject: {email.subject}")
    print("")
    print(email.body_preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
