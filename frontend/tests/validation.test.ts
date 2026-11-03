import { describe, expect, it } from "vitest";
import { validateContact } from "@/lib/validation";

// The browser check uses the same phone rule as the server (backend/profiles/phones.py):
// an optional leading "+", then digits, spaces, brackets and dashes, with 7 to 15 digits in total.
const MESSAGE = "Enter a valid phone number with 7 to 15 digits, e.g. +92 300 0000000.";
const phoneError = (phone: string) => validateContact({ name: "Bilal Ahmed", relationship: "friend", phone }).phone;

describe("validateContact phone rule (same as the server)", () => {
  it.each([
    ["1------", "1 digit hidden behind punctuation"],
    ["((((1))))", "1 digit in brackets"],
    ["+92 300+1234567", "a + that is not at the start"],
    ["+92 300 CALL ME", "letters"],
    ["123456", "6 digits: one too few"],
    ["1234567890123456", "16 digits: one too many"],
  ])("rejects %s (%s)", (phone) => {
    expect(phoneError(phone)).toBe(MESSAGE);
  });

  it.each([
    ["1234567", "7 digits: the minimum"],
    ["+123 456 789 012 345", "15 digits: the maximum"],
    ["+92 (300) 123-4567", "brackets, spaces and dashes"],
    ["  +92-300-1234567  ", "surrounding spaces"],
  ])("accepts %s (%s)", (phone) => {
    expect(phoneError(phone)).toBeUndefined();
  });
});
