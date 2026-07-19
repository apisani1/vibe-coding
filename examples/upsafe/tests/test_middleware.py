import anyio

from upsafe.middleware import BodySizeLimitMiddleware


def _drive(max_body, request_messages, content_length=None):
    """Run the middleware over a scripted receive; return (status, bytes_reaching_app)."""
    downstream = {"bytes": 0, "called": False}
    sent = []

    async def app(scope, receive, send):
        downstream["called"] = True
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                downstream["bytes"] += len(msg.get("body", b""))
                if not msg.get("more_body"):
                    break
            else:
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    scope = {"type": "http", "method": "POST", "path": "/uploads", "headers": headers}

    messages = list(request_messages)

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(msg):
        sent.append(msg)

    mw = BodySizeLimitMiddleware(app, max_body_bytes=max_body)
    anyio.run(mw, scope, receive, send)

    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, downstream


def test_content_length_over_limit_rejected_without_reading_body():
    status, downstream = _drive(
        max_body=1000,
        request_messages=[{"type": "http.request", "body": b"x" * 5000}],
        content_length=5000,
    )
    assert status == 413
    assert downstream["called"] is False  # app never invoked; not a byte read


def test_streaming_over_limit_aborts_before_full_body_reaches_app():
    # No Content-Length (chunked): five 400-byte chunks = 2000 bytes, limit 1000.
    chunks = [{"type": "http.request", "body": b"x" * 400, "more_body": True} for _ in range(4)]
    chunks.append({"type": "http.request", "body": b"x" * 400, "more_body": False})
    status, downstream = _drive(max_body=1000, request_messages=chunks)
    assert status == 413
    # the app saw at most the chunks up to the limit, never the full 2000 bytes
    assert downstream["bytes"] <= 1000 + 400


def test_body_within_limit_passes_through():
    status, downstream = _drive(
        max_body=1000,
        request_messages=[{"type": "http.request", "body": b"x" * 500, "more_body": False}],
        content_length=500,
    )
    assert status == 200
    assert downstream["bytes"] == 500
