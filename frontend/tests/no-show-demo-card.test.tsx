import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NoShowResponse, Profile } from "@/lib/api";

// A stand-in for the backend. `reply` decides what POST /ml/v1/no-show/predict/ answers.
const server = vi.hoisted(() => ({
  profile: null as Profile | null,
  reply: null as null | ((body: unknown) => Promise<unknown>),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: vi.fn(async (path: string, opts: { method?: string; body?: unknown } = {}) => {
      if (path === "/ml/v1/no-show/predict/" && opts.method === "POST") return server.reply!(opts.body);
      if (path === "/auth/me/") return { id: 1, email: "test.member@example.com", name: "Test Member", role: "user" };
      if (path === "/profiles/me/") {
        if (!server.profile) throw new real.ApiError(404, "not_found", "Not found.");
        return server.profile;
      }
      throw new Error(`unexpected call ${path}`);
    }),
  };
});
vi.mock("@/components/Theme", () => ({ ThemeToggle: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

import ProfilePage from "@/app/profile/page";
import { NoShowDemoCard } from "@/components/profile/NoShowDemoCard";
import { ApiError, api } from "@/lib/api";

const URL = "/ml/v1/no-show/predict/";
const DISCLAIMER =
  "Educational demo trained on synthetic data. Not medical advice, not a diagnosis, and not a prediction about any real person or appointment.";
const LIKELY_MISSED: NoShowResponse = {
  prediction: "likely_no_show", probability: 0.5279, threshold: 0.22, model_version: "noshow-1.0.0", disclaimer: DISCLAIMER,
};
const LIKELY_ATTENDED: NoShowResponse = { ...LIKELY_MISSED, prediction: "likely_attend", probability: 0.0505 };
// The prefilled fictional appointment: the same as the first Swagger example.
const EXAMPLE = {
  lead_time_days: 21, weekday: "mon", hour: 9, visit_type: "new_visit", booking_channel: "online",
  reminder_sent: "no", prior_visits: 3, prior_no_shows: 1, distance_band: "15_30km", age_band: null,
};

const mockedApi = vi.mocked(api);
const predictCalls = () => mockedApi.mock.calls.filter(([path]) => path === URL);
const field = (label: string) => screen.getByLabelText(label);
const checkButton = () => screen.getByRole("button", { name: /Check this example|Checking/ });

async function replace(user: ReturnType<typeof userEvent.setup>, label: string, value: string) {
  await user.clear(field(label));
  if (value) await user.type(field(label), value);
}

function profile(status: Profile["status"] = "active"): Profile {
  return {
    id: 1, status, completion: { status: "not_started", percent: 0, missing: [] }, demographics: null,
    emergency_contacts: [], wellness: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

beforeEach(() => {
  mockedApi.mockClear();
  server.profile = null;
  server.reply = async () => LIKELY_MISSED;
});

describe("No-show demo card", () => {
  it("shows the disclaimer and the prefilled fictional example, and calls nothing on load", () => {
    render(<NoShowDemoCard />);
    expect(screen.getByRole("heading", { name: "No-show likelihood demo" })).toBeInTheDocument();
    expect(screen.getByText(/Educational demo\./)).toBeInTheDocument();
    expect(screen.getByText(/not medical advice or a diagnosis/i)).toBeInTheDocument();
    expect(screen.getByText(/never uses your profile/i)).toBeInTheDocument();
    expect(field("Days between booking and appointment")).toHaveValue(21);
    expect(field("Day")).toHaveValue("mon");
    expect(field("Age group")).toHaveValue("");
    expect(within(field("Age group")).getByRole("option", { name: "Not recorded" })).toBeInTheDocument();
    expect(predictCalls()).toHaveLength(0);
  });

  it("sends exactly the 10 fields, with numbers as numbers and 'Not recorded' as null", async () => {
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await user.click(checkButton());
    expect(predictCalls()).toHaveLength(1);
    expect(predictCalls()[0][1]).toEqual({ method: "POST", body: EXAMPLE });
  });

  it("shows the percentage, the verdict, the threshold, the model version and the disclaimer", async () => {
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    const result = screen.getByRole("region", { name: "Demo result" });
    expect(result).toHaveAttribute("aria-live", "polite");
    await user.click(checkButton());

    expect(await within(result).findByText("52.8% chance this fictional appointment is missed")).toBeInTheDocument();
    expect(within(result).getByText(/Above the 22% line/)).toHaveTextContent("likely to be missed");
    expect(within(result).getByText(/Model noshow-1\.0\.0/)).toBeInTheDocument();
    expect(within(result).getByText(DISCLAIMER)).toBeInTheDocument();
    const meter = within(result).getByRole("meter", { name: "Chance of a missed appointment" });
    expect(meter).toHaveAttribute("aria-valuenow", "52.8");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "100");
  });

  it("words a low chance as likely to be attended", async () => {
    server.reply = async () => LIKELY_ATTENDED;
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await user.click(checkButton());
    expect(await screen.findByText("5.1% chance this fictional appointment is missed")).toBeInTheDocument();
    expect(screen.getByText(/Below the 22% line/)).toHaveTextContent("likely to be attended");
  });

  it("sends null for blanks: 'Not recorded' reminder and both earlier fields left empty", async () => {
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await user.selectOptions(field("Reminder sent"), "Not recorded");
    await replace(user, "Earlier appointments", "");
    await replace(user, "Earlier missed appointments", "");
    await user.click(checkButton());
    expect(predictCalls()[0][1]).toEqual({
      method: "POST", body: { ...EXAMPLE, reminder_sent: null, prior_visits: null, prior_no_shows: null },
    });
  });

  it.each([
    ["Days between booking and appointment", "91", "Enter a whole number from 0 to 90."],
    ["Days between booking and appointment", "2.5", "Enter a whole number from 0 to 90."],
    ["Days between booking and appointment", "", "Enter a whole number from 0 to 90."],
    ["Earlier appointments", "21", "Enter a whole number from 0 to 20."],
    ["Earlier missed appointments", "5", "Can't be more than earlier appointments."],
    ["Earlier missed appointments", "", "Fill in both earlier fields, or leave both empty."],
  ])("blocks bad input before sending: %s = '%s'", async (label, value, message) => {
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await replace(user, label, value);
    await user.click(checkButton());
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(predictCalls()).toHaveLength(0);
  });

  it("marks the invalid field for assistive technology", async () => {
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await replace(user, "Days between booking and appointment", "91");
    await user.click(checkButton());
    expect(field("Days between booking and appointment")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a whole number from 0 to 90.");
  });

  it("shows the server's field errors under the right fields", async () => {
    server.reply = async () => {
      throw new ApiError(400, "validation_error", "Invalid input.", {
        weekday: ["Must be one of: mon, tue, wed, thu, fri, sat."],
      });
    };
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await user.click(checkButton());
    expect(await screen.findByText("Must be one of: mon, tue, wed, thu, fri, sat.")).toBeInTheDocument();
    expect(field("Day")).toHaveAttribute("aria-invalid", "true");
  });

  it.each([
    [401, "not_authenticated", "Your session has ended. Please sign in again."],
    [403, "permission_denied", "Your request was blocked for security reasons. Reload the page and try again."],
    [429, "throttled", "That's a lot of checks in a short time. Please wait a minute and try again."],
    [503, "model_unavailable", "The demo model is unavailable right now. Please try again later."],
  ])("explains a %s answer and keeps what was typed", async (status, code, message) => {
    server.reply = async () => {
      throw new ApiError(status, code, "server text");
    };
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await replace(user, "Days between booking and appointment", "35");
    await user.click(checkButton());
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(field("Days between booking and appointment")).toHaveValue(35);
    if (status === 401) expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login");
  });

  it("clears the result as soon as a field changes", async () => {
    const user = userEvent.setup();
    render(<NoShowDemoCard />);
    await user.click(checkButton());
    expect(await screen.findByText(/chance this fictional appointment is missed/)).toBeInTheDocument();
    await user.selectOptions(field("Day"), "Thursday");
    expect(screen.queryByText(/chance this fictional appointment is missed/)).not.toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });

  it("works with the keyboard only: Tab to the first field, Enter sends; the button waits while checking", async () => {
    let answer: (value: NoShowResponse) => void = () => {};
    server.reply = () => new Promise((resolve) => (answer = resolve));
    const user = userEvent.setup();
    render(<NoShowDemoCard />);

    await user.tab();
    expect(field("Days between booking and appointment")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(predictCalls()).toHaveLength(1);
    expect(checkButton()).toHaveTextContent("Checking…");
    expect(checkButton()).toBeDisabled();

    answer(LIKELY_MISSED);
    expect(await screen.findByText(/52\.8% chance/)).toBeInTheDocument();
    expect(checkButton()).toHaveTextContent("Check this example");
    expect(checkButton()).toBeEnabled();
  });

  it("never uses medical or personal wording", async () => {
    const user = userEvent.setup();
    const { container } = render(<NoShowDemoCard />);
    const check = () => {
      const text = (container.textContent ?? "")
        .toLowerCase()
        .replace("not medical advice or a diagnosis", "")
        .replace("not medical advice, not a diagnosis", "");
      for (const word of ["patient", "diagnos", "risk", "health", "symptom", "illness", "your appointment"]) {
        expect(text).not.toContain(word);
      }
    };
    check();
    await user.click(checkButton());
    await screen.findByText(/52\.8% chance/);
    check();
  });
});

describe("No-show demo card on the profile page", () => {
  it.each(["active", "deactivated"] as const)("sits right after the wellness card (%s profile) with a side-menu link", async (status) => {
    server.profile = profile(status);
    render(<ProfilePage />);
    const wellness = await screen.findByRole("heading", { name: "Wellness preferences and goals" });
    const demo = screen.getByRole("heading", { name: "No-show likelihood demo" });
    expect(wellness.compareDocumentPosition(demo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const wellnessCard = wellness.closest("section")!;
    expect(wellnessCard.nextElementSibling).toBe(demo.closest("section"));
    expect(demo.closest("section")).toHaveAttribute("id", "no-show-demo");
    expect(checkButton()).toBeEnabled(); // usable even when the profile is read-only
    expect(screen.getByRole("link", { name: "No-show demo" })).toHaveAttribute("href", "#no-show-demo");
  });

  it("is hidden when the member has no profile yet", async () => {
    render(<ProfilePage />);
    expect(await screen.findByRole("button", { name: "Create my profile" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "No-show likelihood demo" })).not.toBeInTheDocument();
  });
});
