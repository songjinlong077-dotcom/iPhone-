"""向后兼容的 GUI 导入入口。"""

from .ui.main_window import VideoDownloaderApp, format_bytes

__all__ = ["VideoDownloaderApp", "format_bytes"]
