#!/usr/bin/env python3
"""NetScope — macOS WiFi & network diagnostics."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    if sys.platform != "darwin":
        print("NetScope requires macOS (CoreWLAN and system tools).", file=sys.stderr)
        sys.exit(1)
    try:
        import CoreWLAN  # noqa: F401
    except ImportError:
        print(
            "NetScope requires CoreWLAN (PyObjC). Install dependencies: pip install -r requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    from ui.app import NetScopeApp

    app = NetScopeApp()
    app.run()


if __name__ == "__main__":
    main()
