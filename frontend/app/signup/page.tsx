"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthShell } from "@/components/Brand";
import { ApiError, errorMessage, fieldError, userLogin, userSignup } from "@/lib/api";

function passwordScore(pw: string) {
  let score = 0;
  if (pw.length >= 10) score++;
  if (/[a-zA-Z]/.test(pw) && /\d/.test(pw)) score++;
  if (pw.length >= 12) score++;
  if (/[^a-zA-Z0-9]/.test(pw) || pw.length >= 16) score++;
  return score;
}

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const score = passwordScore(password);
  const strengthText =
    password.length === 0
      ? "Use 10+ characters with a mix of letters and numbers."
      : score >= 3
        ? "Strong. Nice choice."
        : score === 2
          ? "Good. Use 10+ characters with a mix of letters and numbers."
          : "Too weak. Use 10+ characters with a mix of letters and numbers.";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await userSignup(name, email, password);
      await userLogin(email, password);
      router.push("/profile");
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const general =
    error && !(error instanceof ApiError && Object.keys(error.fields).length > 0) ? errorMessage(error) : null;

  return (
    <AuthShell
      title={
        <>
          Your wellness profile,
          <br />
          in one calm place.
        </>
      }
      lead="Set your goals, contact preferences and emergency contact. You stay in control of your profile."
      points={[
        "Only you can view and edit your profile",
        "Passwords are securely hashed",
        "Wellness goals only, never diagnoses",
      ]}
    >
      <form className="auth-card" onSubmit={onSubmit} noValidate>
        <h2>Create your account</h2>
        <p className="sub">It takes less than a minute.</p>
        {general && (
          <div className="form-error" role="alert">
            {general}
          </div>
        )}

        <div className="field">
          <label className="label" htmlFor="name">
            Full name
          </label>
          <input
            id="name"
            className="input"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={!!fieldError(error, "name")}
            required
          />
          {fieldError(error, "name") && <span className="error-text">{fieldError(error, "name")}</span>}
        </div>

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
            aria-invalid={!!fieldError(error, "email") || (error instanceof ApiError && error.status === 409)}
            required
          />
          {fieldError(error, "email") && <span className="error-text">{fieldError(error, "email")}</span>}
          {error instanceof ApiError && error.status === 409 && (
            <span className="error-text">
              {error.message} <Link href="/login">Sign in instead</Link>
            </span>
          )}
        </div>

        <div className="field">
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="input"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!fieldError(error, "password")}
            aria-describedby="pw-hint"
            required
          />
          <div className="strength" aria-hidden="true">
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={i <= score ? "on" : ""} />
            ))}
          </div>
          <span id="pw-hint" className="hint">
            {strengthText}
          </span>
          {error instanceof ApiError &&
            error.fields.password?.map((m) => (
              <span key={m} className="error-text">
                {m}
              </span>
            ))}
        </div>

        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </button>
        <p className="auth-switch">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </form>
    </AuthShell>
  );
}
