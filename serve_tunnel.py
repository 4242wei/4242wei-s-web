from __future__ import annotations

import os

from waitress import serve

from app import app, current_port, initialize_runtime


def main() -> None:
    initialize_runtime()
    host = os.getenv("TUNNEL_HOST", "127.0.0.1")
    port = current_port()
    threads = int(os.getenv("WAITRESS_THREADS", "12"))
    connection_limit = int(os.getenv("WAITRESS_CONNECTION_LIMIT", "200"))
    channel_timeout = int(os.getenv("WAITRESS_CHANNEL_TIMEOUT", "120"))
    print(
        f"Serving tunnel origin on http://{host}:{port} "
        f"(threads={threads}, connection_limit={connection_limit}, channel_timeout={channel_timeout})"
    )
    serve(
        app,
        host=host,
        port=port,
        threads=threads,
        connection_limit=connection_limit,
        channel_timeout=channel_timeout,
        ident="stock-research-web",
    )


if __name__ == "__main__":
    main()
