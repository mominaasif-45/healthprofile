// Client-side checks that mirror the backend rules, so people get instant feedback.
// The server still validates everything again: this is only for convenience.

export type Errors = Record<string, string>;

// Same phone rule as the server (backend/profiles/phones.py): an optional leading "+", then digits,
// spaces, brackets and dashes, with 7 to 15 digits in total. "1------" (1 digit) is not a number.
const PHONE_ALLOWED = /^\+?[0-9 ()\-]+$/;
const PHONE_MIN_DIGITS = 7;
const PHONE_MAX_DIGITS = 15;
const PHONE_MESSAGE = `Enter a valid phone number with ${PHONE_MIN_DIGITS} to ${PHONE_MAX_DIGITS} digits, e.g. +92 300 0000000.`;
const MAX_AGE_YEARS = 120;

export const todayISO = () => new Date().toISOString().slice(0, 10);

function isValidPhone(value: string) {
  const digits = value.replace(/\D/g, "").length;
  return PHONE_ALLOWED.test(value) && digits >= PHONE_MIN_DIGITS && digits <= PHONE_MAX_DIGITS;
}

export function validateDemographics(f: {
  full_name: string;
  date_of_birth: string;
  age_range: string;
  preferred_name: string;
  city: string;
}): Errors {
  const e: Errors = {};
  if (f.full_name.trim().length < 2) e.full_name = "Full name must be at least 2 characters.";
  if (f.full_name.length > 120) e.full_name = "Full name can be at most 120 characters.";
  if (f.preferred_name.length > 60) e.preferred_name = "Preferred name can be at most 60 characters.";
  if (f.city.length > 80) e.city = "City can be at most 80 characters.";
  if (!f.date_of_birth && !f.age_range) e.age_range = "Choose an age range or enter a date of birth.";
  if (f.date_of_birth) {
    const dob = new Date(f.date_of_birth);
    const oldest = new Date();
    oldest.setFullYear(oldest.getFullYear() - MAX_AGE_YEARS);
    if (f.date_of_birth > todayISO()) e.date_of_birth = "Date of birth cannot be in the future.";
    else if (dob < oldest) e.date_of_birth = `Date of birth cannot be more than ${MAX_AGE_YEARS} years ago.`;
  }
  return e;
}

export function validateContact(f: { name: string; relationship: string; phone: string }): Errors {
  const e: Errors = {};
  if (f.name.trim().length < 2) e.name = "Name must be at least 2 characters.";
  if (!f.relationship) e.relationship = "Choose a relationship.";
  if (!isValidPhone(f.phone.trim())) e.phone = PHONE_MESSAGE;
  return e;
}

export function validateWellness(f: {
  contact_preference: string;
  sleep_goal_hours: string;
  allergies: string;
  lifestyle_notes: string;
}): Errors {
  const e: Errors = {};
  if (!f.contact_preference) e.contact_preference = "Choose how we should contact you.";
  if (f.sleep_goal_hours !== "") {
    const n = Number(f.sleep_goal_hours);
    if (!Number.isInteger(n) || n < 4 || n > 12) e.sleep_goal_hours = "Sleep goal must be a whole number from 4 to 12.";
  }
  if (f.allergies.length > 500) e.allergies = "Allergies can be at most 500 characters.";
  if (f.lifestyle_notes.length > 500) e.lifestyle_notes = "Notes can be at most 500 characters.";
  return e;
}
