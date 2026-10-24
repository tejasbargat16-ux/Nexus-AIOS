"""
Nexus AIOS Daemon Entrypoint.

Starts the nexusd daemon, initializes the router, and serves the HTTP API.
Handles POSIX signals and Ctrl+C for graceful zero-data-loss termination.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from werkzeug.serving import make_server

from nexusd.api import create_app
from nexusd.audit import audit_logger
from nexusd.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nexusd")


def main() -> None:
    """Main execution entrypoint for nexusd."""
    logger.info("Initializing Nexus AIOS Daemon (Phase 1)...")

    try:
        config = load_config()
    except Exception as err:
        logger.error("Failed to load configuration: %s", err)
        sys.exit(1)

    app = create_app(config=config)
    host = config.api.host
    port = config.api.port

    logger.info("Configuration loaded. Preferred router provider: %s", config.router.prefer)
    logger.info("Binding nexusd API to http://%s:%d", host, port)

    try:
        server = make_server(host, port, app, threaded=True)
    except OSError as err:
        logger.error("Failed to bind port %d: %s", port, err)
        sys.exit(1)

    shutdown_event = threading.Event()

    def handle_shutdown(signum: int, frame: object) -> None:
        """Handle termination signals gracefully."""
        if shutdown_event.is_set():
            return
        shutdown_event.set()
        logger.info("Shutdown signal (%s) received. Stopping nexusd cleanly...", signum)
        audit_logger.log("daemon.shutdown", {"signal": signum}, status="ok")
        # Run server.shutdown in separate thread to avoid deadlock
        threading.Thread(target=server.shutdown, daemon=True).start()

    # Register signal handlers where supported
    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    audit_logger.log(
        "daemon.started",
        {"host": host, "port": port, "prefer": config.router.prefer},
        status="ok",
    )

    logger.info("nexusd is active and ready for intent requests. Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        handle_shutdown(signal.SIGINT, None)
    finally:
        logger.info("nexusd stopped.")


if __name__ == "__main__":
    main()
