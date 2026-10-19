"use client";

import { useEffect, useState } from "react";
import { IconMoon, IconSun } from "./Icons";

type Theme = "light" | "dark";
const KEY = "hp_theme";

/** Runs before first paint (see layout.tsx) so there is no flash of the wrong theme. */
export const themeInitScript = `
try {
  var t = localStorage.getItem("${KEY}");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
`;

function currentTheme(): Theme {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle({ label = false }: { label?: boolean }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  // The real theme is only known in the browser (system setting / saved choice), so read it after mount.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setTheme(currentTheme()), []);

  function toggle() {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {}
    setTheme(next);
  }

  const goingTo = theme === "dark" ? "Light mode" : "Dark mode";
  return (
    <button type="button" className="btn btn-sm" onClick={toggle} aria-label={`Switch to ${goingTo.toLowerCase()}`}>
      {theme === "dark" ? <IconSun size={16} /> : <IconMoon size={16} />}
      {label && <span>{goingTo}</span>}
    </button>
  );
}
