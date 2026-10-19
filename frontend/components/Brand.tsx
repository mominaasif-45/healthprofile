import Link from "next/link";
import type { ReactNode } from "react";
import { IconCheck, IconPulse } from "./Icons";
import { ThemeToggle } from "./Theme";

export function Logo({ staff = false, href = "/" }: { staff?: boolean; href?: string }) {
  return (
    <Link href={href} className="logo">
      <span className="logo-mark">
        <IconPulse size={20} />
      </span>
      <span>
        HealthProfile
        {staff && <small>STAFF PORTAL</small>}
      </span>
    </Link>
  );
}

/** Split-screen layout shared by signup, login and admin login. */
export function AuthShell({
  staff = false,
  title,
  lead,
  points,
  children,
}: {
  staff?: boolean;
  title: ReactNode;
  lead: string;
  points: string[];
  children: ReactNode;
}) {
  return (
    <div className="auth">
      <aside className={`auth-side${staff ? " staff" : ""}`}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Logo href={staff ? "/admin/login" : "/login"} />
          {staff && <span className="pill">Staff portal</span>}
        </div>
        <div>
          <h1>{title}</h1>
          <p>{lead}</p>
          <ul className="ticks">
            {points.map((p) => (
              <li key={p}>
                <span className="tick">
                  <IconCheck size={14} />
                </span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <p className="auth-note">Demo environment. All profiles are synthetic.</p>
      </aside>
      <main className="auth-main">
        <div className="auth-theme">
          <ThemeToggle />
        </div>
        {children}
      </main>
    </div>
  );
}
