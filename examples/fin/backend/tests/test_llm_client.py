"""Check A4 — the tolerant parser degrades in the documented order.

Parsing is lenient; execution is not. Every action extracted here is still
re-validated by the portfolio and watchlist services, so a generous parser is
safe. What is *not* safe is a 500: a model's formatting choice must never take
down the chat panel.

These tests make no network call.
"""

from __future__ import annotations

import pytest

from finally_app.llm.client import EmptyModelResponse, LLMError, parse_response
from finally_app.llm.schema import AssistantResponse, response_format

CLEAN = (
    '{"message": "Buying now.", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}], '
    '"watchlist_changes": []}'
)
FENCED = f"```json\n{CLEAN}\n```"
PROSE_WRAPPED = f"Sure, here is my response:\n\n{CLEAN}\n\nLet me know if you want changes."
SCHEMA_VIOLATING = '{"message": "Careful there.", "trades": "not-a-list"}'
UNPARSEABLE = "I think you should probably buy some Apple stock, but I am not going to format that."


def test_clean_json_yields_typed_fields() -> None:
    result = parse_response(CLEAN)

    assert result.message == "Buying now."
    assert len(result.trades) == 1
    assert result.trades[0].ticker == "AAPL"
    assert result.trades[0].side == "buy"
    assert result.trades[0].quantity == 5


def test_fenced_json_yields_the_same_typed_fields() -> None:
    """Models that ignore response_format very often still fence their JSON."""
    assert parse_response(FENCED) == parse_response(CLEAN)


def test_json_embedded_in_prose_is_extracted() -> None:
    assert parse_response(PROSE_WRAPPED).trades[0].ticker == "AAPL"


def test_schema_violating_json_keeps_the_message_and_drops_the_actions() -> None:
    """A good answer is not thrown away because one field was malformed."""
    result = parse_response(SCHEMA_VIOLATING)

    assert result.message == "Careful there."
    assert result.trades == []
    assert result.watchlist_changes == []


def test_unparseable_prose_degrades_to_message_only() -> None:
    result = parse_response(UNPARSEABLE)

    assert result.message == UNPARSEABLE
    assert result.trades == []


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_output_raises_rather_than_inventing_a_reply(content: str | None) -> None:
    """The one case that is a genuine error: nothing came back at all."""
    with pytest.raises(LLMError):
        parse_response(content)


def test_no_input_produces_an_unhandled_exception() -> None:
    """Sweep the awkward shapes; none may raise anything but LLMError."""
    for content in ["[]", "null", "42", '{"trades": []}', "{{{", '{"message": ""}']:
        try:
            result = parse_response(content)
        except LLMError:
            continue
        assert isinstance(result, AssistantResponse)


def test_response_format_is_generated_from_the_models_and_is_strict() -> None:
    """The wire contract and the validation must not be two hand-written copies."""
    payload = response_format()

    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["strict"] is True

    schema = payload["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    # strict mode requires EVERY property listed as required, including the
    # ones Pydantic considers optional because they have defaults.
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])


def test_deeply_nested_input_does_not_escape_as_recursion_error() -> None:
    """RecursionError is not a ValueError, so it needed catching explicitly.

    Adversarial rather than likely, but the contract is that nothing escapes
    parse_response except LLMError.
    """
    try:
        result = parse_response("[" * 20000)
    except LLMError:
        return
    assert isinstance(result, AssistantResponse)


def test_empty_content_raises_the_dedicated_subclass() -> None:
    """D25: the caller must distinguish 'billed but produced nothing' from a transport failure."""
    with pytest.raises(EmptyModelResponse):
        parse_response(None)


def test_strictify_recurses_into_nested_objects() -> None:
    """A nested object node left with additionalProperties:true is rejected by the provider.

    The earlier implementation visited only $defs plus the root, which is
    correct for today's models and silently wrong for any nested object.
    """
    from finally_app.llm.schema import _strictify

    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {
                    "inner": {"type": "object", "properties": {"x": {"type": "string"}}},
                },
            },
        },
    }
    _strictify(schema)

    def every_object_node(node: object) -> list[dict[str, object]]:
        found: list[dict[str, object]] = []
        if isinstance(node, dict):
            if node.get("type") == "object":
                found.append(node)
            for value in node.values():
                found.extend(every_object_node(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(every_object_node(item))
        return found

    nodes = every_object_node(schema)
    assert len(nodes) == 3
    for node in nodes:
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node["properties"])  # type: ignore[arg-type]


def test_generated_response_format_has_no_permissive_object_node() -> None:
    """Guard the real payload, not just a synthetic fixture."""
    payload = response_format()

    def permissive(node: object) -> bool:
        if isinstance(node, dict):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                return True
            return any(permissive(v) for v in node.values())
        if isinstance(node, list):
            return any(permissive(i) for i in node)
        return False

    assert not permissive(payload["json_schema"]["schema"])
