import type { ReactNode } from "react";
import { Logo } from "./Brand";
import { IconLogout } from "./Icons";

export type NavItem = { href: string; label: string; icon: ReactNode; current?: boolean };

/** Sidebar + main area, used by the member profile page and the admin pages. */
export function Shell({
  staff = false,
  nav,
  box,
  onSignOut,
  children,
}: {
  staff?: boolean;
  nav: NavItem[];
  box: ReactNode;
  onSignOut: () => void;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <Logo staff={staff} href={staff ? "/admin" : "/profile"} />
        <nav className="nav" aria-label="Main">
          {nav.map((n) => (
            <a key={n.href} href={n.href} aria-current={n.current ? "page" : undefined}>
              {n.icon}
              {n.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="side-box">{box}</div>
          <button type="button" className="nav-btn" onClick={onSignOut}>
            <IconLogout size={18} />
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

export function Initials({ name, large = false }: { name: string; large?: boolean }) {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return <span className={`avatar${large ? " lg" : ""}`}>{letters || "?"}</span>;
}
