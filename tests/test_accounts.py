import unittest

from mail_receiver.accounts import AccountFormatError, mask_secret, parse_accounts


class AccountParsingTests(unittest.TestCase):
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
