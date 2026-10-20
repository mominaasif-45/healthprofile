import type { ReactNode } from "react";
import { IconClock, IconUsers } from "./Icons";
import type { NavItem } from "./Shell";

export const adminNav = (current: "profiles" | "audit"): NavItem[] => [
  { href: "/admin", label: "Member profiles", icon: <IconUsers />, current: current === "profiles" },
  { href: "/admin/audit", label: "Audit log", icon: <IconClock />, current: current === "audit" },
];

export function AdminBox({ email }: { email?: string }): ReactNode {
  return (
    <>
      <strong>
        <span className="dot" />
        Session active
      </strong>
      Signed in as {email ?? "…"}. Ends after 30 min idle.
    </>
  );
}
