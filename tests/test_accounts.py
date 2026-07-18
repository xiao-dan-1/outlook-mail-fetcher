import unittest

from mail_receiver.accounts import (
    Account,
    AccountFormatError,
    filter_accounts_by_email,
    mask_secret,
    parse_accounts,
)


class AccountParsingTests(unittest.TestCase):
    def test_filter_accounts_by_email_is_case_insensitive_and_preserves_order(self) -> None:
        accounts = [
            Account("other@outlook.com", "p1", "c1", "r1", 1),
            Account("Target@outlook.com", "p2", "c2", "r2", 2),
            Account("target@OUTLOOK.com", "p3", "c3", "r3", 3),
        ]

        matches = filter_accounts_by_email(accounts, "TARGET@outlook.com")

        self.assertEqual(matches, [accounts[1], accounts[2]])
        self.assertEqual(filter_accounts_by_email(accounts, "missing@outlook.com"), [])

    def test_parse_four_field_order_line(self) -> None:
        accounts = parse_accounts(
            [
                "user@outlook.com----secret----client-id----refresh-token\n",
                "\n",
            ]
        )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].email, "user@outlook.com")
        self.assertEqual(accounts[0].password, "secret")
        self.assertEqual(accounts[0].client_id, "client-id")
        self.assertEqual(accounts[0].refresh_token, "refresh-token")

    def test_reject_invalid_field_count(self) -> None:
        with self.assertRaises(AccountFormatError):
            parse_accounts(["user@outlook.com----secret----client-id\n"])

    def test_mask_secret_keeps_edges(self) -> None:
        self.assertEqual(mask_secret("abcdef", keep_start=1, keep_end=2), "a********ef")


if __name__ == "__main__":
    unittest.main()
