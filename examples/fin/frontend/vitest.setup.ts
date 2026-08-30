import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

/**
 * No component test may reach the network.
 *
 * The same rule the backend suite enforces at the socket layer (check B7), one
 * level up: Node 20+ ships a real `fetch`, so a component that forgets its stub
 * would issue a genuine request — passing on a developer's machine, hanging in
 * CI, and quietly depending on whatever is listening on port 8000. Re-installed
 * before every test so one test's `vi.stubGlobal("fetch", …)` cannot leak into
 * the next and make it look stubbed when it is not.
 */
beforeEach(() => {
  vi.stubGlobal("fetch", () => {
    throw new Error("BLOCKED: a test attempted a real network request — stub fetch for this test");
  });
  // `EventSource` for the same reason, and one more: jsdom does not implement
  // it at all, so an unstubbed test would fail with a bare `ReferenceError` —
  // an accident that happens to stop the request rather than a guard that says
  // why. This makes the message say why.
  vi.stubGlobal(
    "EventSource",
    class {
      constructor() {
        throw new Error("BLOCKED: a test opened an EventSource — stub it for this test");
      }
    },
  );
});
