"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import {
  FAQ_PROMPT_VERSION, QUESTION_MAX, QUESTION_MIN, checkPolicyFile, faqErrorMessage, uploadErrorMessage, uploadPolicy,
  type FaqAnswer, type UploadResult,
} from "@/lib/ml";
import { Disclaimer } from "./Charts";

const STATUS_TEXT: Record<FaqAnswer["status"], string> = {
  answered: "Answered from the policies",
  insufficient_information: "Not in the policies (insufficient information)",
  out_of_scope: "Out of scope",
};

export function FaqTab({ member, admin }: { member: boolean; admin: boolean }) {
  return (
    <div>
      <Disclaimer>
        <strong>Synthetic data only. Educational demo: not medical advice, not a diagnosis.</strong> Answers come only
        from the approved fictional HealthProfile demo policies (each answer lists the passages it used as citations) and
        can be wrong. A local language model answers, with prompt <code>{FAQ_PROMPT_VERSION}</code>; the model name is
        shown with each answer.
      </Disclaimer>
      {member ? <AskForm /> : (
        <p className="card">Sign in as a member to ask the FAQ assistant.</p>
      )}
      {admin && <PolicyUpload />}
    </div>
  );
}

function AskForm() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [answer, setAnswer] = useState<FaqAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A ref, not state: it changes at once, so a second submit in the same tick is refused too.
  const inFlight = useRef(false);

  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  const trimmed = question.trim();
  const valid = trimmed.length >= QUESTION_MIN && trimmed.length <= QUESTION_MAX;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !valid) return;
    inFlight.current = true;
    setBusy(true);
    setElapsed(0);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api<FaqAnswer>("/llm/v1/faq/ask/", { method: "POST", body: { question: trimmed } }));
    } catch (err) {
      setError(faqErrorMessage(err));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="faq-ask" style={{ marginBottom: 16 }}>
      <h2 id="faq-ask">Ask a question about the demo policies</h2>
      <form onSubmit={submit} aria-label="Ask the FAQ assistant" className="stack">
        <div className="field">
          <label className="label" htmlFor="faq-question">Your question</label>
          <textarea id="faq-question" className="textarea" value={question} maxLength={QUESTION_MAX} rows={3}
                    onChange={(e) => setQuestion(e.target.value)} aria-describedby="faq-count faq-hint" />
          <span id="faq-count" className="hint">{question.length} / {QUESTION_MAX}</span>
          <span id="faq-hint" className="hint">
            {QUESTION_MIN} to {QUESTION_MAX} characters. Do not include names, email addresses, phone or ID numbers or
            dates of birth.
          </span>
        </div>
        <div>
          <button type="submit" className="btn btn-primary" disabled={busy || !valid}>
            {busy ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>
      <div role="status" aria-live="polite" style={{ marginTop: 8 }}>
        {busy && (
          <span>
            Thinking… {elapsed} s. Real answers usually take 30 to 50 seconds on this computer; the first question after a
            pause can take longer.
          </span>
        )}
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      {answer && <AnswerView answer={answer} />}
    </section>
  );
}

function AnswerView({ answer }: { answer: FaqAnswer }) {
  const u = answer.usage;
  return (
    <section aria-label="Answer" style={{ marginTop: 16 }}>
      <p><span className="badge">{STATUS_TEXT[answer.status]}</span></p>
      <p>{answer.answer}</p>
      {answer.citations.length > 0 && (
        <>
          <h3 style={{ fontSize: 15 }}>Citations (checked against the policy text)</h3>
          <ul aria-label="Citations">
            {answer.citations.map((c) => (
              <li key={`${c.chunk_id}-${c.quote}`}>
                <strong>{c.document_title}</strong> policy: “{c.quote}”
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted">
        Tokens: {u.prompt_tokens ?? "n/a"} in, {u.completion_tokens ?? "n/a"} out
        {u.source === "estimate" ? " (estimated)" : u.source === "none" ? " (the model was not called)" : ""}. Cost:{" "}
        {answer.cost.amount} {answer.cost.currency}: a local model on this computer, so there is no per-token charge
        (hardware and electricity are not counted).
      </p>
      <p className="muted">
        Model: {answer.model} ({answer.provider}), prompt {answer.prompt_version}, {(answer.latency_ms / 1000).toFixed(1)} s,
        {" "}{answer.retrieval.chunks_sent} passages sent.
      </p>
    </section>
  );
}

function PolicyUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stored, setStored] = useState<UploadResult | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setStored(null);
    const problem = checkPolicyFile(file);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    try {
      setStored(await uploadPolicy(file!));
    } catch (err) {
      setError(uploadErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="faq-upload" style={{ marginBottom: 16 }}>
      <h2 id="faq-upload">Upload a policy (admins only)</h2>
      <p className="muted">
        A fictional policy as a .txt or .md file, at most 200 KB, UTF-8 text, with no personal details. It is split into
        chunks and becomes searchable at once.
      </p>
      <form onSubmit={submit} className="stack">
        <div className="field">
          <label className="label" htmlFor="policy-file">Policy file (.txt or .md, at most 200 KB)</label>
          <input id="policy-file" type="file" accept=".txt,.md,text/plain,text/markdown"
                 onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <div>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
        </div>
      </form>
      {error && <div className="form-error" role="alert">{error}</div>}
      {stored && (
        <p role="status">
          Stored “{stored.title}” ({stored.filename}) as {stored.chunks} {stored.chunks === 1 ? "chunk" : "chunks"} with{" "}
          {stored.embedding_model}.
        </p>
      )}
    </section>
  );
}
