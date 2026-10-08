from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_VALUE_OPTIONS = frozenset({
    "--cookies",
    "--cookies-from-browser",
    "--username",
    "--password",
    "--video-password",
})
FULLY_MASKED_OPTIONS = frozenset({
    "--cookies",
    "--username",
    "--password",
    "--video-password",
})
_HEADER_PATTERN = re.compile(r"(?i)\b(cookie|authorization|proxy-authorization|set-cookie)\s*[:=]\s*(\"[^\"]*\"|\S+)")


def _mask_browser_value(value: str) -> str:
    for separator in ("+", ":"):
        if separator in value:
            return value.split(separator, 1)[0] + separator + "<配置路径已隐藏>"
    return value


def redact_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    safe = str(text)
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, "***")
    safe = _HEADER_PATTERN.sub(lambda match: f"{match.group(1)}: <已隐藏>", safe)
    for token in safe.split():
        if "://" not in token or "@" not in token:
            continue
        try:
            parsed = urlsplit(token.strip("'\"(),"))
            if parsed.username:
                host = parsed.hostname or ""
                port = f":{parsed.port}" if parsed.port else ""
                clean = urlunsplit((parsed.scheme, f"***:***@{host}{port}", parsed.path, parsed.query, parsed.fragment))
                safe = safe.replace(token.strip("'\"(),"), clean)
        except (ValueError, TypeError):
            pass
    return safe


def redact_args(arguments: list[str], secrets: tuple[str, ...] = ()) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item in SENSITIVE_VALUE_OPTIONS:
            result.append(item)
            if index + 1 < len(arguments):
                value = arguments[index + 1]
                if item == "--cookies-from-browser":
                    result.append(_mask_browser_value(value))
                else:
                    result.append("<已隐藏>")
                index += 2
                continue
        elif item.startswith("--cookies-from-browser="):
            result.append("--cookies-from-browser " + _mask_browser_value(item.split("=", 1)[1]))
            index += 1
            continue
        elif item.startswith("--cookies="):
            result.append("--cookies <已隐藏>")
            index += 1
            continue
        result.append(item)
        index += 1
    return [redact_text(item, secrets) for item in result]


def redact_command(arguments: list[str], secrets: tuple[str, ...] = ()) -> str:
    return " ".join(redact_args(arguments, secrets))


def create_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("video_downloader")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_dir / "video_downloader.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
