# Windows 视频下载工具 v2.1

> 第四版状态：FastAPI 服务端、原生 SwiftUI 客户端源码和 GitHub Actions IPA工作流均已完成。GitHub Actions Run `37782960088` 已通过 FastAPI 6/6、Swift 2/2、iPhoneOS arm64 构建和 IPA完整性检查，并生成待 Sideloadly 重签的 IPA。详见 `03_工作过程\第四版GitHubActions配置验收记录.md`。

Windows 中文 GUI 视频下载器。第二版在第一版 MP4 直链下载基础上集成项目随附的 yt-dlp、FFmpeg、FFprobe 和 Deno，支持 yt-dlp 当前兼容的主流公开、可访问、无 DRM 流媒体页面；v2.1 新增浏览器 Cookie 与 cookies.txt 登录支持，用于解决 YouTube 等网站的“登录确认不是机器人”拦截。

项目目录：`D:\workspace\projects\Project002_Windows视频下载工具`

## 最简单的运行方式

交付版主程序：

```text
04_交付物\Windows视频下载工具_v2.1\视频下载工具.exe
```

桌面的“视频下载工具”快捷方式也会打开此交付版。整个 `Windows视频下载工具_v2.1` 文件夹必须一起保留，不能只移动 EXE。

## 下载公开页面视频

1. 粘贴 YouTube、Instagram 或其他 yt-dlp 支持的公开页面 URL。
2. 点击“解析视频”。
3. 检查标题、作者、时长、平台、封面和清晰度。
4. 选择模式：
   - 最高画质：默认，优先 `bv*+ba/b`，不重新编码；结果可能为 MP4 或 MKV。
   - 兼容 MP4：优先 MP4 视频和 M4A 音频。
   - 仅音频：M4A 或 MP3；MP3 会重新编码。
5. 选择保存位置和文件名，点击“开始下载”。
6. 可随时点击“取消下载”；程序会结束 yt-dlp 及其 FFmpeg 子进程，并询问是否保留 `.part`。

如果链接要求登录、会员、私密访问、地区权限或 DRM，程序会拒绝，不尝试绕过。

## Cookie 登录（v2.1 新增）

当 YouTube 提示“Sign in to confirm you're not a bot”时，可在“设置”标签页启用 Cookie：

- **从浏览器读取 Cookie**：选择 Microsoft Edge、Google Chrome 或 Mozilla Firefox，可选填写浏览器配置文件；程序通过 `--cookies-from-browser` 读取本机登录状态。
- **使用 cookies.txt 文件**：选择 Netscape 格式的 cookies.txt，程序通过 `--cookies` 使用它。
- 可点击“测试 Cookie”验证当前登录状态是否有效。

安全边界：

- 不提供账号密码输入框，程序永远不知道也不会保存你的 YouTube 密码。
- Cookie 只用于读取本机已有登录状态，其实际内容不会出现在命令行参数、日志、settings.json 或错误窗口中。
- 不会绕过付费、会员、私密或 DRM 限制；频繁自动下载可能触发网站风控，请仅下载有权访问的内容。

## 直接 MP4 下载

以 `.mp4` 结尾的直接文件 URL 可以不解析，粘贴后直接点击“开始下载”。第一版下载核心和代理测试继续保留。

## 代理和工具

“设置”标签页支持：

- 不使用代理、HTTP、HTTPS、SOCKS5。
- 可选用户名与密码；密码默认隐藏，不保存到配置或日志。
- 代理连通性测试。
- 查看四个随附工具的版本。
- 安全更新 yt-dlp：先下载到临时文件并执行验证，成功后才替换；失败保留旧版本。
- 打开经过脱敏的本机日志。

## 源码运行

```powershell
cd 'D:\workspace\projects\Project002_Windows视频下载工具'
.\.venv\Scripts\python.exe main.py
```

重新安装依赖：

```powershell
py -m venv .venv
$env:PYTHONUTF8='1'
$env:PIP_PROGRESS_BAR='off'
.\.venv\Scripts\python.exe -m pip install --no-color -r requirements-dev.txt
```

## 测试

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe '.\03_工作过程\verify_mp4_integration.py'
.\.venv\Scripts\python.exe '.\03_工作过程\verify_v2_acceptance.py'
```

详见 `03_工作过程\第二版验收记录.md`。

## 打包

```powershell
.\build_config\build_windows.ps1
```

构建方式为 PyInstaller `onedir/windowed`。四个外部工具和许可证以独立目录保留，便于更新、审计和排错。

## 数据位置

- `config\settings.json`：本机设置，不含代理密码和 Cookie 内容；仅在勾选“记住 Cookie 文件路径”时保存文件路径。
- `config\history.json`：最近 500 条本机下载历史。
- `config\download-archive.txt`：播放列表防重复记录。
- `logs\video_downloader.log`：轮转日志，敏感代理信息和 Cookie 内容脱敏。
- `downloads\`：默认下载目录。

## 当前限制

- 无法保证所有网站和所有视频；实际能力随 yt-dlp 和网站变化。
- Cookie 登录用于通过“确认不是机器人”验证，不绕过会员、私密或 DRM。
- 浏览器 Cookie 读取依赖本机浏览器和当前 Windows 用户；本机 Chrome/Edge 受 DPAPI 应用绑定加密限制，已经验证可用的方式是 Firefox Cookie 或 Netscape cookies.txt。
- 播放列表逻辑、参数和本地 archive 已测试，但当前网络环境未完成 YouTube 完整播放列表的在线下载。
- HTTPS 代理参数路径已实现；没有可用的真实 TLS 代理服务器进行在线成功验证。
