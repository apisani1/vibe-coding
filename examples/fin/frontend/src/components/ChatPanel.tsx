"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@/hooks/useChat";
import { formatMoney } from "@/lib/format";
import type { ChatAction, StoredMessage } from "@/lib/types";

/**
 * The assistant panel: transcript, input, and what the assistant actually did.
 *
 * **Both outcomes are rendered, and that is the point** (D6). A panel that
 * shows only `filled` actions reproduces precisely the failure the whole
 * outcome model exists to prevent: the assistant says "I bought 60 shares", the
 * portfolio refused it for insufficient cash, and the user believes the
 * sentence. A rejection is not an error to be swallowed — it is what happened,
 * and it carries the same reason the REST API would have returned as `detail`.
 */

/**
 * `api/chat.py`'s `ChatRequest.message` cap, mirrored here.
 *
 * A boundary rule enforced only in a Pydantic model is invisible to every
 * non-HTTP caller — this run's standing condition — and the mirror image holds
 * too: a cap the *client* does not know about turns into a 422 with the user's
 * text already cleared from the box.
 */
export const MAX_MESSAGE_LENGTH = 4000;

/** One action, in a sentence a person can check against their portfolio. */
export function describeAction(action: ChatAction): string {
  if (action.status === "rejected") {
    return action.reason ?? "Rejected";
  }
  if (action.type === "trade") {
    const verb = action.side === "sell" ? "Sold" : "Bought";
    const at = action.price === undefined ? "" : ` @ ${formatMoney(action.price)}`;
    return `${verb} ${action.quantity ?? ""} ${action.ticker}${at}`.replace(/\s+/g, " ").trim();
  }
  return `${action.action === "remove" ? "Removed" : "Added"} ${action.ticker}`;
}

/** The one word that tells the user whether it happened. Exported so a test can name it. */
export function verdictOf(action: ChatAction): "Rejected" | "Filled" | "Applied" {
  if (action.status === "rejected") {
    return "Rejected";
  }
  return action.type === "trade" ? "Filled" : "Applied";
}

function ActionChip({ action }: { action: ChatAction }) {
  const rejected = action.status === "rejected";

  return (
    <li
      data-testid={`chat-action-${rejected ? "rejected" : "done"}`}
      className={`rounded border px-2 py-1 text-xs ${
        rejected ? "border-down/50 bg-down/10 text-down" : "border-up/50 bg-up/10 text-up"
      }`}
    >
      <span className="font-semibold">{verdictOf(action)}</span> {describeAction(action)}
    </li>
  );
}

function Bubble({ message }: { message: StoredMessage }) {
  const mine = message.role === "user";

  return (
    <li className={`flex flex-col gap-1 ${mine ? "items-end" : "items-start"}`} data-testid={`chat-${message.role}`}>
      <div
        className={`max-w-[90%] whitespace-pre-wrap rounded px-2 py-1 text-sm ${
          mine ? "bg-accent-blue/20 text-terminal-text" : "bg-terminal-border/40 text-terminal-text"
        }`}
      >
        {message.content}
      </div>
      {message.actions.length > 0 && (
        <ul className="flex max-w-[90%] flex-col gap-1">
          {message.actions.map((action, index) => (
            <ActionChip key={`${message.id}-${index}`} action={action} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ChatPanel({ onActions }: { onActions?: (actions: ChatAction[]) => void }) {
  const { messages, pending, error, send } = useChat();
  const [draft, setDraft] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Follow the conversation. `?.` because jsdom has no layout and no
    // `scrollIntoView` in some configurations — a missing scroll must not take
    // the panel down.
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages, pending]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (text.length === 0 || pending) {
      return;
    }
    // Cleared immediately, unlike the trade bar and the ticker box: the message
    // is already on screen as a bubble, so keeping it in the input would show it
    // twice. For the modelled failures that is safe — `handle_message` persists
    // the user's turn *before* calling the model, so a 503 still leaves the row
    // in SQLite. It is not safe for a request that never reached the handler,
    // which is why the input carries the server's own length cap below rather
    // than discovering it as a 422 with the text already gone.
    setDraft("");
    const actions = await send(text);
    // Only when something actually happened. A turn that answered a question,
    // or one whose every action was refused, changed nothing — refetching then
    // would report movement that did not occur.
    if (actions.some((action) => action.status !== "rejected")) {
      onActions?.(actions);
    }
  }

  return (
    <div className="flex min-h-0 flex-col" data-testid="chat-panel">
      <button
        type="button"
        onClick={() => setCollapsed((current) => !current)}
        aria-expanded={!collapsed}
        className="flex items-center justify-between px-3 py-1 text-xs uppercase tracking-wider text-terminal-muted hover:text-terminal-text"
      >
        <span>Assistant</span>
        <span aria-hidden="true">{collapsed ? "▸" : "▾"}</span>
      </button>

      {!collapsed && (
        <>
          <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto px-3 py-2" data-testid="chat-transcript">
            {messages.length === 0 && !pending && (
              <li className="text-sm text-terminal-muted" data-testid="chat-empty">
                Ask about your portfolio, or tell me what to trade.
              </li>
            )}
            {messages.map((message) => (
              <Bubble key={message.id} message={message} />
            ))}
            {pending && (
              <li className="text-sm text-terminal-muted" data-testid="chat-pending" role="status">
                Thinking…
              </li>
            )}
            <div ref={end} />
          </ul>

          {error && (
            <p role="alert" className="px-3 pb-1 text-xs text-down" data-testid="chat-error">
              {error}
            </p>
          )}

          <form onSubmit={submit} className="flex items-center gap-2 border-t border-terminal-border px-3 py-2">
            <input
              aria-label="Message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={MAX_MESSAGE_LENGTH}
              placeholder="Buy 10 AAPL"
              className="w-full rounded border border-terminal-border bg-terminal-bg px-2 py-1 text-terminal-text"
            />
            <button
              type="submit"
              disabled={pending || draft.trim().length === 0}
              className="rounded bg-accent-purple px-3 py-1 text-xs font-semibold text-white disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </>
      )}
    </div>
  );
}
