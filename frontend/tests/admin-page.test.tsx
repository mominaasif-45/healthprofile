import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdminRow } from "@/lib/api";

// An in-memory stand-in for the backend: the list endpoint filters by status, deactivate/reactivate flip one row.
const server = vi.hoisted(() => ({ rows: [] as AdminRow[] }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: vi.fn(async (path: string) => {
    const change = path.match(/^\/admin\/profiles\/(\d+)\/(deactivate|reactivate)\/$/);
    if (change) {
      const row = server.rows.find((r) => r.id === Number(change[1]))!;
      row.status = change[2] === "deactivate" ? "deactivated" : "active";
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

function profile(id: number, display_name: string, status: AdminRow["status"] = "active"): AdminRow {
  return {
    id,
    display_name,
    email: `${display_name.split(" ")[0].toLowerCase()}@example.com`,
    status,
    completion_status: "complete",
    completion_percent: 100,
    created_at: "2026-01-01T00:00:00Z",
  };
}

async function confirmChange(user: ReturnType<typeof userEvent.setup>, action: "Deactivate" | "Reactivate") {
  await user.click(screen.getByRole("button", { name: `${action} profile` }));
  await user.click(screen.getByRole("button", { name: action }));
}

const pageHeading = () => screen.getByRole("heading", { level: 1, name: "Member profiles" });

describe("Admin page focus after a status change", () => {
  beforeEach(() => {
    server.rows = [];
  });

  it("moves focus to the 'Member profiles' heading when deactivating the last active profile", async () => {
    server.rows = [profile(1, "Zara One")];
    const user = userEvent.setup();
    render(<AdminPage />);

    await user.click(await screen.findByRole("button", { name: "Active" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Zara One" })).toBeInTheDocument();

    await confirmChange(user, "Deactivate");

    expect(await screen.findByText("No profiles match your filters.")).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Selected profile" })).not.toBeInTheDocument();
    await waitFor(() => expect(pageHeading()).toHaveFocus());
    expect(document.body).not.toHaveFocus();
  });

  it("moves focus to the 'Member profiles' heading when reactivating the last deactivated profile", async () => {
    server.rows = [profile(1, "Zara One", "deactivated")];
    const user = userEvent.setup();
    render(<AdminPage />);

    await user.click(await screen.findByRole("button", { name: "Deactivated" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Zara One" })).toBeInTheDocument();

    await confirmChange(user, "Reactivate");

    expect(await screen.findByText("No profiles match your filters.")).toBeInTheDocument();
    await waitFor(() => expect(pageHeading()).toHaveFocus());
    expect(document.body).not.toHaveFocus();
  });

  it("moves focus to the selected profile's heading when it is still in the list", async () => {
    server.rows = [profile(1, "Zara One"), profile(2, "Zara Two")];
    const user = userEvent.setup();
    render(<AdminPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "Zara One" })).toBeInTheDocument();

    await confirmChange(user, "Deactivate");

    expect(await screen.findByRole("button", { name: "Reactivate profile" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: "Zara One" })).toHaveFocus());
  });
});
