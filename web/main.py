"""NetScope web — PyWebView launcher (starts uvicorn + opens native window)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_ROOT)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765

try:
    from core.version import read_version as _read_version
except ImportError:  # pragma: no cover - cwd edge case
    def _read_version() -> str:
        return "0.0.0-dev"


def _window_title() -> str:
    return f"NetScope v{_read_version()}"


def _wait_for_tcp(host: str, port: int, timeout: float = 15.0) -> bool:
    """Return True once *host*:*port* accepts a TCP connection (uvicorn bound)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "web.backend.server:app",
            "--host", _DEFAULT_HOST,
            "--port", str(_DEFAULT_PORT),
        ],
        cwd=_REPO,
    )


def main() -> None:
    url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"
    print(f"NetScope v{_read_version()} — {url}", file=sys.stderr)
    server = start_server()
    if not _wait_for_tcp(_DEFAULT_HOST, _DEFAULT_PORT):
        print(
            "Timed out waiting for the web server to listen on "
            f"{_DEFAULT_HOST}:{_DEFAULT_PORT} — opening the window anyway.",
            file=sys.stderr,
        )
    else:
        time.sleep(0.1)

    try:
        import webview
        webview.create_window(_window_title(), url, width=1200, height=760)
        webview.start()
    except ImportError:
        print(
            "pywebview not installed — open http://127.0.0.1:8765 in your browser.\n"
            "Press Ctrl-C to stop.",
            file=sys.stderr,
        )
        try:
            server.wait()
        except KeyboardInterrupt:
            pass
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
