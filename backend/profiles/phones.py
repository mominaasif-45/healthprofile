"""
One canonical form for (fictional) phone numbers: an optional leading "+" followed by digits only.

    "+92 (300) 123-4567"  ->  "+923001234567"

The serializer and the services both call normalize_phone(), so validation, storage and the
duplicate check all compare the same thing. The database enforces the same shape with the
CHECK constraint contact_phone_is_canonical (see EmergencyContact.Meta).

Limitation: there are no country rules (that would need a new dependency), so "0300 1234567"
and "+92 300 1234567" stay different numbers, and so do "+92..." and "92...".
"""
import re

MIN_DIGITS = 7   # a short local number
MAX_DIGITS = 15  # the international maximum (ITU E.164)

# What a person may type: an optional "+" at the start, then digits, spaces, brackets and dashes.
ALLOWED_INPUT = re.compile(r"^\+?[0-9 ()\-]+$")
CANONICAL = rf"^\+?[0-9]{{{MIN_DIGITS},{MAX_DIGITS}}}$"

INVALID_MESSAGE = f"Enter a valid phone number with {MIN_DIGITS} to {MAX_DIGITS} digits, e.g. +92 300 0000000."


def normalize_phone(value):
    """Return the canonical form of value, or raise ValueError if it is not a valid phone number."""
    value = (value or "").strip()
    if not ALLOWED_INPUT.match(value):
        raise ValueError(INVALID_MESSAGE)
    digits = re.sub(r"\D", "", value)
    if not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        raise ValueError(INVALID_MESSAGE)
    return ("+" if value.startswith("+") else "") + digits
