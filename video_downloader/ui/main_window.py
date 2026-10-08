from __future__ import annotations

import io
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageTk

from ..core import DownloadCancelled, DownloadError, DownloadProgress, clean_error_detail, download_file, test_proxy, validate_destination, validate_http_url
from ..models.auth_config import AuthConfig, CookieMode, SupportedBrowser, build_auth_args
from ..models.download_task import DownloadMode, DownloadTask, TaskState
from ..models.media_info import MediaInfo
from ..proxy import ProxyConfig, ProxyMode
from ..services.app_logging import create_logger
from ..services.download_service import DownloadResult, YtDlpDownloadService
from ..services.filename_utils import safe_stem
from ..services.history import HistoryStore
from ..services.media_analyzer import MediaAnalyzer
from ..services.process_manager import ProcessManager
from ..services.progress_parser import StructuredProgress
from ..services.settings import SettingsStore
from ..services.tool_manager import ToolError, ToolManager
from .settings_window import SettingsPanel


def format_bytes(value: int | float | None) -> str:
    if value is None:
        return "正在计算"
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.2f} {unit}"
        number /= 1024
    return f"{number:.2f} TB"


def format_eta(seconds: int | None) -> str:
    if seconds is None:
        return "正在计算"
    minutes, seconds = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


class VideoDownloaderApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Windows 视频下载工具 v2.1")
        self.root.geometry("940x880")
        self.root.minsize(780, 700)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.tools = ToolManager()
        self.logger = create_logger(self.tools.app_root / "logs")
        self.processes = ProcessManager()
        self.analyzer = MediaAnalyzer(self.tools, self.processes, self.logger)
        self.download_service = YtDlpDownloadService(self.tools, self.processes, self.logger)
        self.settings_store = SettingsStore(self.tools.app_root / "config")
        self.history = HistoryStore(self.tools.app_root / "config")
        saved = self.settings_store.load()

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.poll_after_id: str | None = None
        self.media_info: MediaInfo | None = None
        self.playlist_download = False
        self.last_download: Path | None = None
        self.thumbnail_image: ImageTk.PhotoImage | None = None
        self.active_operation = ""
        self.last_retry: str | None = None

        self.url_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=str(saved.get("output_folder") or (self.tools.app_root / "downloads")))
        self.filename_var = tk.StringVar(value="video")
        self.mode_var = tk.StringVar(value=DownloadMode.BEST.value)
        self.resolution_var = tk.StringVar(value="自动最高")
        self.audio_format_var = tk.StringVar(value="M4A（尽量不重编码）")
        self.proxy_mode_var = tk.StringVar(value=str(saved.get("proxy_mode") or ProxyMode.NONE.value))
        self.proxy_address_var = tk.StringVar(value=str(saved.get("proxy_address") or "http://127.0.0.1:7890"))
        self.proxy_user_var = tk.StringVar(value=str(saved.get("proxy_username") or ""))
        self.proxy_password_var = tk.StringVar()
        self.cookie_mode_var = tk.StringVar(value=str(saved.get("cookie_mode") or CookieMode.NONE.value))
        self.cookie_browser_var = tk.StringVar(value=str(saved.get("cookie_browser") or SupportedBrowser.EDGE.value))
        self.cookie_profile_var = tk.StringVar(value="")
        self.cookie_file_var = tk.StringVar(value=str(saved.get("cookie_file") or ""))
        self.remember_cookie_file_var = tk.BooleanVar(value=bool(saved.get("remember_cookie_file")))
        self.title_var = tk.StringVar(value="尚未解析")
        self.uploader_var = tk.StringVar(value="—")
        self.duration_var = tk.StringVar(value="—")
        self.platform_var = tk.StringVar(value="—")
        self.playlist_var = tk.StringVar(value="单个视频")
        self.state_var = tk.StringVar(value=TaskState.IDLE.value)
        self.size_var = tk.StringVar(value="已下载：0 B / 总大小：正在计算")
        self.speed_var = tk.StringVar(value="速度：0 B/s")
        self.eta_var = tk.StringVar(value="剩余时间：正在计算")

        self._configure_style()
        self._build_ui()
        self.mode_var.trace_add("write", self._mode_changed)
        self.url_var.trace_add("write", self._url_changed)
        self.poll_after_id = self.root.after(100, self._poll_events)
        self.root.after(250, self._refresh_tool_versions)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 6))
        style.configure("TEntry", font=("Microsoft YaHei UI", 10))
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("State.TLabel", font=("Microsoft YaHei UI", 11, "bold"), foreground="#075985")

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Windows 视频下载工具 v2.1", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="支持 yt-dlp 当前兼容的主流公开流媒体视频；可在本机读取 Cookie 登录，但不绕过付费、地区或 DRM 限制。",
            foreground="#666666",
        ).pack(anchor="w", pady=(2, 10))
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)
        self.download_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.download_tab, text="下载")
        self.settings_panel = SettingsPanel(
            notebook,
            proxy_mode=self.proxy_mode_var,
            proxy_address=self.proxy_address_var,
            proxy_username=self.proxy_user_var,
            proxy_password=self.proxy_password_var,
            cookie_mode=self.cookie_mode_var,
            cookie_browser=self.cookie_browser_var,
            cookie_profile=self.cookie_profile_var,
            cookie_file=self.cookie_file_var,
            remember_cookie_file=self.remember_cookie_file_var,
            test_proxy=self._start_proxy_test,
            test_cookie=self._start_cookie_test,
            choose_cookie_file=self._choose_cookie_file,
            refresh_tools=self._refresh_tool_versions,
            update_yt_dlp=self._update_yt_dlp,
            open_log=self._open_log,
        )
        notebook.add(self.settings_panel, text="代理与工具")
        self._build_download_tab()

    def _build_download_tab(self) -> None:
        tab = self.download_tab
        tab.columnconfigure(0, weight=1)
        url_box = ttk.LabelFrame(tab, text="视频网址", padding=10)
        url_box.grid(row=0, column=0, sticky="ew")
        url_box.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_box, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.analyze_button = ttk.Button(url_box, text="解析视频", command=self._start_analysis)
        self.analyze_button.grid(row=0, column=1, padx=(8, 0))

        info_box = ttk.LabelFrame(tab, text="媒体信息", padding=10)
        info_box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        info_box.columnconfigure(1, weight=1)
        self.thumbnail_label = ttk.Label(info_box, text="封面预览", anchor="center", width=24)
        self.thumbnail_label.grid(row=0, column=0, rowspan=5, sticky="nsew", padx=(0, 12))
        for row, (label, variable) in enumerate(
            (("标题：", self.title_var), ("作者/频道：", self.uploader_var), ("时长：", self.duration_var), ("平台：", self.platform_var), ("范围：", self.playlist_var))
        ):
            ttk.Label(info_box, text=label).grid(row=row, column=1, sticky="nw", pady=2)
            ttk.Label(info_box, textvariable=variable, wraplength=570).grid(row=row, column=2, sticky="nw", pady=2)

        options = ttk.LabelFrame(tab, text="下载选项", padding=10)
        options.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        options.columnconfigure(5, weight=1)
        ttk.Label(options, text="模式：").grid(row=0, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(options, textvariable=self.mode_var, values=[mode.value for mode in DownloadMode], state="readonly", width=15)
        self.mode_combo.grid(row=0, column=1, sticky="w")
        ttk.Label(options, text="清晰度：").grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.resolution_combo = ttk.Combobox(options, textvariable=self.resolution_var, values=["自动最高"], state="readonly", width=15)
        self.resolution_combo.grid(row=0, column=3, sticky="w")
        ttk.Label(options, text="音频格式：").grid(row=0, column=4, sticky="w", padx=(14, 0))
        self.audio_combo = ttk.Combobox(
            options,
            textvariable=self.audio_format_var,
            values=["M4A（尽量不重编码）", "MP3（需要重新编码）"],
            state="disabled",
            width=23,
        )
        self.audio_combo.grid(row=0, column=5, sticky="w")
        ttk.Label(options, text="最高画质模式可能输出 MP4 或 MKV，以避免降质和重新编码。", foreground="#9a5b00").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(7, 0)
        )

        save_box = ttk.LabelFrame(tab, text="保存位置", padding=10)
        save_box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        save_box.columnconfigure(1, weight=1)
        ttk.Label(save_box, text="文件夹：").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(save_box, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(save_box, text="选择…", command=self._choose_folder).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(save_box, text="文件名：").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(save_box, textvariable=self.filename_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        status = ttk.LabelFrame(tab, text="任务状态", padding=10)
        status.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.state_var, style="State.TLabel").grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status, maximum=100, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(7, 5))
        detail = ttk.Frame(status)
        detail.grid(row=2, column=0, sticky="ew")
        detail.columnconfigure((0, 1, 2), weight=1)
        ttk.Label(detail, textvariable=self.size_var).grid(row=0, column=0, sticky="w")
        ttk.Label(detail, textvariable=self.speed_var).grid(row=0, column=1, sticky="w")
        ttk.Label(detail, textvariable=self.eta_var).grid(row=0, column=2, sticky="w")

        actions = ttk.Frame(tab)
        actions.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        actions.columnconfigure(4, weight=1)
        self.download_button = ttk.Button(actions, text="开始下载", command=self._start_download)
        self.download_button.grid(row=0, column=0)
        self.cancel_button = ttk.Button(actions, text="取消下载", command=self._cancel_download, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(8, 0))
        self.open_file_button = ttk.Button(actions, text="打开文件", command=self._open_file, state="disabled")
        self.open_file_button.grid(row=0, column=2, padx=(8, 0))
        self.open_folder_button = ttk.Button(actions, text="打开文件夹", command=self._open_folder, state="disabled")
        self.open_folder_button.grid(row=0, column=3, padx=(8, 0))

    def _proxy_config(self) -> ProxyConfig:
        return ProxyConfig(
            ProxyMode(self.proxy_mode_var.get()),
            self.proxy_address_var.get(),
            self.proxy_user_var.get(),
            self.proxy_password_var.get(),
        )

    def _build_auth_config(self) -> AuthConfig:
        mode = CookieMode(self.cookie_mode_var.get())
        if mode is CookieMode.NONE:
            return AuthConfig()
        if mode is CookieMode.BROWSER:
            try:
                browser = SupportedBrowser(self.cookie_browser_var.get())
            except ValueError as exc:
                raise ValueError("请选择有效的浏览器。") from exc
            auth = AuthConfig(cookie_mode=mode, browser=browser, browser_profile=self.cookie_profile_var.get().strip() or None)
        elif mode is CookieMode.FILE:
            path_text = self.cookie_file_var.get().strip()
            if not path_text:
                raise ValueError("请选择 cookies.txt 文件。")
            auth = AuthConfig(cookie_mode=mode, cookie_file=Path(path_text))
        else:
            raise ValueError("无效的 Cookie 方式。")
        build_auth_args(auth)
        return auth

    def _choose_cookie_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Netscape cookies.txt 文件",
            initialdir=str(self.tools.app_root),
            filetypes=[("Netscape Cookie 文件", "*.txt"), ("所有文件", "*.*")],
        )
        if path:
            self.cookie_file_var.set(path)

    def _set_busy(self, operation: str = "") -> None:
        busy = bool(operation)
        self.active_operation = operation
        self.analyze_button.configure(state="disabled" if busy else "normal")
        self.download_button.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if operation in {"download", "cookie"} else "disabled")
        self.settings_panel.set_tools_busy(busy)

    def _url_changed(self, *_args: object) -> None:
        if self.media_info and self.url_var.get().strip() != self.media_info.url:
            self.media_info = None
            self.title_var.set("网址已改变，请重新解析")

    def _mode_changed(self, *_args: object) -> None:
        self.audio_combo.configure(state="readonly" if self.mode_var.get() == DownloadMode.AUDIO_ONLY.value else "disabled")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(self.tools.app_root))
        if folder:
            self.folder_var.set(folder)

    def _start_analysis(self) -> None:
        if self.active_operation:
            return
        try:
            url = validate_http_url(self.url_var.get())
            proxy = self._proxy_config()
            proxy.requests_proxies()
            auth = self._build_auth_config()
        except (DownloadError, ValueError) as exc:
            self._show_error(str(exc), str(exc), "analysis")
            return
        self.last_retry = "analysis"
        self._set_busy("analysis")
        self.state_var.set(TaskState.ANALYZING.value)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

        def work() -> None:
            try:
                info = self.analyzer.analyze(url, proxy, auth)
                thumbnail = self._download_thumbnail(info.thumbnail_url, proxy)
                self.events.put(("analyzed", (info, thumbnail)))
            except Exception as exc:
                self.events.put(("operation_error", (str(exc), getattr(exc, "detail", str(exc)), "analysis")))

        self.worker = threading.Thread(target=work, name="media-analysis", daemon=True)
        self.worker.start()

    @staticmethod
    def _download_thumbnail(url: str, proxy: ProxyConfig) -> bytes | None:
        if not url:
            return None
        try:
            with requests.Session() as session:
                session.trust_env = False
                proxies = proxy.requests_proxies()
                response = session.get(url, timeout=(8, 15), proxies=proxies)
                response.raise_for_status()
                return response.content if len(response.content) <= 8 * 1024 * 1024 else None
        except requests.RequestException:
            return None

    def _apply_media_info(self, info: MediaInfo, thumbnail: bytes | None) -> None:
        self.media_info = info
        self.title_var.set(info.title)
        self.uploader_var.set(info.uploader)
        self.duration_var.set(info.duration_text)
        self.platform_var.set(info.platform)
        self.filename_var.set(safe_stem(info.title, Path(self.folder_var.get())))
        resolutions = ["自动最高", *[f"{item.height}p" for item in info.formats if item.height]]
        self.resolution_combo.configure(values=list(dict.fromkeys(resolutions)))
        self.resolution_var.set("自动最高")
        self.playlist_download = False
        if info.is_playlist:
            choice = messagebox.askyesnocancel(
                "检测到播放列表",
                "这个链接包含播放列表。\n\n是：下载整个播放列表\n否：仅下载当前视频（默认）\n取消：停止",
                parent=self.root,
            )
            if choice is None:
                self.media_info = None
                self.state_var.set(TaskState.IDLE.value)
                return
            self.playlist_download = bool(choice)
        self.playlist_var.set("整个播放列表" if self.playlist_download else "仅当前视频")
        if thumbnail:
            try:
                image = Image.open(io.BytesIO(thumbnail))
                image.thumbnail((190, 108))
                self.thumbnail_image = ImageTk.PhotoImage(image)
                self.thumbnail_label.configure(image=self.thumbnail_image, text="")
            except Exception:
                self.thumbnail_label.configure(text="封面不可用", image="")
        self.state_var.set(TaskState.READY.value)

    def _start_download(self) -> None:
        if self.active_operation:
            return
        try:
            url = validate_http_url(self.url_var.get())
            folder = Path(self.folder_var.get()).expanduser()
            if not folder.is_dir():
                raise DownloadError("保存文件夹不存在，请重新选择。")
            proxy = self._proxy_config()
            proxy.requests_proxies()
        except (DownloadError, ValueError) as exc:
            self._show_error(str(exc), str(exc), "download")
            return

        direct_mp4 = Path(urlsplit(url).path).suffix.lower() == ".mp4" and self.media_info is None
        if not direct_mp4 and self.media_info is None:
            self._show_error("请先点击“解析视频”，确认媒体信息后再下载。", "尚未解析页面链接。", "analysis")
            return

        auth = AuthConfig()
        if not direct_mp4:
            try:
                auth = self._build_auth_config()
            except (DownloadError, ValueError) as exc:
                self._show_error(str(exc), str(exc), "download")
                return

        overwrite = False
        raw_name = self.filename_var.get().strip()
        stem_source = Path(raw_name).stem if Path(raw_name).suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a", ".mp3"} else raw_name
        stem = safe_stem(stem_source, folder)
        if not self.playlist_download and any(folder.glob(f"{stem}.*")):
            choice = messagebox.askyesnocancel(
                "发现同名文件",
                "是：覆盖同名文件\n否：自动生成新名称\n取消：停止下载",
                parent=self.root,
            )
            if choice is None:
                return
            overwrite = bool(choice)

        self.last_retry = "download"
        self.cancel_event.clear()
        self.last_download = None
        self._set_busy("download")
        self.state_var.set(TaskState.DOWNLOADING_VIDEO.value)
        self.progress.stop()
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        self.open_file_button.configure(state="disabled")
        self.open_folder_button.configure(state="disabled")

        def work() -> None:
            try:
                if direct_mp4:
                    filename = self.filename_var.get().strip()
                    if not filename.lower().endswith(".mp4"):
                        filename += ".mp4"
                    destination = validate_destination(folder, filename)
                    if overwrite and destination.exists():
                        destination.unlink()
                    result = download_file(
                        url,
                        destination,
                        proxy,
                        progress_callback=lambda item: self.events.put(("direct_progress", item)),
                        cancel_event=self.cancel_event,
                    )
                    self.events.put(("download_done", DownloadResult([result], [])))
                else:
                    resolution = None
                    if self.resolution_var.get().endswith("p"):
                        resolution = int(self.resolution_var.get()[:-1])
                    task = DownloadTask(
                        url=url,
                        output_folder=folder,
                        filename_stem=stem,
                        mode=DownloadMode(self.mode_var.get()),
                        resolution=resolution,
                        audio_format="mp3" if self.audio_format_var.get().startswith("MP3") else "m4a",
                        playlist=self.playlist_download,
                        overwrite=overwrite,
                        proxy=proxy,
                        auth=auth,
                    )
                    result = self.download_service.download(
                        task,
                        lambda item: self.events.put(("progress", item)),
                        lambda state: self.events.put(("state", state)),
                        self.cancel_event,
                    )
                    self.events.put(("download_done", result))
            except DownloadCancelled:
                self.events.put(("cancelled", folder))
            except Exception as exc:
                self.events.put(("operation_error", (str(exc), getattr(exc, "detail", str(exc)), "download")))

        self.worker = threading.Thread(target=work, name="media-download", daemon=True)
        self.worker.start()

    def _cancel_download(self) -> None:
        if self.active_operation not in {"download", "cookie"}:
            return
        self.cancel_event.set()
        self.state_var.set("正在取消并结束子进程…")
        self.cancel_button.configure(state="disabled")
        threading.Thread(target=self.processes.cancel, name="cancel-process-tree", daemon=True).start()

    def _handle_progress(self, item: StructuredProgress) -> None:
        self.state_var.set(item.state.value)
        if item.percent is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=min(100, item.percent))
        self.size_var.set(f"已下载：{format_bytes(item.downloaded)} / 总大小：{format_bytes(item.total)}")
        self.speed_var.set(f"速度：{format_bytes(item.speed)}/s" if item.speed else "速度：正在计算")
        self.eta_var.set(f"剩余时间：{format_eta(item.eta)}")

    def _handle_direct_progress(self, item: DownloadProgress) -> None:
        progress = StructuredProgress(
            TaskState.DOWNLOADING_VIDEO,
            item.downloaded,
            item.total,
            item.speed_bytes,
            None,
            item.downloaded / item.total * 100 if item.total else None,
        )
        self._handle_progress(progress)

    def _start_proxy_test(self) -> None:
        if self.active_operation:
            return
        try:
            proxy = self._proxy_config()
            proxy.requests_proxies()
        except ValueError as exc:
            self._show_error(str(exc), str(exc), None)
            return
        self._set_busy("proxy")
        self.state_var.set("正在测试代理…")

        def work() -> None:
            try:
                result = test_proxy(proxy)
                self.events.put(("proxy_done", (result, proxy.safe_description())))
            except Exception as exc:
                self.events.put(("operation_error", (str(exc), getattr(exc, "detail", str(exc)), None)))

        self.worker = threading.Thread(target=work, name="proxy-test", daemon=True)
        self.worker.start()

    def _start_cookie_test(self) -> None:
        if self.active_operation:
            return
        try:
            auth = self._build_auth_config()
            if auth.cookie_mode is CookieMode.NONE:
                raise DownloadError("请先选择“从浏览器读取 Cookie”或“使用 cookies.txt 文件”。")
            url = validate_http_url(self.url_var.get())
            proxy = self._proxy_config()
            proxy.requests_proxies()
        except (DownloadError, ValueError) as exc:
            self._show_error(str(exc), str(exc), None)
            return
        self.cancel_event.clear()
        self._set_busy("cookie")
        self.state_var.set("正在测试 Cookie…")

        def work() -> None:
            try:
                result = self.analyzer.test_cookie(url, proxy, auth, self.cancel_event, timeout=45.0)
                self.events.put(("cookie_done", result))
            except DownloadCancelled:
                self.events.put(("cookie_cancelled", None))
            except Exception as exc:
                self.events.put(("operation_error", (str(exc), getattr(exc, "detail", str(exc)), None)))

        self.worker = threading.Thread(target=work, name="cookie-test", daemon=True)
        self.worker.start()

    def _refresh_tool_versions(self) -> None:
        if self.active_operation:
            return
        self._set_busy("tools")

        def work() -> None:
            try:
                self.events.put(("tool_versions", self.tools.versions()))
            except Exception as exc:
                self.events.put(("operation_error", (str(exc), getattr(exc, "detail", str(exc)), None)))

        self.worker = threading.Thread(target=work, name="tool-check", daemon=True)
        self.worker.start()

    def _update_yt_dlp(self) -> None:
        if self.active_operation:
            messagebox.showwarning("暂时不能更新", "请等待当前任务结束后再更新。", parent=self.root)
            return
        self._set_busy("update")
        self.settings_panel.tool_versions.set("正在安全更新 yt-dlp…")

        def work() -> None:
            try:
                self.events.put(("update_done", self.tools.update_yt_dlp()))
            except Exception as exc:
                self.events.put(("operation_error", (str(exc), getattr(exc, "detail", str(exc)), None)))

        self.worker = threading.Thread(target=work, name="tool-update", daemon=True)
        self.worker.start()

    def _poll_events(self) -> None:
        self.poll_after_id = None
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "analyzed":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self._set_busy()
                    info, thumbnail = payload  # type: ignore[misc]
                    self._apply_media_info(info, thumbnail)
                elif kind == "progress":
                    self._handle_progress(payload)  # type: ignore[arg-type]
                elif kind == "direct_progress":
                    self._handle_direct_progress(payload)  # type: ignore[arg-type]
                elif kind == "state":
                    self.state_var.set(payload.value)  # type: ignore[union-attr]
                elif kind == "download_done":
                    self._download_finished(payload)  # type: ignore[arg-type]
                elif kind == "cancelled":
                    self._cancel_finished(Path(payload))  # type: ignore[arg-type]
                elif kind == "operation_error":
                    message, detail, retry = payload  # type: ignore[misc]
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self.state_var.set(TaskState.FAILED.value)
                    self._set_busy()
                    self._show_error(str(message), str(detail), retry)
                elif kind == "proxy_done":
                    result, description = payload  # type: ignore[misc]
                    self._set_busy()
                    self.state_var.set("代理连接成功")
                    messagebox.showinfo("代理连接成功", f"代理：{description}\n状态码：{result.status_code}\n耗时：{result.elapsed_seconds:.2f} 秒", parent=self.root)
                elif kind == "cookie_done":
                    result = payload  # type: ignore[assignment]
                    self._set_busy()
                    self.state_var.set("Cookie 验证成功")
                    messagebox.showinfo(
                        "Cookie 验证成功",
                        f"浏览器：{result.browser_label}\n视频：{result.title}\n频道：{result.uploader}\n\n现在可以返回主界面开始下载。",
                        parent=self.root,
                    )
                elif kind == "cookie_cancelled":
                    self._set_busy()
                    self.state_var.set(TaskState.CANCELLED.value)
                elif kind == "tool_versions":
                    versions = payload  # type: ignore[assignment]
                    self.settings_panel.tool_versions.set("\n".join(f"{key}: {value}" for key, value in versions.items()))
                    self._set_busy()
                elif kind == "update_done":
                    self._set_busy()
                    messagebox.showinfo("更新完成", str(payload), parent=self.root)
                    self._refresh_tool_versions()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.poll_after_id = self.root.after(100, self._poll_events)

    def _download_finished(self, result: DownloadResult) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100)
        self.state_var.set(TaskState.COMPLETED.value)
        self._set_busy()
        self.last_download = result.files[-1]
        self.open_file_button.configure(state="normal")
        self.open_folder_button.configure(state="normal")
        info = self.media_info
        self.history.add(
            title=info.title if info else self.last_download.stem,
            url=self.url_var.get().strip(),
            platform=info.platform if info else "直接 MP4",
            path=str(self.last_download),
            status="成功",
        )
        messagebox.showinfo("下载完成", f"已保存：\n{self.last_download}", parent=self.root)

    def _cancel_finished(self, folder: Path) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.state_var.set(TaskState.CANCELLED.value)
        self._set_busy()
        keep = messagebox.askyesno("下载已取消", "是否保留 .part 临时文件？", parent=self.root)
        if not keep:
            removed = self.download_service.remove_partial_files(folder)
            self.state_var.set(f"已取消，已清理 {removed} 个临时文件")

    def _show_error(self, message: str, detail: str, retry: str | None) -> None:
        cleaned = clean_error_detail(detail)
        window = tk.Toplevel(self.root)
        window.title("操作失败")
        window.transient(self.root)
        window.grab_set()
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=message, wraplength=520, foreground="#991b1b").pack(anchor="w")
        details = tk.Text(frame, width=72, height=7, wrap="word")
        details.pack(fill="both", expand=True, pady=(10, 10))
        details.insert("1.0", cleaned)
        details.configure(state="disabled")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="复制详细信息", command=lambda: self._copy_text(cleaned or message)).pack(side="left")
        ttk.Button(buttons, text="打开日志", command=self._open_log).pack(side="left", padx=(8, 0))
        if retry:
            ttk.Button(buttons, text="重新尝试", command=lambda: self._retry(window, retry)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="关闭", command=window.destroy).pack(side="right")

    def _copy_text(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _retry(self, window: tk.Toplevel, retry: str) -> None:
        window.destroy()
        if retry == "analysis":
            self._start_analysis()
        elif retry == "download":
            self._start_download()

    def _save_settings(self) -> None:
        values = {
            "output_folder": self.folder_var.get(),
            "proxy_mode": self.proxy_mode_var.get(),
            "proxy_address": self.proxy_address_var.get(),
            "proxy_username": self.proxy_user_var.get(),
            "cookie_mode": self.cookie_mode_var.get(),
            "cookie_browser": self.cookie_browser_var.get(),
            "remember_cookie_file": self.remember_cookie_file_var.get(),
        }
        if self.remember_cookie_file_var.get() and self.cookie_file_var.get().strip():
            values["cookie_file"] = self.cookie_file_var.get().strip()
        self.settings_store.save(values)

    def _open_file(self) -> None:
        if self.last_download and self.last_download.exists():
            os.startfile(str(self.last_download))

    def _open_folder(self) -> None:
        folder = self.last_download.parent if self.last_download else Path(self.folder_var.get())
        if folder.exists():
            os.startfile(str(folder))

    def _open_log(self) -> None:
        path = self.tools.app_root / "logs" / "video_downloader.log"
        path.touch(exist_ok=True)
        os.startfile(str(path))

    def _on_close(self) -> None:
        if self.active_operation in {"download", "analysis"}:
            if not messagebox.askyesno("任务仍在运行", "关闭程序会终止当前任务，确定退出吗？", parent=self.root):
                return
            self.cancel_event.set()
            self.processes.cancel()
        self._save_settings()
        if self.poll_after_id:
            try:
                self.root.after_cancel(self.poll_after_id)
            except tk.TclError:
                pass
        self.root.destroy()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            if self.poll_after_id:
                try:
                    self.root.after_cancel(self.poll_after_id)
                except tk.TclError:
                    pass
                self.poll_after_id = None
