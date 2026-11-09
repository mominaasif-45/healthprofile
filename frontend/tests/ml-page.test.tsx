import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
// The real committed reports, so the page is tested against the data it will really show.
import clustersReport from "../../backend/ml/reports/clusters.json";
import workbenchReport from "../../backend/ml/reports/workbench.json";

// A stand-in for the backend: who is signed in, and what the FAQ endpoint answers.
const server = vi.hoisted(() => ({
  member: true,
  admin: false,
  ask: null as null | ((body: unknown) => Promise<unknown>),
  replace: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: vi.fn(async (path: string, opts: { method?: string; body?: unknown } = {}) => {
      if (path === "/auth/me/") {
        if (!server.member) throw new real.ApiError(401, "not_authenticated", "RAW-SERVER-TEXT");
        return { id: 1, email: "test.member@example.com", name: "Test Member", role: "user" };
      }
      if (path === "/admin/me/") {
        if (!server.admin) throw new real.ApiError(403, "not_authenticated", "RAW-SERVER-TEXT");
        return { id: 2, email: "admin@example.com", name: "Admin", role: "admin" };
      }
      if (path === "/ml/v1/workbench/") return workbenchReport;
      if (path === "/ml/v1/clusters/") return clustersReport;
      if (path === "/llm/v1/faq/ask/" && opts.method === "POST") return server.ask!(opts.body);
      throw new Error(`unexpected call ${path}`);
    }),
    userLogout: vi.fn(async () => {}),
  };
});
vi.mock("@/lib/ml", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/ml")>();
  return { ...real, uploadPolicy: vi.fn() };
});
vi.mock("@/components/Theme", () => ({ ThemeToggle: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: server.replace, push: vi.fn() }) }));

import MlPage from "@/app/ml/page";
import { ApiError, api } from "@/lib/api";
import { uploadPolicy } from "@/lib/ml";

const mockedApi = vi.mocked(api);
const askCalls = () => mockedApi.mock.calls.filter(([path]) => path === "/llm/v1/faq/ask/");

const ANSWER = {
  status: "answered",
  answer: "A member can add up to three emergency contacts to a profile.",
  citations: [{ chunk_id: "3", document_id: 2, document_title: "Emergency contacts",
                quote: "A member can add up to three emergency contacts to a profile." }],
  retrieval: { top_k: 3, min_similarity: 0.62, chunk_size: 600, chunk_overlap: 100,
               embedding_model: "ollama:nomic-embed-text", best_similarity: 0.7841, chunks_sent: 3,
               unverified_citations_removed: 0 },
  provider: "ollama", model: "llama3.2:3b", prompt_version: "faq-system-2",
  usage: { prompt_tokens: 706, completion_tokens: 54, total_tokens: 760, source: "provider" },
  cost: { amount: "0.00", currency: "USD",
          note: "Local model on this computer: no per-token charge. Hardware and electricity are not counted." },
  latency_ms: 35600,
  disclaimer: "Educational demo on synthetic data.",
};

async function openPage() {
  render(<MlPage />);
  return screen.findByRole("tablist", { name: "ML dashboard sections" });
}

async function openTab(name: string) {
  await openPage();
  await userEvent.click(screen.getByRole("tab", { name }));
  return screen.getByRole("tabpanel", { name });
}

beforeEach(() => {
  server.member = true;
  server.admin = false;
  server.ask = null;
  server.replace.mockClear();
  mockedApi.mockClear();
  vi.mocked(uploadPolicy).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

// ================================================================ page, sign-in, tabs
describe("ML dashboard page", () => {
  it("sends a visitor who is signed in neither as a member nor as an admin to the login page", async () => {
    server.member = false;
    render(<MlPage />);
    await vi.waitFor(() => expect(server.replace).toHaveBeenCalledWith("/login"));
  });

  it("has three tabs with the right roles, and the first one is selected", async () => {
    const tablist = await openPage();
    const tabs = within(tablist).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Supervised", "Clusters", "FAQ assistant"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
    expect(tabs[0]).toHaveAttribute("tabindex", "0");
    expect(tabs[1]).toHaveAttribute("tabindex", "-1");
    const panel = screen.getByRole("tabpanel", { name: "Supervised" });
    expect(tabs[0]).toHaveAttribute("aria-controls", panel.id);
  });

  it("switches tabs with the arrow keys, Home and End, and moves focus", async () => {
    await openPage();
    const user = userEvent.setup();
    const tab = (name: string) => screen.getByRole("tab", { name });
    tab("Supervised").focus();
    await user.keyboard("{ArrowRight}");
    expect(tab("Clusters")).toHaveFocus();
    expect(tab("Clusters")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Clusters" })).toBeInTheDocument();
    await user.keyboard("{End}");
    expect(tab("FAQ assistant")).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(tab("Supervised")).toHaveFocus(); // wraps around
    await user.keyboard("{ArrowLeft}");
    expect(tab("FAQ assistant")).toHaveFocus();
    await user.keyboard("{Home}");
    expect(tab("Supervised")).toHaveFocus();
    expect(screen.getByRole("tabpanel", { name: "Supervised" })).toBeInTheDocument();
  });

  it("has a disclaimer with synthetic data, educational demo, not medical advice and a version on every tab", async () => {
    await openPage();
    const versions = { Supervised: "workbench-1.0.0", Clusters: "clusters-1.0.0", "FAQ assistant": "faq-system-2" };
    for (const [name, version] of Object.entries(versions)) {
      await userEvent.click(screen.getByRole("tab", { name }));
      const note = within(screen.getByRole("tabpanel", { name })).getByRole("note");
      expect(note).toHaveTextContent(/synthetic data only/i);
      expect(note).toHaveTextContent(/educational demo/i);
      expect(note).toHaveTextContent(/not medical advice/i);
      expect(note).toHaveTextContent(version);
    }
  });

  it("never uses the words 'risk group' or 'patient type' on any tab", async () => {
    await openPage();
    for (const name of ["Supervised", "Clusters", "FAQ assistant"]) {
      await userEvent.click(screen.getByRole("tab", { name }));
      expect(document.body.textContent).not.toMatch(/risk group|patient type/i);
    }
  });
});

// ================================================================ supervised tab
describe("Supervised tab", () => {
  it("shows the versions, the four models with validation and cross-validation metrics", async () => {
    const panel = await openTab("Supervised");
    expect(panel).toHaveTextContent("workbench-1.0.0");
    expect(panel).toHaveTextContent("noshow-1.0.0");
    expect(panel).toHaveTextContent(/seed 42/i);
    const table = within(panel).getByRole("table", { name: /validation comparison/i });
    for (const name of ["Baseline", "Logistic regression", "Random forest", "Gradient boosting"]) {
      expect(within(table).getByRole("rowheader", { name })).toBeInTheDocument();
    }
    expect(table).toHaveTextContent("0.308"); // logistic regression validation PR-AUC
    expect(table).toHaveTextContent("0.347 ± 0.044"); // its cross-validated PR-AUC
  });

  it("says which model is used and that the choice used the validation pile only", async () => {
    const panel = await openTab("Supervised");
    const choice = within(panel).getByRole("region", { name: /which model and why/i });
    expect(choice).toHaveTextContent(/logistic regression/i);
    expect(choice).toHaveTextContent(/validation/i);
    expect(choice).toHaveTextContent(/random forest/i); // best on validation PR-AUC, but practically tied
  });

  it("shows the confusion matrix at the 0.22 decision line", async () => {
    const panel = await openTab("Supervised");
    const matrix = within(panel).getByRole("table", { name: /confusion matrix/i });
    expect(matrix).toHaveTextContent("0.22");
    for (const value of ["100", "224", "87", "489"]) expect(matrix).toHaveTextContent(value);
  });

  it("shows permutation importance, the overfitting gap and the mistakes inspection", async () => {
    const panel = await openTab("Supervised");
    const importance = within(panel).getByRole("region", { name: /permutation importance/i });
    expect(importance).toHaveTextContent("lead_time_days");
    expect(importance.querySelector("svg")).not.toBeNull();
    const gap = within(panel).getByRole("table", { name: /training versus validation/i });
    expect(gap).toHaveTextContent("+0.274");
    const errors = within(panel).getByRole("region", { name: /false positives and false negatives/i });
    expect(errors).toHaveTextContent(/false alarms/i);
    expect(errors).toHaveTextContent(/missed no-shows/i);
    expect(errors).toHaveTextContent("A04329"); // the most confident false alarm
  });

  it("shows the test pile result exactly once, labelled as used once and not used to choose", async () => {
    const panel = await openTab("Supervised");
    const tests = within(panel).getAllByRole("table", { name: /test pile/i });
    expect(tests).toHaveLength(1);
    const section = within(panel).getByRole("region", { name: /test pile/i });
    expect(section).toHaveTextContent(/used once/i);
    expect(section).toHaveTextContent(/not used to choose/i);
    expect(tests[0]).toHaveTextContent("0.340"); // logistic regression test PR-AUC
  });
});

// ================================================================ clusters tab
describe("Clusters tab", () => {
  it("is labelled exploratory and shows the version, elbow, silhouette and the chosen k", async () => {
    const panel = await openTab("Clusters");
    expect(panel).toHaveTextContent(/exploratory/i);
    expect(panel).toHaveTextContent("clusters-1.0.0");
    const elbow = within(panel).getByRole("table", { name: /elbow and silhouette/i });
    expect(within(elbow).getAllByRole("row")).toHaveLength(8); // header + k = 2..8
    expect(elbow).toHaveTextContent("13408");
    expect(elbow).toHaveTextContent("0.260");
    expect(panel).toHaveTextContent(/k = 2/);
    expect(panel).toHaveTextContent(/weak structure/i);
  });

  it("draws the 2D PCA scatter with 500 points, shapes per cluster and the variance kept", async () => {
    const panel = await openTab("Clusters");
    const figure = within(panel).getByRole("img", { name: /PCA/ });
    expect(figure.querySelectorAll("[data-point]")).toHaveLength(500);
    expect(figure.querySelectorAll("circle[data-point]").length).toBeGreaterThan(0);
    expect(figure.querySelectorAll("rect[data-point]").length).toBeGreaterThan(0); // not colour alone
    expect(panel).toHaveTextContent("33%");
    expect(panel).toHaveTextContent("25%");
    expect(panel).toHaveTextContent("58%");
  });

  it("shows the cluster descriptions and how much the two methods agree", async () => {
    const panel = await openTab("Clusters");
    expect(panel).toHaveTextContent(clustersReport.summary[0].description);
    expect(panel).toHaveTextContent(clustersReport.summary[1].description);
    expect(panel).toHaveTextContent("0.594");
    expect(panel).toHaveTextContent(/agglomerative/i);
  });
});

// ================================================================ FAQ assistant tab
describe("FAQ assistant tab", () => {
  it("counts characters and only allows questions of 3 to 500 characters", async () => {
    const panel = await openTab("FAQ assistant");
    const box = within(panel).getByLabelText("Your question");
    const button = within(panel).getByRole("button", { name: "Ask" });
    expect(within(panel).getByText("0 / 500")).toBeInTheDocument();
    expect(button).toBeDisabled();
    await userEvent.type(box, "Hi");
    expect(within(panel).getByText("2 / 500")).toBeInTheDocument();
    expect(button).toBeDisabled();
    await userEvent.type(box, "!");
    expect(button).toBeEnabled();
    expect(box).toHaveAttribute("maxlength", "500");
  });

  it("shows a thinking state with elapsed seconds, and a second submit sends nothing", async () => {
    let finish!: (value: unknown) => void;
    server.ask = () => new Promise((resolve) => { finish = resolve; });
    const panel = await openTab("FAQ assistant");
    fireEvent.change(within(panel).getByLabelText("Your question"), {
      target: { value: "How many emergency contacts can I add?" } });
    const form = within(panel).getByRole("form", { name: /ask the faq assistant/i });
    fireEvent.submit(form);
    fireEvent.submit(form); // double submit (for example Enter pressed twice)
    expect(askCalls()).toHaveLength(1);
    const button = within(panel).getByRole("button", { name: /thinking/i });
    expect(button).toBeDisabled();
    const status = within(panel).getByRole("status");
    expect(status).toHaveTextContent(/thinking/i);
    expect(status).toHaveTextContent("0 s");
    expect(status).toHaveTextContent(/30 to 50 seconds/);
    // Real time (fake timers stall React here): the counter moves on after a second.
    await vi.waitFor(() => expect(status).toHaveTextContent("1 s"), { timeout: 2500 });
    fireEvent.click(button);
    expect(askCalls()).toHaveLength(1);
    finish(ANSWER); // the findBy query below waits for the re-render
    expect(await within(panel).findByText(ANSWER.answer, { selector: "p" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Ask" })).toBeEnabled();
    expect(askCalls()[0][1]).toMatchObject({ method: "POST", body: { question: "How many emergency contacts can I add?" } });
  });

  it("shows the status, answer, citations, tokens and the 0.00 local cost", async () => {
    server.ask = async () => ANSWER;
    const panel = await openTab("FAQ assistant");
    await userEvent.type(within(panel).getByLabelText("Your question"), "How many emergency contacts can I add?");
    await userEvent.click(within(panel).getByRole("button", { name: "Ask" }));
    const result = await within(panel).findByRole("region", { name: /answer/i });
    expect(result).toHaveTextContent(/answered/i);
    expect(result).toHaveTextContent(ANSWER.answer);
    const citations = within(result).getByRole("list", { name: /citations/i });
    expect(citations).toHaveTextContent("Emergency contacts");
    expect(citations).toHaveTextContent(ANSWER.citations[0].quote);
    expect(result).toHaveTextContent("706");
    expect(result).toHaveTextContent("54");
    expect(result).toHaveTextContent("0.00");
    expect(result).toHaveTextContent(/local model/i);
    expect(result).toHaveTextContent("llama3.2:3b");
  });

  it("shows a refusal status with no citations", async () => {
    server.ask = async () => ({ ...ANSWER, status: "insufficient_information", citations: [],
      answer: "I could not find this in the approved HealthProfile demo policies, so I will not guess." });
    const panel = await openTab("FAQ assistant");
    await userEvent.type(within(panel).getByLabelText("Your question"), "How far is the Moon?");
    await userEvent.click(within(panel).getByRole("button", { name: "Ask" }));
    const result = await within(panel).findByRole("region", { name: /answer/i });
    expect(result).toHaveTextContent(/not in the policies/i);
    expect(within(result).queryByRole("list", { name: /citations/i })).toBeNull();
  });

  const ERRORS: [string, () => Error, RegExp][] = [
    ["400 personal details", () => new ApiError(400, "validation_error", "RAW-SERVER-TEXT", { question: ["RAW-SERVER-TEXT"] }), /personal details/i],
    ["401 signed out", () => new ApiError(401, "not_authenticated", "RAW-SERVER-TEXT"), /sign in again/i],
    ["429 throttled", () => new ApiError(429, "throttled", "RAW-SERVER-TEXT"), /wait a minute/i],
    ["502 bad reply", () => new ApiError(502, "llm_bad_reply", "RAW-SERVER-TEXT"), /wrong format/i],
    ["503 unavailable", () => new ApiError(503, "llm_unavailable", "RAW-SERVER-TEXT"), /not available right now/i],
    ["504 timeout", () => new ApiError(504, "llm_timeout", "RAW-SERVER-TEXT"), /took too long/i],
    ["network error", () => new TypeError("Failed to fetch RAW-SERVER-TEXT"), /could not reach the server/i],
    ["anything else", () => new ApiError(500, "error", "RAW-SERVER-TEXT"), /something went wrong/i],
  ];

  it.each(ERRORS)("maps %s to a safe message and never shows raw server text", async (_label, error, message) => {
    server.ask = async () => { throw error(); };
    const panel = await openTab("FAQ assistant");
    await userEvent.type(within(panel).getByLabelText("Your question"), "How many emergency contacts can I add?");
    await userEvent.click(within(panel).getByRole("button", { name: "Ask" }));
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(document.body.textContent).not.toContain("RAW-SERVER-TEXT");
    expect(within(panel).getByRole("button", { name: "Ask" })).toBeEnabled(); // can try again
  });

  it("says answers come only from the listed documents and can be wrong", async () => {
    const panel = await openTab("FAQ assistant");
    const note = within(panel).getByRole("note");
    expect(note).toHaveTextContent(/only from/i);
    expect(note).toHaveTextContent(/can be wrong/i);
  });
});

// ================================================================ policy upload (admins only)
describe("Policy upload", () => {
  it("is hidden from members who are not admins", async () => {
    const panel = await openTab("FAQ assistant");
    expect(within(panel).queryByRole("region", { name: /upload a policy/i })).toBeNull();
    expect(within(panel).queryByLabelText(/policy file/i)).toBeNull();
  });

  it("is shown to an admin and shows the server's error message for a refused file", async () => {
    server.admin = true;
    vi.mocked(uploadPolicy).mockRejectedValue(
      new ApiError(400, "validation_error", "Invalid input.", { file: ["Only .txt and .md files can be uploaded."] }));
    const panel = await openTab("FAQ assistant");
    const upload = within(panel).getByRole("region", { name: /upload a policy/i });
    const input = within(upload).getByLabelText(/policy file/i);
    await userEvent.upload(input, new File(["# Policy\n\nText."], "policy.md", { type: "text/markdown" }));
    await userEvent.click(within(upload).getByRole("button", { name: /upload/i }));
    expect(await within(upload).findByRole("alert")).toHaveTextContent("Only .txt and .md files can be uploaded.");
  });

  it("checks the file type and size before sending", async () => {
    server.admin = true;
    const panel = await openTab("FAQ assistant");
    const upload = within(panel).getByRole("region", { name: /upload a policy/i });
    const input = within(upload).getByLabelText(/policy file/i);
    fireEvent.change(input, { target: { files: [new File(["x".repeat(200 * 1024 + 1)], "big.md")] } });
    await userEvent.click(within(upload).getByRole("button", { name: /upload/i }));
    expect(await within(upload).findByRole("alert")).toHaveTextContent(/200 KB/);
    fireEvent.change(input, { target: { files: [new File(["%PDF"], "policy.pdf")] } });
    await userEvent.click(within(upload).getByRole("button", { name: /upload/i }));
    expect(await within(upload).findByRole("alert")).toHaveTextContent(/\.txt or \.md/);
    expect(uploadPolicy).not.toHaveBeenCalled();
  });

  it("shows what was stored after a successful upload", async () => {
    server.admin = true;
    vi.mocked(uploadPolicy).mockResolvedValue({
      id: 9, title: "Visiting hours", filename: "visiting-hours.md", sha256: "a".repeat(64), size_bytes: 120,
      chunks: 1, embedding_model: "ollama:nomic-embed-text", chunk_size: 600, chunk_overlap: 100 });
    const panel = await openTab("FAQ assistant");
    const upload = within(panel).getByRole("region", { name: /upload a policy/i });
    await userEvent.upload(within(upload).getByLabelText(/policy file/i),
      new File(["# Visiting hours\n\nText."], "visiting-hours.md", { type: "text/markdown" }));
    await userEvent.click(within(upload).getByRole("button", { name: /upload/i }));
    expect(await within(upload).findByRole("status")).toHaveTextContent(/Visiting hours/);
    expect(within(upload).getByRole("status")).toHaveTextContent(/1 chunk/);
  });

  it("lets an admin who is not signed in as a member use the upload, with a note about the member tabs", async () => {
    server.member = false;
    server.admin = true;
    await openPage();
    expect(server.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("tabpanel", { name: "Supervised" })).toHaveTextContent(/sign in as a member/i);
    await userEvent.click(screen.getByRole("tab", { name: "FAQ assistant" }));
    const panel = screen.getByRole("tabpanel", { name: "FAQ assistant" });
    expect(within(panel).getByRole("region", { name: /upload a policy/i })).toBeInTheDocument();
    expect(within(panel).queryByLabelText("Your question")).toBeNull();
  });
});
