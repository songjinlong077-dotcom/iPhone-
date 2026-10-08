from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..models.auth_config import BROWSER_LABELS, LABEL_TO_BROWSER, CookieMode, SupportedBrowser
from ..proxy import ProxyMode


class SettingsPanel(ttk.Frame):
    BROWSER_DISPLAY = [BROWSER_LABELS[browser] for browser in SupportedBrowser]

    def __init__(
        self,
        parent: tk.Misc,
        *,
        proxy_mode: tk.StringVar,
        proxy_address: tk.StringVar,
        proxy_username: tk.StringVar,
        proxy_password: tk.StringVar,
        cookie_mode: tk.StringVar,
        cookie_browser: tk.StringVar,
        cookie_profile: tk.StringVar,
        cookie_file: tk.StringVar,
        remember_cookie_file: tk.BooleanVar,
        test_proxy: Callable[[], None],
        test_cookie: Callable[[], None],
        choose_cookie_file: Callable[[], None],
        refresh_tools: Callable[[], None],
        update_yt_dlp: Callable[[], None],
        open_log: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=16)
        self.columnconfigure(0, weight=1)
        self._cookie_mode = cookie_mode

        proxy_box = ttk.LabelFrame(self, text="代理设置", padding=12)
        proxy_box.grid(row=0, column=0, sticky="ew")
        proxy_box.columnconfigure(1, weight=1)

        ttk.Label(proxy_box, text="代理类型：").grid(row=0, column=0, sticky="w", pady=5)
        self.proxy_combo = ttk.Combobox(
            proxy_box,
            textvariable=proxy_mode,
            values=[mode.value for mode in ProxyMode],
            state="readonly",
            width=18,
        )
        self.proxy_combo.grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(proxy_box, text="代理地址：").grid(row=1, column=0, sticky="w", pady=5)
        self.address_entry = ttk.Entry(proxy_box, textvariable=proxy_address)
        self.address_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(proxy_box, text="用户名（可选）：").grid(row=2, column=0, sticky="w", pady=5)
        self.user_entry = ttk.Entry(proxy_box, textvariable=proxy_username)
        self.user_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(proxy_box, text="密码（不保存）：").grid(row=3, column=0, sticky="w", pady=5)
        self.password_entry = ttk.Entry(proxy_box, textvariable=proxy_password, show="●")
        self.password_entry.grid(row=3, column=1, sticky="ew", pady=5)
        self.show_password = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            proxy_box,
            text="显示密码",
            variable=self.show_password,
            command=lambda: self.password_entry.configure(show="" if self.show_password.get() else "●"),
        ).grid(row=3, column=2, padx=(8, 0))
        self.proxy_widgets = [self.address_entry, self.user_entry, self.password_entry]
        self.test_button = ttk.Button(proxy_box, text="测试代理", command=test_proxy)
        self.test_button.grid(row=4, column=1, sticky="w", pady=(8, 0))

        cookie_box = ttk.LabelFrame(self, text="Cookie 与网站身份验证", padding=12)
        cookie_box.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        cookie_box.columnconfigure(1, weight=1)

        ttk.Label(cookie_box, text="网站身份验证：").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Radiobutton(cookie_box, text="不使用 Cookie", variable=cookie_mode, value=CookieMode.NONE.value).grid(
            row=1, column=0, columnspan=3, sticky="w"
        )
        ttk.Radiobutton(cookie_box, text="从浏览器读取 Cookie", variable=cookie_mode, value=CookieMode.BROWSER.value).grid(
            row=2, column=0, columnspan=3, sticky="w"
        )
        ttk.Radiobutton(cookie_box, text="使用 cookies.txt 文件", variable=cookie_mode, value=CookieMode.FILE.value).grid(
            row=3, column=0, columnspan=3, sticky="w"
        )

        ttk.Label(cookie_box, text="浏览器：").grid(row=4, column=0, sticky="w", pady=(10, 4))
        self.browser_combo = ttk.Combobox(
            cookie_box,
            values=self.BROWSER_DISPLAY,
            state="readonly",
            width=18,
        )
        self.browser_combo.grid(row=4, column=1, sticky="w", pady=(10, 4))
        self.browser_combo.set(BROWSER_LABELS.get(self._to_browser(cookie_browser.get()), self.BROWSER_DISPLAY[0]))
        self.browser_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: cookie_browser.set(LABEL_TO_BROWSER[self.browser_combo.get()].value),
        )

        ttk.Label(cookie_box, text="配置文件（留空=自动检测）：").grid(row=5, column=0, sticky="w", pady=4)
        self.profile_entry = ttk.Entry(cookie_box, textvariable=cookie_profile)
        self.profile_entry.grid(row=5, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(cookie_box, text="Cookie 文件：").grid(row=6, column=0, sticky="w", pady=4)
        self.cookie_file_entry = ttk.Entry(cookie_box, textvariable=cookie_file, state="readonly")
        self.cookie_file_entry.grid(row=6, column=1, sticky="ew", pady=4)
        self.choose_file_button = ttk.Button(cookie_box, text="选择文件", command=choose_cookie_file)
        self.choose_file_button.grid(row=6, column=2, padx=(8, 0))

        self.cookie_test_button = ttk.Button(cookie_box, text="测试 Cookie", command=test_cookie)
        self.cookie_test_button.grid(row=7, column=1, sticky="w", pady=(8, 0))

        ttk.Checkbutton(
            cookie_box,
            text="记住 Cookie 文件路径（只保存路径，不复制内容）",
            variable=remember_cookie_file,
        ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Label(
            cookie_box,
            text=(
                "Cookie 只用于读取你本机已有的登录状态。\n"
                "程序不会保存账号密码，也不会绕过付费、私密或 DRM 限制。\n"
                "频繁自动下载可能触发网站风控，请仅下载有权访问的内容。"
            ),
            foreground="#9a5b00",
            justify="left",
            wraplength=560,
        ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.cookie_widgets_browser = [self.browser_combo, self.profile_entry]
        self.cookie_widgets_file = [self.cookie_file_entry, self.choose_file_button]

        tools_box = ttk.LabelFrame(self, text="随附工具", padding=12)
        tools_box.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        tools_box.columnconfigure(0, weight=1)
        self.tool_versions = tk.StringVar(value="正在检查工具…")
        ttk.Label(tools_box, textvariable=self.tool_versions, justify="left").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Button(tools_box, text="刷新版本", command=refresh_tools).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.update_button = ttk.Button(tools_box, text="更新 yt-dlp", command=update_yt_dlp)
        self.update_button.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        ttk.Button(tools_box, text="打开日志", command=open_log).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

        ttk.Label(
            self,
            text="设置只保存在本机；代理密码不会写入 settings.json 或日志，Cookie 内容不会保存或记录。",
            foreground="#666666",
        ).grid(row=3, column=0, sticky="w", pady=(14, 0))
        proxy_mode.trace_add("write", lambda *_: self.update_proxy_state(proxy_mode.get()))
        cookie_mode.trace_add("write", lambda *_: self.update_cookie_state(cookie_mode.get()))
        self.update_proxy_state(proxy_mode.get())
        self.update_cookie_state(cookie_mode.get())

    @staticmethod
    def _to_browser(value: str) -> SupportedBrowser:
        try:
            return SupportedBrowser(value)
        except ValueError:
            return SupportedBrowser.EDGE

    def update_proxy_state(self, mode: str) -> None:
        enabled = mode != ProxyMode.NONE.value
        state = "normal" if enabled else "disabled"
        for widget in self.proxy_widgets:
            widget.configure(state=state)
        self.test_button.configure(state=state)

    def update_cookie_state(self, mode: str) -> None:
        browser_state = "normal" if mode == CookieMode.BROWSER.value else "disabled"
        file_state = "normal" if mode == CookieMode.FILE.value else "disabled"
        test_state = "normal" if mode in {CookieMode.BROWSER.value, CookieMode.FILE.value} else "disabled"
        for widget in self.cookie_widgets_browser:
            widget.configure(state=browser_state)
        for widget in self.cookie_widgets_file:
            widget.configure(state=file_state)
        self.cookie_test_button.configure(state=test_state)

    def set_tools_busy(self, busy: bool) -> None:
        self.update_button.configure(state="disabled" if busy else "normal")
