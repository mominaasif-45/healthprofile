"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthShell } from "@/components/Brand";
import { ApiError, errorMessage, userLogin } from "@/lib/api";

export default function LoginPage() {
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
      await userLogin(email, password);
      router.push("/profile");
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
      title={
        <>
          Welcome back to
          <br />
          your calm place.
        </>
      }
      lead="Sign in to review your goals, contact preferences and emergency contact."
      points={[
        "Only you can view and edit your profile",
        "Your session lives in a secure HttpOnly cookie",
        "Wellness goals only, never diagnoses",
      ]}
    >
      <form className="auth-card" onSubmit={onSubmit} noValidate>
        <h2>Sign in</h2>
        <p className="sub">Use the email and password you registered with.</p>
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
            autoComplete="email"
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
        <button className="btn btn-primary btn-block" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="auth-switch">
          New here? <Link href="/signup">Create an account</Link>
        </p>
        <p className="auth-switch" style={{ marginTop: 6 }}>
          Staff? <Link href="/admin/login">Admin sign in</Link>
        </p>
      </form>
    </AuthShell>
  );
}
