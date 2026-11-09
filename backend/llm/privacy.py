"""
Personal details are refused, not stripped, before anything reaches the model.

Why refuse instead of strip: quietly deleting part of a question changes what the member asked, and what is left
can still identify someone. A clear 400 tells the member what to remove. Nothing is sent to the model, and the error
never repeats the detail.

What counts as a personal detail here:
* an email address;
* a run of 7 or more digits, even split by spaces, dashes, dots or brackets (phone, CNIC or other ID numbers, and
  dates written with digits, such as a date of birth);
* the member's own name (each part of 3+ letters, from the account and the profile) or the account email.

Limits: a name the server does not know (someone else's) cannot be detected; and a member whose name is also an
ordinary word may see a false refusal. The endpoint itself never reads profile data into the prompt.
"""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DIGIT_RUN = re.compile(r"\+?\d[\d\s().\-/]*\d")
MIN_DIGITS = 7
MIN_NAME_PART = 3

MESSAGE = ("Please remove personal details (names, email addresses, phone or ID numbers, dates of birth) before "
           "asking. They are never sent to the assistant.")


def _known_names(user):
    names = [getattr(user, "name", "") or ""]
    profile = getattr(user, "health_profile", None) if user is not None else None
    demographics = getattr(profile, "demographics", None) if profile is not None else None
    if demographics is not None:
        names.append(demographics.full_name or "")
    parts = set()
    for name in names:
        parts.update(part.lower() for part in re.findall(r"[^\W\d_]+", name) if len(part) >= MIN_NAME_PART)
    return parts


def contains_personal_details(text, user=None):
    if EMAIL.search(text):
        return True
    if any(sum(ch.isdigit() for ch in match.group()) >= MIN_DIGITS for match in DIGIT_RUN.finditer(text)):
        return True
    if user is None:
        return False
    lowered = text.lower()
    email = (getattr(user, "email", "") or "").lower()
    if email and email in lowered:
        return True
    words = set(re.findall(r"[^\W\d_]+", lowered))
    return bool(words & _known_names(user))
