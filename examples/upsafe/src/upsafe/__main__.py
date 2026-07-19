"""Run the service: ``python -m upsafe`` (or the ``upsafe`` console script).

Configuration comes from the environment (see ``config.load_settings``). Host/port are
read here so deployment does not require code changes.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "upsafe.app:create_app",
        factory=True,
        host=os.environ.get("UPSAFE_HOST", "127.0.0.1"),
        port=int(os.environ.get("UPSAFE_PORT", "8000")),
        # Uvicorn's default access log records the full request line, including
        # /downloads/<token> — which would leak the download capability (contra D8).
        # The app's own redacting logger (logging.log_request) covers observability.
        access_log=False,
    )


if __name__ == "__main__":
    main()
