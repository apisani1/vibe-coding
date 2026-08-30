"""One-shot probe: does the configured model honour strict ``json_schema``?

This is the single sanctioned live, billable LLM call in the entire build plan
(verification-plan.md check A5, risk R1). It answers a question no offline test
can: OpenRouter's structured-output support varies by model, the model is
user-selectable, and the whole chat feature assumes typed fields come back.

**It lives in ``backend/scripts/`` and not in the package.** It is verification
tooling, and shipping it inside ``finally_app`` put a billable live-call entry
point into the runtime image — the ``Dockerfile`` copies ``backend/src`` and
nothing else, so moving it here is what actually removes it. It also leaves the
strict-typing and pylint scopes, which ``pyproject.toml`` already excludes
``scripts/`` from: a one-shot probe was being held to the standard of production
code forever, for no benefit to either.

Run once:

    cd backend && uv run python scripts/spike.py

Constraints, deliberately enforced in code rather than by discipline:

* exactly one ``acompletion`` — no retry loop, no iteration against the meter
* a bounded ``max_tokens`` and one short message
* it prints the response *body* only. LiteLLM's verbose/debug output dumps
  request headers including the ``Authorization`` bearer, and this output is
  pasted into build-log.md, which the secret scan reads at every gate.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import litellm

from finally_app.config import load_settings
from finally_app.llm.schema import AssistantResponse, response_format

MAX_TOKENS = 400

PROMPT = (
    "You are FinAlly, an AI trading assistant. The user holds 10 shares of AAPL "
    "at an average cost of $190 and $8,100 in cash. Reply with your structured "
    "JSON only. Buy 5 shares of MSFT and add PYPL to the watchlist."
)


async def _run() -> int:
    settings = load_settings()
    if not settings.llm_configured:
        print("SKIP: OPENROUTER_API_KEY and OPENROUTER_MODEL must both be set.", file=sys.stderr)
        return 2
    if settings.llm_mock:
        print("SKIP: LLM_MOCK=true. Unset it for this one command only.", file=sys.stderr)
        return 2

    print(f"model: {settings.openrouter_model}")
    print("making ONE live call...\n")

    try:
        response = await litellm.acompletion(
            model=f"openrouter/{settings.openrouter_model}",
            messages=[{"role": "user", "content": PROMPT}],
            api_key=settings.openrouter_api_key,
            response_format=response_format(),
            temperature=0.4,
            timeout=60,
            max_tokens=MAX_TOKENS,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Deliberately broad: litellm surfaces provider errors of many types and
        # this call is billed. Record whatever came back and stop -- never retry.
        print(f"CALL FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    choice = response.choices[0]
    # Dump the message object and finish_reason -- NOT headers, and not
    # litellm's verbose mode, which prints the Authorization bearer.
    print("--- FINISH REASON ---")
    print(getattr(choice, "finish_reason", "<none>"))
    print("--- MESSAGE OBJECT ---")
    try:
        print(json.dumps(choice.message.model_dump(), indent=2, default=str)[:4000])
    except Exception:  # pylint: disable=broad-exception-caught
        print(repr(choice.message)[:4000])
    print("--- END MESSAGE OBJECT ---\n")

    content: Any = choice.message.content
    print("--- RAW CONTENT ---")
    print(content)
    print("--- END RAW CONTENT ---\n")

    verdict = "IGNORED"
    try:
        parsed = json.loads(content)
        verdict = "HONOURED (content is bare JSON)"
    except (TypeError, json.JSONDecodeError):
        parsed = None
        if content and "```" in content:
            verdict = "DEGRADED (fenced JSON, not bare)"

    print(f"strict json_schema: {verdict}")
    if parsed is not None:
        try:
            validated = AssistantResponse.model_validate(parsed)
            print(
                f"schema validation: PASS — trades={len(validated.trades)} "
                f"watchlist_changes={len(validated.watchlist_changes)}"
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"schema validation: FAIL — {exc}")
    return 0


def main() -> int:
    """Entry point for ``uv run python scripts/spike.py``."""
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
