"use client";

/**
 * The conversation: transcript, in-flight state, and sending.
 *
 * Split out from the panel for the same reason as `usePortfolio` — check C7
 * asserts that a loading indicator is **present while the request is in flight
 * and gone after it resolves**, and "in flight" is only observable if the
 * request is somewhere a test can hold open.
 *
 * The transcript is loaded from the server on mount (D18). Without that, the
 * panel is blank after every reload while the rows sit in SQLite, which is the
 * gap that endpoint was added to close.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getChatMessages, sendChatMessage } from "@/lib/api";
import type { ChatAction, StoredMessage } from "@/lib/types";

export interface ChatState {
  messages: StoredMessage[];
  /** True from the moment a turn is sent until it resolves, however it resolves. */
  pending: boolean;
  error: string | null;
  /** Resolves with the actions the turn produced — empty on failure or on a plain answer. */
  send: (text: string) => Promise<ChatAction[]>;
}

export function useChat(): ChatState {
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const local = useRef(0);
  // Sequencing, for the same reason as `useWatchlist`: the mount load is a
  // round trip long, and anything the user does inside that window would be
  // erased when the older response landed. My own tests caught it — sending a
  // turn while the transcript was still loading left the transcript empty and
  // the message gone, which is the worst possible failure for a chat box.
  const generation = useRef(0);

  const reload = useCallback(async () => {
    const mine = (generation.current += 1);
    try {
      const rows = await getChatMessages();
      if (mine !== generation.current) {
        // Superseded, but the rows are still the true history: merge rather
        // than discard. Dropping them was D18 failing in exactly the race this
        // guard was added for — send during the mount load and the stored
        // conversation stayed invisible until a browser refresh, because
        // nothing calls `reload()` again.
        setMessages((current) => {
          // De-duplicated, because the two sets can overlap: if the load is
          // served *after* the POST persisted the turn, the stored rows already
          // contain what the local ones hold, and concatenating showed every
          // message twice until a refresh. Matched on role and content — the
          // ids cannot match, since the local ones are synthetic.
          const stored = new Set(rows.map((row) => [row.role, row.content].join("::")));
          const locals = current.filter(
            (message) => message.id.startsWith("local-") && !stored.has([message.role, message.content].join("::")),
          );
          return [...rows, ...locals];
        });
        return;
      }
      setMessages(rows);
      setError(null);
    } catch (caught) {
      if (mine !== generation.current) {
        return;
      }
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const send = useCallback(async (text: string): Promise<ChatAction[]> => {
    // The user's own message appears immediately rather than after the round
    // trip: a model turn can take tens of seconds, and a chat box that swallows
    // what you typed for that long looks broken. The id is synthetic — the
    // server has its own, and a reload replaces this row with it.
    // Claims the newest generation, so a transcript load still in flight cannot
    // land afterwards and delete what the user just said.
    generation.current += 1;
    local.current += 1;
    const optimistic: StoredMessage = {
      id: `local-${local.current}`,
      role: "user",
      content: text,
      actions: [],
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    setPending(true);
    setError(null);

    try {
      const turn = await sendChatMessage(text);
      setMessages((current) => [
        ...current,
        {
          id: `local-${(local.current += 1)}`,
          role: "assistant",
          content: turn.message,
          actions: turn.actions,
          created_at: new Date().toISOString(),
        },
      ]);
      return turn.actions;
    } catch (caught) {
      // The user's message stays on screen because the server kept it: the turn
      // is persisted before the model is called, so removing the bubble here
      // would contradict what a reload shows.
      setError(caught instanceof Error ? caught.message : String(caught));
      return [];
    } finally {
      setPending(false);
    }
  }, []);

  // `reload` is deliberately not returned. It is still what loads the
  // transcript on mount, but no caller outside this hook ever invoked it, and
  // an exported function nobody calls is a contract this hook has to keep
  // honouring for no one. Re-export it when something needs it.
  return { messages, pending, error, send };
}
