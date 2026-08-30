import { describe, expect, it, vi } from "vitest";
import { ApiError, getPortfolio, removeTicker, trade } from "./api";

/** A `fetch` returning one canned response, recording what it was called with. */
function stubFetch(status: number, body: string, contentType = "application/json") {
  const calls: Array<[string, RequestInit | undefined]> = [];
  const fetchStub = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push([url, init]);
    // `null`, not `""`: the Response constructor rejects a body-carrying 204,
    // which is the same rule the browser enforces on the real DELETE.
    return new Response(body === "" ? null : body, { status, headers: { "Content-Type": contentType } });
  });
  vi.stubGlobal("fetch", fetchStub);
  return calls;
}

describe("request", () => {
  it("parses a successful response and calls the same-origin path", async () => {
    const calls = stubFetch(200, JSON.stringify({ cash_balance: 10000, positions: [] }));

    const portfolio = await getPortfolio();

    expect(portfolio.cash_balance).toBe(10000);
    expect(calls[0][0]).toBe("/api/portfolio");
  });

  it("surfaces the server's detail sentence, not a generic status message", async () => {
    // The exact sentence services/portfolio.py writes. It names the numbers the
    // user needs; "Request failed (400)" does not.
    stubFetch(400, JSON.stringify({ detail: "Insufficient cash: need $12,000.00, have $10,000.00" }));

    await expect(trade("AAPL", "buy", 60)).rejects.toMatchObject({
      status: 400,
      message: "Insufficient cash: need $12,000.00, have $10,000.00",
    });
  });

  it("joins the messages of a Pydantic 422, whose detail is a list rather than a string", async () => {
    stubFetch(422, JSON.stringify({ detail: [{ msg: "String should match pattern" }, { msg: "Input should be > 0" }] }));

    await expect(trade("!!", "buy", 1)).rejects.toThrow("String should match pattern; Input should be > 0");
  });

  it("names the cause when the body is HTML rather than JSON", async () => {
    // The R3 failure mode: a static export mounted ahead of the API routers
    // answers unknown /api paths with the shell and a 200. Without this branch
    // the caller sees "Unexpected token '<'", which points at nothing.
    stubFetch(200, "<!DOCTYPE html><html></html>", "text/html");

    await expect(getPortfolio()).rejects.toThrow(/shadowed by the static export/);
  });

  it("treats 204 as success rather than trying to parse an empty body", async () => {
    stubFetch(204, "");

    await expect(removeTicker("AAPL")).resolves.toBeUndefined();
  });

  it("throws ApiError carrying the status", async () => {
    stubFetch(404, JSON.stringify({ detail: "'ZZZZ' is not on the watchlist" }));

    const error = await removeTicker("ZZZZ").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
  });
});
