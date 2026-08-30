import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePortfolio } from "@/hooks/usePortfolio";
import { stubApi } from "@/test/api";
import type { Portfolio } from "@/lib/types";

const ACCOUNT: Portfolio = {
  cash_balance: 10000,
  positions: [],
  positions_value: 0,
  total_value: 10000,
  unrealized_pnl: 0,
};

describe("usePortfolio", () => {
  it("fetches once on mount", async () => {
    // "Once" is the load-bearing word: check C5 counts refetches after a trade,
    // and that count means nothing if the hook also polls.
    const api = stubApi([{ match: "/api/portfolio", body: ACCOUNT }]);

    const { result } = renderHook(() => usePortfolio());

    await waitFor(() => expect(result.current.portfolio).toEqual(ACCOUNT));
    expect(api.to("/api/portfolio")).toHaveLength(1);
  });

  it("refetches exactly once per refresh() call", async () => {
    const api = stubApi([{ match: "/api/portfolio", body: ACCOUNT }]);
    const { result } = renderHook(() => usePortfolio());
    await waitFor(() => expect(api.to("/api/portfolio")).toHaveLength(1));

    await act(async () => {
      await result.current.refresh();
    });

    expect(api.to("/api/portfolio")).toHaveLength(2);
  });

  it("surfaces the server's sentence and keeps the last good portfolio on screen", async () => {
    // Stale-but-labelled beats blank: the totals were true a moment ago, and
    // wiping them turns a transient failure into an account that looks emptied.
    const api = stubApi([{ match: "/api/portfolio", body: ACCOUNT }]);
    const { result } = renderHook(() => usePortfolio());
    await waitFor(() => expect(result.current.portfolio).toEqual(ACCOUNT));

    api.serve([{ match: "/api/portfolio", status: 503, body: { detail: "database is locked" } }]);
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.error).toBe("database is locked");
    expect(result.current.portfolio).toEqual(ACCOUNT);
  });

  // The `loading` test that used to sit here went with the flag it tested. It
  // was the only reader that field ever had, which is what made it dead
  // surface: a test asserting a value nothing renders proves the value exists,
  // not that it matters.
});
