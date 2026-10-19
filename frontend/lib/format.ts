export function greeting(date = new Date()): string {
  const h = date.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export const dateShort = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export const dateTime = (iso: string) => {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${day}, ${time}`;
};

/** "25-34" -> "25–34" (typographic en dash, as in the design) */
export const ageLabel = (range: string | null) => (range ? range.replace("-", "–") : "—");

export const contactLabel = (c: string) => ({ email: "Email", phone: "Phone", sms: "SMS" }[c] ?? c);
