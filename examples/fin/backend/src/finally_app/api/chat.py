"""Chat endpoints: send a turn, read the transcript.

``async def`` here, unlike every other router in this application, because the
handler awaits an LLM call that can take tens of seconds. On the threadpool that
would occupy a worker thread for the whole request; on the loop it costs
nothing, and the database work underneath still runs in ``services/`` the same
way (D21).

**A rejected action is not an error.** The one status code worth stating
explicitly: a trade the assistant asked for and the portfolio refused returns
**200** with the rejection recorded in ``actions`` (D6). The model answered; the
user needs to see what it tried and why it failed. A 4xx would replace that with
a generic failure banner and lose the reason.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..llm.client import LLMError, LLMNotConfigured
from ..services import chat

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    """The wire shape of a turn."""

    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)]


@router.post("")
async def send_message(payload: ChatRequest, request: Request) -> chat.ChatTurn:
    """Send one message; get the reply and every action it caused.

    The rate check is **first**, before anything is persisted. A refusal that
    happened after the user's turn was written would leave the transcript
    holding a message the assistant was never asked about — the same orphan
    shape the 503 path had.
    """
    wait = request.app.state.chat_limiter.take()
    if wait > 0:
        # 429 and a Retry-After the client can act on. Each of these is one
        # billed completion, so this is a spend limit rather than load shedding,
        # and it is the only route in the application that has one.
        raise HTTPException(
            status_code=429,
            detail=f"Too many messages. Please wait about {max(1, round(wait))}s and try again.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )

    try:
        return await chat.handle_message(
            request.app.state.settings.db_path,
            request.app.state.cache,
            request.app.state.settings,
            payload.message,
        )
    except LLMNotConfigured as exc:
        # 503 is right here and only here: the service genuinely cannot do this
        # until someone sets a variable. The message names which one.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        # Transport failure — the model was unreachable, so "try again later" is
        # honest. EmptyModelResponse never reaches this: it is a 200 with an
        # apology, handled in the service (D25).
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/messages")
def read_messages(request: Request, limit: int = Query(default=100, ge=1, le=1000)) -> list[chat.StoredMessage]:
    """The stored conversation, oldest last (D18).

    Without this the panel is blank after every reload while the rows sit in
    SQLite unreachable.
    """
    return chat.list_messages(request.app.state.settings.db_path, limit)
