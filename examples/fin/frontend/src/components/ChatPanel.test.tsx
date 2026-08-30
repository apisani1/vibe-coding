import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel, describeAction, MAX_MESSAGE_LENGTH, verdictOf } from "@/components/ChatPanel";
import { stubApi } from "@/test/api";
import type { ChatAction, StoredMessage } from "@/lib/types";

const FILLED: ChatAction = {
  type: "trade",
  ticker: "AAPL",
  side: "buy",
  quantity: 5,
  status: "filled",
  price: 190.5,
};

const REJECTED: ChatAction = {
  type: "trade",
  ticker: "AAPL",
  side: "buy",
  quantity: 600,
  status: "rejected",
  reason: "Insufficient cash: need $114,300.00, have $10,000.00",
};

function stored(overrides: Partial<StoredMessage> & { id: string; role: string; content: string }): StoredMessage {
  return { actions: [], created_at: "2026-08-16T12:00:00Z", ...overrides };
}

async function mount(onActions?: (actions: ChatAction[]) => void) {
  await act(async () => {
    render(<ChatPanel onActions={onActions} />);
  });
}

async function ask(text: string) {
  await act(async () => {
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: text } });
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!);
  });
}

describe("the transcript (check C7)", () => {
  it("loads the stored conversation on mount", async () => {
    // D18. Without this the panel is blank after every reload while the rows
    // sit in SQLite — the gap that endpoint exists to close.
    const api = stubApi([
      {
        match: "/api/chat/messages",
        body: [
          stored({ id: "1", role: "user", content: "how am I doing?" }),
          stored({ id: "2", role: "assistant", content: "Up $120 today." }),
        ],
      },
    ]);

    await mount();

    expect(api.to("/api/chat/messages")).toHaveLength(1);
    expect(screen.getByText("how am I doing?")).toBeInTheDocument();
    expect(screen.getByText("Up $120 today.")).toBeInTheDocument();
  });

  it("shows an empty state rather than a blank panel", async () => {
    stubApi([{ match: "/api/chat/messages", body: [] }]);

    await mount();

    expect(screen.getByTestId("chat-empty")).toBeInTheDocument();
  });

  it("renders actions stored against an earlier turn, not only ones from this session", async () => {
    // The reload path carries actions too; a panel that rendered them only from
    // the live response would lose every outcome across a refresh.
    stubApi([
      {
        match: "/api/chat/messages",
        body: [stored({ id: "1", role: "assistant", content: "Done.", actions: [FILLED, REJECTED] })],
      },
    ]);

    await mount();

    expect(screen.getByTestId("chat-action-done")).toBeInTheDocument();
    expect(screen.getByTestId("chat-action-rejected")).toBeInTheDocument();
  });
});

describe("the loading indicator (check C7)", () => {
  it("is present while the turn is in flight and gone once it resolves", async () => {
    // Both halves, and the gate is what makes the first half observable: with
    // every fetch settling inside one act() flush there is no "while".
    let release: () => void = () => {};
    const inFlight = new Promise<void>((resolve) => {
      release = resolve;
    });
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "Bought.", actions: [] }, gate: inFlight },
    ]);
    await mount();

    await ask("buy 5 AAPL");
    expect(screen.getByTestId("chat-pending")).toBeInTheDocument();

    await act(async () => {
      release();
    });

    expect(screen.queryByTestId("chat-pending")).not.toBeInTheDocument();
  });

  it("shows the user's message immediately, before the answer arrives", async () => {
    // A model turn can take tens of seconds. A box that swallows what you typed
    // for that long reads as broken.
    let release: () => void = () => {};
    const inFlight = new Promise<void>((resolve) => {
      release = resolve;
    });
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "Done.", actions: [] }, gate: inFlight },
    ]);
    await mount();

    await ask("buy 5 AAPL");

    expect(screen.getByText("buy 5 AAPL")).toBeInTheDocument();

    await act(async () => {
      release();
    });
  });

  it("refuses to send a second turn while one is in flight", async () => {
    let release: () => void = () => {};
    const inFlight = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "Done.", actions: [] }, gate: inFlight },
    ]);
    await mount();

    await ask("first");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await act(async () => {
      release();
    });
    expect(api.calls.filter((call) => call.method === "POST")).toHaveLength(1);
  });
});

describe("both outcomes are rendered (check C7, D6)", () => {
  it("renders a filled action as a confirmation carrying the fill price", async () => {
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "Bought them.", actions: [FILLED] } },
    ]);
    await mount();

    await ask("buy 5 AAPL");

    const chip = screen.getByTestId("chat-action-done");
    expect(chip).toHaveTextContent("Bought 5 AAPL @ $190.50");
  });

  it("renders a rejected action with the server's reason", async () => {
    // The whole of D6. A panel that showed only `filled` actions would let the
    // assistant's "I bought 600 shares" stand while the portfolio refused it —
    // exactly the failure the outcome model exists to prevent.
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "I tried to buy 600.", actions: [REJECTED] } },
    ]);
    await mount();

    await ask("buy 600 AAPL");

    expect(screen.getByTestId("chat-action-rejected")).toHaveTextContent(
      "Insufficient cash: need $114,300.00, have $10,000.00",
    );
  });

  it("renders both when one turn produced each", async () => {
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "One of two went through.", actions: [FILLED, REJECTED] } },
    ]);
    await mount();

    await ask("buy 5 AAPL and 600 MSFT");

    expect(screen.getByTestId("chat-action-done")).toBeInTheDocument();
    expect(screen.getByTestId("chat-action-rejected")).toBeInTheDocument();
  });

  it("describes watchlist changes as applied, not filled", async () => {
    expect(describeAction({ type: "watchlist", ticker: "NVDA", action: "add", status: "applied" })).toBe("Added NVDA");
    expect(describeAction({ type: "watchlist", ticker: "NVDA", action: "remove", status: "applied" })).toBe(
      "Removed NVDA",
    );
  });

  it("names the verdict the user reads to know whether it happened", async () => {
    // The word was pinned by nothing: replacing it with a constant "Filled"
    // survived all 164 tests, because the assertions checked the testid and the
    // reason sentence. A refused trade reading "Filled Insufficient cash…" is
    // the D6 failure in one word.
    expect(verdictOf(REJECTED)).toBe("Rejected");
    expect(verdictOf(FILLED)).toBe("Filled");
    expect(verdictOf({ type: "watchlist", ticker: "NVDA", action: "add", status: "applied" })).toBe("Applied");
  });

  it("renders that verdict in the chip", async () => {
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "No.", actions: [REJECTED] } },
    ]);
    await mount();

    await ask("buy 600 AAPL");

    expect(screen.getByTestId("chat-action-rejected")).toHaveTextContent(/^Rejected/);
  });

  it("describes a sell as sold", async () => {
    expect(describeAction({ ...FILLED, side: "sell" })).toBe("Sold 5 AAPL @ $190.50");
  });
});

describe("telling the rest of the page what happened", () => {
  it("reports actions that changed something", async () => {
    // The assistant trades through the same service functions a person does
    // (D5), so the account and the watchlist have to be re-read.
    const onActions = vi.fn();
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "Bought.", actions: [FILLED] } },
    ]);
    await mount(onActions);

    await ask("buy 5 AAPL");

    expect(onActions).toHaveBeenCalledTimes(1);
    expect(onActions).toHaveBeenCalledWith([FILLED]);
  });

  it("stays quiet when the turn only answered a question", async () => {
    const onActions = vi.fn();
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "You are up $120.", actions: [] } },
    ]);
    await mount(onActions);

    await ask("how am I doing?");

    expect(onActions).not.toHaveBeenCalled();
  });

  it("stays quiet when every action was refused", async () => {
    // A rejection changed nothing. Refetching would report movement that did
    // not happen — the same rule the trade bar follows.
    const onActions = vi.fn();
    stubApi([
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: { message: "I could not.", actions: [REJECTED] } },
    ]);
    await mount(onActions);

    await ask("buy 600 AAPL");

    expect(onActions).not.toHaveBeenCalled();
  });
});

describe("when the model cannot be reached", () => {
  it("shows the server's sentence and keeps the message the server already stored", async () => {
    // `handle_message` persists the user's turn before calling the model, so
    // removing the bubble here would contradict what a reload shows.
    stubApi([
      { match: "/api/chat/messages", body: [] },
      {
        match: "/api/chat",
        method: "POST",
        status: 503,
        body: { detail: "OPENROUTER_API_KEY is not set" },
      },
    ]);
    await mount();

    await ask("buy 5 AAPL");

    await waitFor(() => expect(screen.getByTestId("chat-error")).toHaveTextContent("OPENROUTER_API_KEY is not set"));
    expect(screen.getByText("buy 5 AAPL")).toBeInTheDocument();
    expect(screen.queryByTestId("chat-pending")).not.toBeInTheDocument();
  });
});

describe("the panel itself", () => {
  it("collapses and expands", async () => {
    stubApi([{ match: "/api/chat/messages", body: [] }]);
    await mount();

    const toggle = screen.getByRole("button", { name: /assistant/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    act(() => {
      toggle.click();
    });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
  });

  it("will not send an empty or whitespace-only message", async () => {
    const api = stubApi([{ match: "/api/chat/messages", body: [] }]);
    await mount();

    await ask("   ");

    expect(api.calls.filter((call) => call.method === "POST")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("the input", () => {
  it("carries the server's own length cap", async () => {
    // The mirror of this run's standing condition. A cap the client does not
    // know about becomes a 422 with the user's text already cleared from the
    // box, because the box is cleared on submit.
    stubApi([{ match: "/api/chat/messages", body: [] }]);
    await mount();

    expect(screen.getByLabelText("Message")).toHaveAttribute("maxLength", String(MAX_MESSAGE_LENGTH));
  });

  it("uses the same cap the API declares", () => {
    const source = readFileSync(resolve(process.cwd(), "../backend/src/finally_app/api/chat.py"), "utf8");

    const declared = Number(source.match(/MAX_MESSAGE_LENGTH = (\d+)/)![1]);

    expect(MAX_MESSAGE_LENGTH).toBe(declared);
  });
});
