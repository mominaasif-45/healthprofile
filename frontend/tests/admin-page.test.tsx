import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdminRow } from "@/lib/api";

// An in-memory stand-in for the backend: the list endpoint filters by status, deactivate flips one row.
const server = vi.hoisted(() => ({ rows: [] as AdminRow[] }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: vi.fn(async (path: string) => {
    const deactivate = path.match(/^\/admin\/profiles\/(\d+)\/deactivate\/$/);
    if (deactivate) {
      const row = server.rows.find((r) => r.id === Number(deactivate[1]))!;
      row.status = "deactivated";
      return { ...row };
    }
    const status = new URLSearchParams(path.split("?")[1]).get("status");
    const results = server.rows.filter((r) => !status || r.status === status).map((r) => ({ ...r }));
    return { count: results.length, next: null, previous: null, results };
  }),
}));

vi.mock("@/lib/useAdmin", () => ({
  useAdmin: () => ({ admin: { email: "admin@example.com" }, signOut: vi.fn(), handleSessionError: () => false }),
}));

// ThemeToggle needs window.matchMedia (not in jsdom) and Link needs the Next router; neither matters here.
vi.mock("@/components/Theme", () => ({ ThemeToggle: () => null }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import AdminPage from "@/app/admin/page";

function profile(id: number, full_name: string): AdminRow {
  return {
    id,
    full_name,
    email: `${full_name.split(" ")[0].toLowerCase()}@example.com`,
    age_range: "25-34",
    contact_preference: "email",
    wellness_goals: [],
    allergies: "",
    emergency_contact_name: "",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

async function deactivateSelected(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Deactivate profile" }));
  await user.click(screen.getByRole("button", { name: "Deactivate" }));
}

describe("Admin page focus after deactivating", () => {
  beforeEach(() => {
    server.rows = [];
  });

  it("moves focus to the 'Member profiles' heading when the last matching profile disappears", async () => {
    server.rows = [profile(1, "Zara One")];
    const user = userEvent.setup();
    render(<AdminPage />);

    await user.click(await screen.findByRole("button", { name: "Active" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Zara One" })).toBeInTheDocument();

    await deactivateSelected(user);

    expect(await screen.findByText("No profiles match your search.")).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Selected profile" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: "Member profiles" })).toHaveFocus());
    expect(document.body).not.toHaveFocus();
  });

  it("moves focus to the selected profile's heading when it is still in the list", async () => {
    server.rows = [profile(1, "Zara One"), profile(2, "Zara Two")];
    const user = userEvent.setup();
    render(<AdminPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "Zara One" })).toBeInTheDocument();

    await deactivateSelected(user);

    expect(await screen.findByRole("button", { name: "Already deactivated" })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: "Zara One" })).toHaveFocus());
  });
});
