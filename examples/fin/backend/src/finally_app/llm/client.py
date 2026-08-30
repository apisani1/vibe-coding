"""LiteLLM -> OpenRouter, with a deliberately tolerant parser.

Parsing is lenient; execution is not. Anything extracted here is still
re-validated by the same service functions a manual action goes through, so a
generous parser cannot turn into a privileged write path.

That sentence was **false for quantity** until CP9 review: the finite-and-
positive rule lived in ``api/``'s ``TradeRequest``, which the chat path never
constructs, so a model-authored ``-5`` filled and credited cash. The rule now
lives in ``portfolio.execute_trade``, where both callers cross it — which is what
makes the invariant above testable rather than aspirational.

The request names a model and nothing else — no ``provider.order``, no
``allow_fallbacks: false``. Pinning one inference provider buys latency at the
cost of a hard outage whenever that provider drops the model, and it conflicts
with a user-selectable ``OPENROUTER_MODEL``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import litellm
from pydantic import ValidationError

from ..config import Settings
from .schema import AssistantResponse, response_format

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 60
TEMPERATURE = 0.4

# What the user is told when the call fails, verbatim and always. The provider's
# own exception text is NOT interpolated: api/chat.py returns this as the 503
# `detail` and the chat panel renders it, and the shape of a third-party
# exception string is not under this repository's control — it has embedded a
# request URL before (that is how the Massive key nearly reached the logs), and
# nothing stops the next version embedding a header. The exception is not lost;
# it goes to `logger.exception` one line above, which is where an operator
# looks and a user does not.
UNREACHABLE_MESSAGE = "Could not reach the model. Please try again in a moment."
UNUSABLE_ENVELOPE_MESSAGE = "The model returned a response that could not be read."

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMError(Exception):
    """The model could not be reached, or its reply could not be understood."""


class LLMNotConfigured(LLMError):
    """No API key or no model id — the chat endpoint reports this as a 503."""


class EmptyModelResponse(LLMError):
    """The model returned no content at all.

    Its own subclass because the caller must handle it differently from a
    transport failure: the call *succeeded* and was billed, the model simply
    produced nothing usable. D25 requires the chat endpoint to answer 200 with
    an apology rather than 503, since retrying will not help.
    """


def _candidates(content: str) -> list[str]:
    """Yield decreasingly-literal readings of the model's output.

    Ordered from most to least trusting: the raw text, then any fenced block,
    then the outermost brace-delimited span. Support for ``response_format``
    varies across OpenRouter's catalogue and the model is user-selectable, so
    the client cannot assume the best case.
    """
    out = [content.strip()]
    out.extend(match.strip() for match in _FENCE.findall(content))
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        out.append(content[start : end + 1])
    return [c for c in out if c]


def parse_response(content: str | None) -> AssistantResponse:
    """Turn raw model output into a validated response.

    Raises ``LLMError`` for exactly one condition — nothing usable came back at
    all. Every other malformation degrades: an unreadable reply becomes a
    message-only response carrying the raw text, because a 500 in the chat
    endpoint would take down a panel over a model's formatting choice.

    The empty case is genuinely different from the malformed case: there is no
    message to show, so there is nothing to degrade *to*. It is real and not
    theoretical — a reasoning model can spend its whole ``max_tokens`` budget on
    reasoning and return ``content: null`` with ``finish_reason: length``
    (observed once during the CP2 spike). See ``decisions.md`` D25: the caller
    is responsible for turning this into a 200 with an apology, not a 500.
    """
    if not content or not content.strip():
        raise EmptyModelResponse("The model returned no content")

    for candidate in _candidates(content):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError, RecursionError):
            # RecursionError is not a subclass of ValueError: deeply nested
            # input such as "[" * 20000 blows the decoder's stack, and without
            # this it would escape as something other than LLMError.
            continue
        if not isinstance(data, dict):
            continue
        try:
            return AssistantResponse.model_validate(data)
        except ValidationError:
            # Parsed as JSON but did not match the contract. If there is at
            # least a message, keep it and drop the actions rather than
            # discarding a perfectly good answer.
            message = data.get("message")
            if isinstance(message, str) and message.strip():
                logger.warning("model returned JSON that violates the schema; keeping message, dropping actions")
                return AssistantResponse(message=message)
            continue

    logger.warning("model returned no usable JSON; falling back to raw text as the message")
    return AssistantResponse(message=content.strip())


async def complete(settings: Settings, messages: list[dict[str, str]]) -> AssistantResponse:
    """Make one structured-output call and validate the result."""
    if not settings.llm_configured:
        missing = "OPENROUTER_API_KEY" if not settings.openrouter_api_key else "OPENROUTER_MODEL"
        raise LLMNotConfigured(f"{missing} is not set")

    try:
        response = await litellm.acompletion(
            model=f"openrouter/{settings.openrouter_model}",
            messages=messages,
            api_key=settings.openrouter_api_key,
            response_format=response_format(),
            temperature=TEMPERATURE,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # litellm raises a wide variety of provider errors
        logger.exception("LLM call failed")
        raise LLMError(UNREACHABLE_MESSAGE) from exc

    # Reading the choice is inside its own guard: litellm preserves an empty
    # `choices` list as-is, so a provider returning {"choices": []} would raise
    # IndexError and escape as a 500 — exactly what this module forbids.
    try:
        content: Any = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        logger.exception("unusable response envelope from the model")
        raise LLMError(UNUSABLE_ENVELOPE_MESSAGE) from exc

    return parse_response(content if isinstance(content, str) else None)
