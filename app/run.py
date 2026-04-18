"""
Launcher: start uvicorn + open the browser.
    python -m app.run
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

HOST = os.environ.get("ADMISSION_APP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADMISSION_APP_PORT", "8766"))


def _open_browser():
    time.sleep(1.0)
    webbrowser.open(f"http://{HOST}:{PORT}/")


def main():
    try:
        import uvicorn
    except ImportError:
        print("請先安裝套件： pip install -r app/requirements.txt", file=sys.stderr)
        sys.exit(1)

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
