from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from video_downloader.core import clean_error_detail, validate_http_url
from video_downloader.models.auth_config import (
    AuthConfig,
    CookieMode,
    SupportedBrowser,
    build_auth_args,
    validate_browser_profile,
    validate_cookie_file,
)
from video_downloader.models.download_task import DownloadTask
from video_downloader.proxy import ProxyConfig
from video_downloader.services.app_logging import redact_args, redact_text
from video_downloader.services.download_service import YtDlpDownloadService
from video_downloader.services.error_translator import translate_error
from video_downloader.services.media_analyzer import MediaAnalyzer


class ParameterTests(unittest.TestCase):
    """参数构建：默认无 Cookie、浏览器模式、文件模式、非法输入。"""

    def test_none_mode_produces_no_auth_arguments(self) -> None:
        self.assertEqual(build_auth_args(AuthConfig()), [])

    def test_browser_mode_emits_cookies_from_browser(self) -> None:
        args = build_auth_args(AuthConfig(cookie_mode=CookieMode.BROWSER, browser=SupportedBrowser.EDGE))
        self.assertEqual(args, ["--cookies-from-browser", "edge"])

    def test_browser_mode_with_profile_uses_colon_separator(self) -> None:
        args = build_auth_args(
            AuthConfig(cookie_mode=CookieMode.BROWSER, browser=SupportedBrowser.CHROME, browser_profile="Profile 1")
        )
        self.assertEqual(args, ["--cookies-from-browser", "chrome:Profile 1"])

    def test_browser_mode_rejects_unknown_browser(self) -> None:
        with self.assertRaises(ValueError):
            build_auth_args(AuthConfig(cookie_mode=CookieMode.BROWSER, browser="opera"))  # type: ignore[arg-type]

    def test_file_mode_emits_cookies_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cookie_file = Path(tmp) / "cookies.txt"
            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tid\t1\n", encoding="utf-8"
            )
            args = build_auth_args(AuthConfig(cookie_mode=CookieMode.FILE, cookie_file=cookie_file))
            self.assertEqual(args, ["--cookies", str(cookie_file)])

    def test_file_mode_requires_valid_netscape_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cookie_file = Path(tmp) / "cookies.txt"
            cookie_file.write_text("not a netscape header\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_auth_args(AuthConfig(cookie_mode=CookieMode.FILE, cookie_file=cookie_file))


class SecurityTests(unittest.TestCase):
    """安全约束：Cookie 内容不落命令行、敏感信息被遮蔽、非法输入被拒绝。"""

    def test_validate_browser_profile_rejects_control_chars_and_flags_and_urls(self) -> None:
        for bad in ("line\nbreak", "--profile", "https://example.com", "file:///c:/x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_browser_profile(bad)
        self.assertEqual(validate_browser_profile("  Default  "), "Default")
        self.assertEqual(validate_browser_profile(None), "")

    def test_validate_cookie_file_rejects_missing_empty_and_oversized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.txt"
            with self.assertRaises(ValueError):
                validate_cookie_file(missing)
            empty = Path(tmp) / "empty.txt"
            empty.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_cookie_file(empty)
            oversized = Path(tmp) / "big.txt"
            oversized.write_text("# Netscape HTTP Cookie File\n" + "x" * (21 * 1024 * 1024), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_cookie_file(oversized)
            not_netscape = Path(tmp) / "plain.txt"
            not_netscape.write_text("hello\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_cookie_file(not_netscape)

    def test_redact_args_masks_browser_profile_and_cookie_path(self) -> None:
        self.assertEqual(
            redact_args(["--cookies-from-browser", "chrome:Profile 1"]),
            ["--cookies-from-browser", "chrome:<配置路径已隐藏>"],
        )
        self.assertEqual(redact_args(["--cookies", "/secret/cookies.txt"]), ["--cookies", "<已隐藏>"])
        self.assertEqual(
            redact_args(["--cookies-from-browser=edge+Default"]),
            ["--cookies-from-browser edge+<配置路径已隐藏>"],
        )

    def test_redact_text_masks_cookie_and_auth_headers(self) -> None:
        self.assertNotIn("abc=def", redact_text("Cookie: abc=def"))
        self.assertNotIn("Bearer xyz", redact_text("Authorization: Bearer xyz"))

    def test_redact_text_replaces_explicit_secrets(self) -> None:
        self.assertEqual(redact_text("proxy secret123 here", ("secret123",)), "proxy *** here")

    def test_auth_args_never_embed_cookie_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cookie_file = Path(tmp) / "cookies.txt"
            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tsession\tVERYSECRET\n",
                encoding="utf-8",
            )
            args = build_auth_args(AuthConfig(cookie_mode=CookieMode.FILE, cookie_file=cookie_file))
            joined = " ".join(args)
            self.assertNotIn("VERYSECRET", joined)
            self.assertIn(str(cookie_file), joined)

    def test_validate_http_url_still_blocks_non_http_schemes(self) -> None:
        for bad in ("file:///c:/x.mp4", "ftp://host/x.mp4", "javascript:alert(1)", "no-scheme"):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                validate_http_url(bad)

    def test_clean_error_detail_strips_null_tokens(self) -> None:
        self.assertEqual(clean_error_detail(None), "")
        self.assertEqual(clean_error_detail("null"), "")
        self.assertEqual(clean_error_detail("None"), "")
        self.assertEqual(clean_error_detail("  some detail  "), "some detail")

    def test_clean_error_detail_strips_standalone_null_lines(self) -> None:
        self.assertEqual(
            clean_error_detail("ERROR: sign in to confirm you're not a bot\nnull"),
            "ERROR: sign in to confirm you're not a bot",
        )
        self.assertEqual(clean_error_detail("line1\nNone\nline3"), "line1\nline3")


class SharedArgumentsTests(unittest.TestCase):
    """解析与下载必须使用完全一致的认证参数。"""

    @staticmethod
    def _fake_tools(tmp: Path) -> SimpleNamespace:
        return SimpleNamespace(
            require_tools=Mock(),
            validate_output_folder=Mock(),
            app_root=tmp,
            paths=SimpleNamespace(
                yt_dlp=Path("yt-dlp.exe"),
                root=tmp / "tools",
                deno=tmp / "tools" / "deno.exe",
                ffmpeg=tmp / "tools" / "ffmpeg.exe",
                ffprobe=tmp / "tools" / "ffprobe.exe",
            ),
        )

    def test_parse_and_download_use_identical_auth_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            output.mkdir()
            tools = self._fake_tools(root)
            auth = AuthConfig(cookie_mode=CookieMode.BROWSER, browser=SupportedBrowser.FIREFOX)
            task = DownloadTask(url="https://youtube.com/watch?v=abc", output_folder=output, filename_stem="v", auth=auth)
            service = YtDlpDownloadService(tools, Mock(), Mock())
            download_args, _stem = service.build_arguments(task)

            analyzer = MediaAnalyzer(tools, Mock(), Mock())
            parse_args = analyzer._parse_arguments(task.url, ProxyConfig(), auth)

            self.assertIn("--cookies-from-browser", download_args)
            self.assertIn("firefox", download_args)
            self.assertIn("--cookies-from-browser", parse_args)
            self.assertIn("firefox", parse_args)


class ErrorTranslationTests(unittest.TestCase):
    def test_sign_in_bot_message(self) -> None:
        self.assertEqual(
            translate_error("Sign in to confirm you're not a bot"),
            "YouTube 要求登录验证，请在设置中启用浏览器 Cookie。",
        )

    def test_cookie_database_cannot_be_read(self) -> None:
        self.assertEqual(
            translate_error("Could not copy the cookie database"),
            "无法读取浏览器 Cookie，请完全关闭浏览器后重试。",
        )

    def test_chromium_dpapi_app_bound_encryption(self) -> None:
        self.assertEqual(
            translate_error("Failed to decrypt with DPAPI"),
            "Chrome/Edge 的 Cookie 受到 Windows 应用绑定加密保护，当前无法直接读取；请改用 Firefox 登录，或选择 Netscape 格式的 cookies.txt。",
        )

    def test_cookie_file_not_netscape(self) -> None:
        self.assertEqual(
            translate_error("cookie file must be in netscape format"),
            "Cookie 文件格式不正确，需要 Netscape cookies.txt。",
        )

    def test_expired_cookies(self) -> None:
        self.assertEqual(
            translate_error("cookies have expired"),
            "Cookie 已过期，请重新登录并更新 Cookie。",
        )

    def test_private_and_drm_messages(self) -> None:
        self.assertEqual(translate_error("this video is private"), "这是私密视频，本工具不会绕过访问权限。")
        self.assertEqual(translate_error("DRM encrypted content"), "内容受到 DRM 保护，本工具不支持下载。")


if __name__ == "__main__":
    unittest.main(verbosity=2)
