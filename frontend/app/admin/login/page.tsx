"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthShell } from "@/components/Brand";
import { IconClock } from "@/components/Icons";
import { ApiError, adminLogin, errorMessage } from "@/lib/api";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await adminLogin(email, password);
      router.push("/admin");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many attempts. Please wait a minute and try again."
          : errorMessage(err)
      );
      setBusy(false);
    }
  }

  return (
    <AuthShell
      staff
      title={
        <>
          Admin access,
          <br />
          kept separate.
        </>
      }
      lead="Admin accounts are created by the system administrator. There is no public sign-up."
      points={[
        "Server-side session with secure cookie",
        "CSRF protection on every change",
        "Search and review member profiles",
      ]}
    >
      <form className="auth-card" onSubmit={onSubmit} noValidate>
        <h2>Admin sign in</h2>
        <p className="sub">Use the credentials provided to you.</p>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <div className="field">
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            className="input"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="input"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <div className="info-box">
          <IconClock size={14} />
          Your session ends after 30 minutes without activity.
        </div>
        <button className="btn btn-primary btn-block" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in to admin"}
        </button>
        <p className="auth-switch">
          Not an admin? <Link href="/login">Go to member sign in</Link>
        </p>
      </form>
    </AuthShell>
  );
}
