import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { uploadPolicy } from "@/lib/ml";

describe("uploadPolicy", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    document.cookie = "csrftoken=csrf-test-token";
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("posts the file as multipart form data with the session cookie and the CSRF header", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 1, title: "T", chunks: 1 }), { status: 201 }));
    const file = new File(["# T\n\nText."], "t.md", { type: "text/markdown" });
    const result = await uploadPolicy(file);
    expect(result).toMatchObject({ id: 1, title: "T" });
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/llm/v1/policies/");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["X-CSRFToken"]).toBe("csrf-test-token");
    expect(init.headers["Content-Type"]).toBeUndefined(); // the browser sets the multipart boundary itself
    expect((init.body as FormData).get("file")).toBe(file);
  });

  it("turns the error shape into an ApiError with the field messages", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      error: { code: "validation_error", message: "Invalid input.", fields: { file: ["The file is larger than 200 KB."] } },
    }), { status: 400 }));
    const err = await uploadPolicy(new File(["x"], "x.md")).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.fields.file).toEqual(["The file is larger than 200 KB."]);
  });
});
