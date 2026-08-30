"""The structured response contract, defined once.

The JSON Schema sent to OpenRouter is *generated from* these Pydantic models
rather than written out a second time, so the wire contract and the validation
cannot drift apart.

OpenAI-style ``strict`` mode has two requirements that shape the models below:
every property must appear in ``required``, and every object must set
``additionalProperties: false``. That is why ``trades`` and ``watchlist_changes``
are required with an empty list as the "nothing to do" value, rather than being
optional fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_ACTIONS_PER_RESPONSE = 10


class TradeAction(BaseModel):
    """A trade the assistant wants executed."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    side: Literal["buy", "sell"]
    # Constrained here as well as in the service. `json.loads` turns the model
    # text `1e400` into `inf`, and a bare float would carry it all the way to
    # the trade log; rejecting it here degrades the turn to message-only instead.
    quantity: float = Field(gt=0, allow_inf_nan=False)


class WatchlistAction(BaseModel):
    """A watchlist change the assistant wants applied."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    action: Literal["add", "remove"]


class AssistantResponse(BaseModel):
    """The complete structured reply the assistant must produce."""

    model_config = ConfigDict(extra="forbid")

    message: str
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistAction] = Field(default_factory=list)


def _strictify(node: Any) -> Any:
    """Make a Pydantic-generated schema satisfy OpenAI strict mode, recursively.

    Pydantic omits fields with defaults from ``required``; strict mode demands
    every property be listed and every object forbid extra properties.
    Rewriting the generated schema keeps a single source of truth — the
    alternative is a hand-written copy that silently diverges the first time a
    field is added.

    **Recursion is not decoration.** An earlier version visited only ``$defs``
    values plus the root, which is correct for today's two-level models and
    silently wrong for anything nested: a ``dict[str, Any]`` field would emit an
    object node with ``additionalProperties: true`` while still being listed in
    ``required``, producing a schema the provider rejects at request time. That
    failure is loud but late — a 400 at runtime, surfacing as a degraded chat
    panel in production rather than a red test here.
    """
    if isinstance(node, dict):
        if node.get("type") == "object":
            node["additionalProperties"] = False
            node["required"] = sorted(node.get("properties", {}))
        for value in node.values():
            _strictify(value)
    elif isinstance(node, list):
        for item in node:
            _strictify(item)
    return node


def response_format() -> dict[str, Any]:
    """The ``response_format`` payload for the OpenRouter request."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "assistant_response",
            "strict": True,
            "schema": _strictify(AssistantResponse.model_json_schema()),
        },
    }
