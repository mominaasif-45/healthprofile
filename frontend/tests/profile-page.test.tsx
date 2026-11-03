import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Profile } from "@/lib/api";

// An in-memory stand-in for the backend: the member has one profile until DELETE removes it.
const server = vi.hoisted(() => ({ profile: null as Profile | null }));

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: vi.fn(async (path: string, opts: { method?: string } = {}) => {
      if (path === "/auth/me/") return { id: 1, email: "test.member@example.com", name: "Test Member", role: "user" };
      if (path === "/profiles/me/" && opts.method === "DELETE") {
        server.profile = null;
        return null;
      }
      if (path === "/profiles/me/") {
        if (!server.profile) throw new real.ApiError(404, "not_found", "Not found.");
        return server.profile;
      }
      throw new Error(`unexpected call ${path}`);
    }),
  };
});

// ThemeToggle needs window.matchMedia (not in jsdom) and the page needs the Next router; neither matters here.
vi.mock("@/components/Theme", () => ({ ThemeToggle: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

import ProfilePage from "@/app/profile/page";

function emptyProfile(): Profile {
  return {
    id: 1,
    status: "active",
    completion: { status: "not_started", percent: 0, missing: [] },
    demographics: null,
    emergency_contacts: [],
    wellness: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("Profile page focus after deleting the profile", () => {
  beforeEach(() => {
    server.profile = emptyProfile();
  });

  it("moves focus to the 'Create your wellness profile' heading once the profile is gone", async () => {
    const user = userEvent.setup();
    render(<ProfilePage />);

    await user.click(await screen.findByRole("button", { name: "Delete my profile" }));
    await user.type(screen.getByRole("textbox", { name: /Type DELETE to confirm/ }), "DELETE");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete my profile" }));

    expect(await screen.findByRole("button", { name: "Create my profile" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Create your wellness profile" })).toHaveFocus());
    expect(document.body).not.toHaveFocus();
  });
});
