from __future__ import annotations


_SHORT_ESCAPES = {
    "\r": "\\r",
    "\n": "\\n",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
    "\v": "\\v",
}


def visible_text(value: object) -> str:
    """Return text with terminal-significant control characters made visible."""
    result: list[str] = []
    for character in str(value):
        short_escape = _SHORT_ESCAPES.get(character)
        if short_escape is not None:
            result.append(short_escape)
            continue
        if character.isprintable() and character not in {"\u2028", "\u2029"}:
            result.append(character)
            continue

        codepoint = ord(character)
        if codepoint <= 0xFF:
            result.append(f"\\x{codepoint:02x}")
        elif codepoint <= 0xFFFF:
            result.append(f"\\u{codepoint:04x}")
        else:
            result.append(f"\\U{codepoint:08x}")
    return "".join(result)
