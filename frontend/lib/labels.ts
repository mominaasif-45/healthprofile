// Human-readable labels for the codes the API uses, plus the option lists for the forms.

export const AGE_RANGES = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"];

export const GENDERS = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "non_binary", label: "Non-binary" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];

export const RELATIONSHIPS = [
  { value: "parent", label: "Parent" },
  { value: "sibling", label: "Sibling" },
  { value: "partner", label: "Partner" },
  { value: "friend", label: "Friend" },
  { value: "other", label: "Other" },
];

export const CONTACT_PREFERENCES: { value: "email" | "phone" | "sms"; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "sms", label: "SMS" },
];

export const ACTIVITY_LEVELS = [
  { value: "sedentary", label: "Sedentary" },
  { value: "light", label: "Light" },
  { value: "moderate", label: "Moderate" },
  { value: "active", label: "Active" },
];

export const DIETS = [
  { value: "no_preference", label: "No preference" },
  { value: "vegetarian", label: "Vegetarian" },
  { value: "vegan", label: "Vegan" },
  { value: "halal", label: "Halal" },
  { value: "other", label: "Other" },
];

export const GOALS = [
  { value: "better_sleep", label: "Better sleep" },
  { value: "more_activity", label: "More activity" },
  { value: "stress_management", label: "Stress management" },
  { value: "healthy_eating", label: "Healthy eating" },
  { value: "hydration", label: "Hydration" },
  { value: "weight_management", label: "Weight management" },
];

export const COMPLETION_LABELS: Record<string, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
};

export const ACTION_LABELS: Record<string, string> = {
  "profile.created": "Profile created",
  "profile.updated": "Profile updated",
  "profile.deleted": "Profile deleted",
  "demographics.updated": "Demographics saved",
  "wellness.updated": "Wellness saved",
  "goals.updated": "Goals saved",
  "emergency_contact.created": "Emergency contact added",
  "emergency_contact.updated": "Emergency contact changed",
  "emergency_contact.deleted": "Emergency contact removed",
  "admin.login": "Admin signed in",
  "admin.login_failed": "Admin sign-in failed",
  "admin.logout": "Admin signed out",
  "admin.profile_viewed": "Profile viewed by admin",
  "admin.profile_deactivated": "Profile deactivated",
  "admin.profile_reactivated": "Profile reactivated",
};

export const labelOf = (list: { value: string; label: string }[], value: string | null | undefined) =>
  list.find((o) => o.value === value)?.label ?? (value || "—");

export const actionLabel = (action: string) => ACTION_LABELS[action] ?? action;
