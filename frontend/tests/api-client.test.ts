import { describe, expect, it, vi, beforeEach } from "vitest";
import { apiRequest, ApiError } from "@/lib/api/client";

describe("apiRequest", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed JSON when response is ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: "ok" }),
      })
    );

    const result = await apiRequest<{ status: string }>("/health");
    expect(result.status).toBe("ok");
  });

  it("throws ApiError with detail when request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: "Not found" }),
      })
    );

    await expect(apiRequest("/missing")).rejects.toBeInstanceOf(ApiError);
    await expect(apiRequest("/missing")).rejects.toMatchObject({
      status: 404,
      message: "Not found",
    });
  });
});
