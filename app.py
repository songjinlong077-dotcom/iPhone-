from __future__ import annotations

import sys
from pathlib import Path

from video_downloader.gui import VideoDownloaderApp


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    app = VideoDownloaderApp()
    if smoke_test:
        app.root.after(600, app.root.destroy)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
