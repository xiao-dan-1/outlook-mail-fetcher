from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


ACCOUNT_SEPARATOR = "----"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountFormatError(ValueError):
    """Raised when an account line cannot be parsed."""


@dataclass(frozen=True)
class Account:
    email: str
    password: str
    client_id: str
    refresh_token: str
    source_line: int

    @property
    def masked_password(self) -> str:
        return mask_secret(self.password)

    @property
    def masked_refresh_token(self) -> str:
        return mask_secret(self.refresh_token, keep_start=8, keep_end=6)


def mask_secret(value: str, keep_start: int = 2, keep_end: int = 2) -> str:
    if not value:
        return ""
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return f"{value[:keep_start]}{'*' * 8}{value[-keep_end:]}"


def parse_account_line(line: str, line_number: int) -> Account:
    raw = line.strip()
    if not raw:
        raise AccountFormatError(f"line {line_number}: empty account line")

    parts = raw.split(ACCOUNT_SEPARATOR)
    if len(parts) != 4:
        raise AccountFormatError(
            f"line {line_number}: expected 4 fields separated by {ACCOUNT_SEPARATOR!r}, got {len(parts)}"
        )

    email, password, client_id, refresh_token = [part.strip() for part in parts]
    if not EMAIL_RE.match(email):
        raise AccountFormatError(f"line {line_number}: invalid email address {email!r}")
    if not password:
        raise AccountFormatError(f"line {line_number}: password is empty")
    if not client_id:
        raise AccountFormatError(f"line {line_number}: client_id is empty")
    if not refresh_token:
        raise AccountFormatError(f"line {line_number}: refresh_token is empty")

    return Account(
        email=email,
        password=password,
        client_id=client_id,
        refresh_token=refresh_token,
        source_line=line_number,
    )


def parse_accounts(lines: Iterable[str]) -> list[Account]:
    accounts: list[Account] = []
    errors: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            accounts.append(parse_account_line(line, line_number))
        except AccountFormatError as exc:
            errors.append(str(exc))

    if errors:
        raise AccountFormatError("; ".join(errors))
    return accounts


def filter_accounts_by_email(
    accounts: Iterable[Account],
    selected_email: str,
) -> list[Account]:
    normalized_email = selected_email.lower()
    return [
        account
        for account in accounts
        if account.email.lower() == normalized_email
    ]


def load_accounts(path: str | Path) -> list[Account]:
    account_path = Path(path)
    with account_path.open("r", encoding="utf-8-sig") as handle:
        return parse_accounts(handle)
