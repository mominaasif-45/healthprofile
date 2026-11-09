/**
 * Week 4 ML dashboard: report types, the FAQ answer type, the admin policy upload and safe error messages.
 *
 * The upload is multipart (a file), so it cannot use api(), which sends JSON. It follows the same rules: same-origin
 * cookies (the admin session), the X-CSRFToken header, and the {"error": {code, message, fields}} shape -> ApiError.
 */
import { ApiError, ensureCsrf, type Fields } from "./api";

// ------------------------------------------------------------------ GET /api/ml/v1/workbench/
type Metrics = {
  roc_auc: number; pr_auc: number; brier: number; threshold: number; precision: number; recall: number; f1: number;
  balanced_accuracy: number; accuracy: number; tp: number; fp: number; fn: number; tn: number;
};
type MeanSd = { mean: number; sd: number; folds: number[] };

export type WorkbenchModel = {
  tuning: { best_params: Record<string, string | number>; cv_pr_auc: number | null };
  cv: { rows: number; roc_auc: MeanSd; pr_auc: MeanSd };
  train: { roc_auc: number; pr_auc: number; brier: number; f1: number };
  validation: Metrics;
  gap: { pr_auc: number; overfit: boolean };
};

export type Inspected = Record<string, string | number | null> & { appointment_id: string; p: number };

export type Workbench = {
  version: string;
  disclaimer: string;
  test_pile_note: string;
  settings: { split_seed: number; model_seed: number; cv_folds: number; rf_search_tries: number;
              permutation_repeats: number; overfit_gap: number; scikit_learn: string; shipped_model: string };
  pile_sizes: Record<"train" | "validation" | "test", { rows: number; no_shows: number }>;
  models: Record<string, WorkbenchModel>;
  best_on_validation: string;
  importance: Record<string, { feature: string; mean: number; sd: number }[]>;
  errors: {
    model: string;
    threshold: number;
    profile: { box: string; rows: number; mean_predicted: number; no_reminder: number; mean_lead_time: number;
               any_prior_no_show: number; phone_booking: number }[];
    false_alarms: Inspected[];
    misses: Inspected[];
  };
  test: Record<string, Metrics>;
};

// ------------------------------------------------------------------ GET /api/ml/v1/clusters/
export type ClusterSummary = {
  cluster: number; rows: number; share: number; mean_lead_time: number; mean_prior_visits: number;
  any_prior_no_show: number; reminder_yes: number; channel: Record<string, number>; description: string;
};

export type Clusters = {
  version: string;
  disclaimer: string;
  features: string[];
  settings: { split_seed: number; seed: number; n_init: number; k_range: number[]; plot_points: number };
  elbow: { k: number; inertia: number; silhouette: number }[];
  chosen_k: number;
  structure_note: string;
  kmeans: { silhouette: number; sizes: number[] };
  agglomerative: { k: number; linkage: string; silhouette: number; sizes: number[]; adjusted_rand_vs_kmeans: number };
  validation: { rows: number; sizes: number[]; silhouette: number };
  pca: { explained_variance: number[]; points: [number, number, number][] };
  summary: ClusterSummary[];
};

// ------------------------------------------------------------------ POST /api/llm/v1/faq/ask/
export type FaqStatus = "answered" | "insufficient_information" | "out_of_scope";

export type FaqAnswer = {
  status: FaqStatus;
  answer: string;
  citations: { chunk_id: string; document_id: number; document_title: string; quote: string }[];
  retrieval: { top_k: number; min_similarity: number; best_similarity: number | null; chunks_sent: number;
               unverified_citations_removed: number; embedding_model: string };
  provider: string;
  model: string;
  prompt_version: string;
  usage: { prompt_tokens: number | null; completion_tokens: number | null; total_tokens: number | null; source: string };
  cost: { amount: string; currency: string; note: string };
  latency_ms: number;
  disclaimer: string;
};

export const FAQ_PROMPT_VERSION = "faq-system-2";
export const QUESTION_MIN = 3;
export const QUESTION_MAX = 500;

/**
 * A friendly message for every way asking can fail. The server's own text is never shown: it is replaced by a fixed
 * sentence chosen from the status code.
 */
export function faqErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400:
        return "This question was not sent because it seems to contain personal details (an email address, a phone or ID number, a date written in digits, or your name). Remove them and try again.";
      case 401:
        return "Your session has ended. Please sign in again.";
      case 403:
        return "Your session could not be confirmed. Reload the page and try again.";
      case 429:
        return "You have asked 10 questions in the last minute. Please wait a minute and try again.";
      case 502:
        return "The assistant's answer came back in the wrong format, so it was not shown. Please try again or rephrase your question.";
      case 503:
        return "The assistant is not available right now (the local model may not be running). Please try again later.";
      case 504:
        return "The assistant took too long to answer (more than 100 seconds). Please try again: the first question after a pause is the slowest.";
      default:
        return "Something went wrong. Please try again.";
    }
  }
  if (err instanceof TypeError) return "Could not reach the server. Check your connection and try again.";
  return "Something went wrong. Please try again.";
}

// ------------------------------------------------------------------ POST /api/llm/v1/policies/ (admins only)
export type UploadResult = {
  id: number; title: string; filename: string; sha256: string; size_bytes: number; chunks: number;
  embedding_model: string; chunk_size: number; chunk_overlap: number;
};

export const UPLOAD_MAX_BYTES = 200 * 1024;
export const UPLOAD_EXTENSIONS = [".txt", ".md"];

function csrfCookie(): string {
  const match = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
}

export async function uploadPolicy(file: File): Promise<UploadResult> {
  await ensureCsrf();
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/llm/v1/policies/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrfCookie() }, // no Content-Type: the browser adds the multipart boundary
    body,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; fields?: Fields } } | null)?.error;
    throw new ApiError(res.status, err?.code ?? "error", err?.message ?? `Request failed (${res.status})`,
                       err?.fields ?? {});
  }
  return data as UploadResult;
}

/** The upload message to show: the server's own (fixed, safe) reason for a refused file, or a fixed sentence. */
export function uploadErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const reason = err.fields.file?.[0] ?? Object.values(err.fields)[0]?.[0];
    if (err.status === 400 && reason) return reason;
    if (err.status === 401 || err.status === 403) return "Only admins can upload, or your admin session has ended. Sign in again at /admin/login.";
    if (err.status === 409) return "This document has already been uploaded.";
    if (err.status === 429) return "Too many uploads in the last minute. Please wait a minute.";
    if (err.status === 503 || err.status === 504) return "The embedding model is not available right now, so nothing was stored. Please try again later.";
    return "The upload failed. Please try again.";
  }
  if (err instanceof TypeError) return "Could not reach the server. Check your connection and try again.";
  return "The upload failed. Please try again.";
}

/** Client-side check before sending (the server checks again; it is the authority). */
export function checkPolicyFile(file: File | null): string | null {
  if (!file) return "Choose a .txt or .md file first.";
  const name = file.name.toLowerCase();
  if (!UPLOAD_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Only .txt or .md files can be uploaded.";
  if (file.size > UPLOAD_MAX_BYTES) return "The file is larger than 200 KB.";
  if (file.size === 0) return "The file is empty.";
  return null;
}
