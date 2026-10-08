"""Arabic-aware text normalization, used for product matching and number parsing."""

import re
from decimal import Decimal, InvalidOperation

# Arabic-Indic and Eastern Arabic-Indic digits.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Letter variants people type interchangeably: alef forms, taa marbuta, alef maqsura, and the
# yaa and kaf variants some keyboards produce.
_LETTERS = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ی": "ي", "ک": "ك", "ۀ": "ه"}
)
# Arabic diacritics, tatweel, and invisible joiners.
_STRIP = re.compile("[ً-ٰٟـ‌‍‎‏]")
_SPACES = re.compile(r"\s+")
# Arabic thousands and decimal separators.
_SEPARATORS = str.maketrans({"٬": ",", "٫": "."})


def to_ascii_digits(text: str) -> str:
    return text.translate(_DIGITS)


def normalize(text: str) -> str:
    """Canonical form for comparisons: unified letters, ASCII digits, lowercase, one space."""
    text = to_ascii_digits(text).translate(_LETTERS)
    text = _STRIP.sub(" ", text)
    return _SPACES.sub(" ", text).strip().lower()


def parse_decimal(value: object) -> Decimal | None:
    """Parse "$1,250.50", "١٢٥٠", "49,99 AED", 3.0 or "12" into a Decimal; None without digits.

    A comma is a thousands separator when three digits follow it ("1,250"), otherwise a
    decimal comma ("49,99").
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = re.sub(r"[^\d.,]", "", to_ascii_digits(str(value)).translate(_SEPARATORS))
    if "." in text:
        text = text.replace(",", "")
    elif "," in text:
        whole, _, last = text.rpartition(",")
        text = text.replace(",", "") if len(last) == 3 else f"{whole.replace(',', '')}.{last}"
    text = text.strip(".")
    if not text or text.count(".") > 1:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_int(value: object) -> int | None:
    """Parse "1,250", "١٢٥٠", 3.0 or "12" into an int; None if there are no digits."""
    number = parse_decimal(value)
    return int(number) if number is not None else None
