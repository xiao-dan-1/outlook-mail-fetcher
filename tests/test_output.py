import unittest

from mail_receiver.output import visible_text


class VisibleTextTests(unittest.TestCase):
    def test_visible_text_escapes_control_and_non_printable_characters(self) -> None:
        cases = {
            "plain text 中文": "plain text 中文",
            "carriage\rreturn\nline\ttab\bback\fform\vvertical": (
                "carriage\\rreturn\\nline\\ttab\\bback\\fform\\vvertical"
            ),
            "nul\x00 esc\x1b del\x7f c1\x85": (
                "nul\\x00 esc\\x1b del\\x7f c1\\x85"
            ),
            "zero-width\u200b separators\u2028\u2029": (
                "zero-width\\u200b separators\\u2028\\u2029"
            ),
            "language-tag\U000e0001": "language-tag\\U000e0001",
        }

        for value, expected in cases.items():
            with self.subTest(value=ascii(value)):
                self.assertEqual(visible_text(value), expected)

    def test_visible_text_does_not_normalize_unicode_or_escape_printable_backslashes(self) -> None:
        decomposed = "e\u0301\\n中文"

        result = visible_text(decomposed)

        self.assertEqual(result, decomposed)
        self.assertNotEqual(result, "é\\n中文")


if __name__ == "__main__":
    unittest.main()
