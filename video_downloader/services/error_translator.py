from __future__ import annotations


# 每条规则：(关键词元组, 中文提示, 是否要求全部关键词同时命中)
ERROR_RULES = (
    (("sign in to confirm you're not a bot",), "YouTube 要求登录验证，请在设置中启用浏览器 Cookie。", True),
    (("could not copy", "cookie database"), "无法读取浏览器 Cookie，请完全关闭浏览器后重试。", True),
    (("could not find", "cookies database"), "没有找到该浏览器的 Cookie，请确认浏览器和配置文件。", True),
    (("failed to decrypt with dpapi",), "Chrome/Edge 的 Cookie 受到 Windows 应用绑定加密保护，当前无法直接读取；请改用 Firefox 登录，或选择 Netscape 格式的 cookies.txt。", True),
    (("failed to decrypt", "cookie"), "Cookie 解密失败，请尝试使用当前 Windows 用户运行，或改用 Firefox。", True),
    (("cookie file must be in netscape format",), "Cookie 文件格式不正确，需要 Netscape cookies.txt。", False),
    (("http error 400", "cookie"), "Cookie 文件可能已损坏或换行格式不正确。", True),
    (("cookies are no longer valid", "cookies have expired"), "Cookie 已过期，请重新登录并更新 Cookie。", False),
    (("account", "temporarily"), "网站暂时限制了该账号，请停止重试并稍后再试。", True),
    (("http error 429", "too many requests"), "请求过于频繁，请稍后再试。", False),
    (("private video", "private"), "这是私密视频，本工具不会绕过访问权限。", False),
    (("members-only", "members only"), "这是会员内容，本工具不会绕过会员权限。", False),
    (("drm", "encrypted"), "内容受到 DRM 保护，本工具不支持下载。", False),
    (("unsupported url", "no suitable extractor"), "暂不支持这个网站或链接格式。", False),
    (("video unavailable", "video is unavailable", "not available"), "视频不存在、已删除或暂时不可用。", False),
    (("sign in", "login required", "cookies"), "该视频需要登录，请在设置中启用浏览器 Cookie。", False),
    (("http error 403", "403 forbidden"), "网站拒绝访问，请更新 yt-dlp 或检查网络。", False),
    (("geo", "not available in your country"), "当前地区无法访问该内容。", False),
    (("ffmpeg", "ffprobe"), "未找到或无法使用 FFmpeg，无法合并音视频。", False),
    (("timed out", "timeout"), "网络连接超时，请检查网络或代理。", False),
    (("no space left", "disk full"), "磁盘空间不足。", False),
    (("permission denied", "access is denied"), "保存目录没有写入权限。", False),
    (("proxy", "socks"), "代理连接失败，请检查代理设置，或切换为直连后重试。", False),
)


def translate_error(detail: str) -> str:
    lowered = detail.lower()
    for needles, message, require_all in ERROR_RULES:
        if require_all:
            matches = all(needle in lowered for needle in needles)
        else:
            matches = any(needle in lowered for needle in needles)
        if matches:
            return message
    return "下载失败，请查看详细日志或重试。"
