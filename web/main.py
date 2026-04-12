"""NetScope web — PyWebView launcher (starts uvicorn + opens native window)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_ROOT)

try:
    from core.version import read_version as _read_version
except ImportError:  # pragma: no cover - cwd edge case
    def _read_version() -> str:
        return "0.0.0-dev"


def _window_title() -> str:
    return f"NetScope v{_read_version()}"


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "web.backend.server:app",
            "--host", "127.0.0.1",
            "--port", "8765",
        ],
        cwd=_REPO,
    )


def main() -> None:
    print(f"NetScope v{_read_version()} — http://127.0.0.1:8765", file=sys.stderr)
    server = start_server()
    time.sleep(1.5)

    try:
        import webview
        webview.create_window(_window_title(), "http://127.0.0.1:8765", width=1200, height=760)
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
