import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChat } from "@/hooks/useChat";
import { stubApi } from "@/test/api";

const TURN = { message: "Bought them.", actions: [{ type: "trade", ticker: "AAPL", status: "filled" }] };

describe("useChat", () => {
  it("loads the transcript once on mount", async () => {
    const api = stubApi([{ match: "/api/chat/messages", body: [] }]);

    renderHook(() => useChat());

    await waitFor(() => expect(api.to("/api/chat/messages")).toHaveLength(1));
  });

  it("appends the user's message before the request and the reply after it", async () => {
    let release: () => void = () => {};
    const inFlight = new Promise<void>((resolve) => {
      release = resolve;
    });
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: TURN, gate: inFlight },
    ]);
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.messages).toEqual([]));

    let sending: Promise<unknown> | undefined;
    await act(async () => {
      sending = result.current.send("buy 5 AAPL");
    });

    expect(result.current.messages.map((message) => message.role)).toEqual(["user"]);
    expect(result.current.pending).toBe(true);

    await act(async () => {
      release();
      await sending;
    });

    expect(result.current.messages.map((message) => message.role)).toEqual(["user", "assistant"]);
    expect(result.current.pending).toBe(false);
  });

  it("resolves with the actions the turn produced", async () => {
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: TURN },
    ]);
    const { result } = renderHook(() => useChat());

    let actions: unknown;
    await act(async () => {
      actions = await result.current.send("buy 5 AAPL");
    });

    expect(actions).toEqual(TURN.actions);
  });

  it("resolves with nothing and records the reason when the turn fails", async () => {
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", status: 503, body: { detail: "Could not reach the model" } },
    ]);
    const { result } = renderHook(() => useChat());

    let actions: unknown;
    await act(async () => {
      actions = await result.current.send("buy 5 AAPL");
    });

    expect(actions).toEqual([]);
    expect(result.current.error).toBe("Could not reach the model");
    // The server persisted the turn before calling the model, so the bubble
    // stays: removing it would contradict what a reload shows.
    expect(result.current.messages.map((message) => message.content)).toEqual(["buy 5 AAPL"]);
    expect(result.current.pending).toBe(false);
  });

  it("gives every optimistic message a distinct id", async () => {
    // Two turns in a session must not collide, or React reuses one row for the
    // other and the transcript loses a message.
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: TURN },
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.send("one");
    });
    await act(async () => {
      await result.current.send("two");
    });

    const ids = result.current.messages.map((message) => message.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toHaveLength(4);
  });

  it("surfaces a failed transcript load", async () => {
    stubApi([{ match: "/api/chat/messages", status: 503, body: { detail: "database is locked" } }]);
    const { result } = renderHook(() => useChat());

    await waitFor(() => expect(result.current.error).toBe("database is locked"));
  });
});

describe("a send during the mount load", () => {
  it("does not show the turn twice when the load already contains it", async () => {
    // The merge's own defect, found by the overseer: if the transcript GET is
    // served after the POST has persisted the turn, the stored rows already
    // hold what the optimistic ones do, and a blind concatenation rendered
    // every message twice until a browser refresh.
    //
    // The gated route carries the stored rows **up front**. My first attempt
    // gated an empty list and swapped in the rows with `serve()` afterwards —
    // but an in-flight request holds the route object it matched, so it still
    // answered `[]` and the test passed under the very implementation it was
    // written to reject.
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    stubApi([
      {
        match: "/api/chat/messages",
        gate: slow,
        body: [
          { id: "s1", role: "user", content: "today's question", actions: [], created_at: "2026-08-16T12:00:00Z" },
          {
            id: "s2",
            role: "assistant",
            content: TURN.message,
            actions: TURN.actions,
            created_at: "2026-08-16T12:00:01Z",
          },
        ],
      },
      { match: "/api/chat", method: "POST", body: TURN },
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.send("today's question");
    });

    await act(async () => {
      release();
    });

    expect(result.current.messages.map((message) => message.content)).toEqual(["today's question", TURN.message]);
  });

  it("keeps the stored history as well as the new message", async () => {
    // The generation guard stopped the load from erasing the user's bubble but
    // then dropped the load entirely, so the stored conversation stayed
    // invisible until a browser refresh — D18 failing in the very race the
    // guard was written for. Superseded loads merge now.
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    const stored = [
      { id: "s1", role: "user", content: "yesterday's question", actions: [], created_at: "2026-08-15T12:00:00Z" },
      { id: "s2", role: "assistant", content: "yesterday's answer", actions: [], created_at: "2026-08-15T12:00:01Z" },
    ];
    stubApi([
      { match: "/api/chat/messages", body: stored, gate: slow },
      { match: "/api/chat", method: "POST", body: TURN },
    ]);
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.send("today's question");
    });

    await act(async () => {
      release();
    });

    expect(result.current.messages.map((message) => message.content)).toEqual([
      "yesterday's question",
      "yesterday's answer",
      "today's question",
      TURN.message,
    ]);
  });
});
