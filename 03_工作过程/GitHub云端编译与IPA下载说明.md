# GitHub 云端编译与 IPA 下载说明

## 已验证构建

- 成功运行：[GitHub Actions Run 37782960088](https://github.com/songjinlong077-dotcom/iPhone-/actions/runs/37782960088)
- 分支：`codex/v4-ios`
- Artifact：`VideoDownloader-v4-ios-build`（ID `11553496265`，GitHub显示 2026-10-22 到期）
- 本机交付目录：`D:\workspace\projects\Project002_Windows视频下载工具\04_交付物\iOS_V4_GitHub_Run_37782960088`
- IPA SHA-256：`25affd86f3883270b5e2eb418bfa76587cfbbb38f85ff67cef8b4fa876c00138`

## 前提

项目必须先上传到 GitHub 仓库。不要提交真实 API Key、Apple ID、Cookie、下载历史、视频文件、虚拟环境或本机工具目录；根目录 `.gitignore` 已排除这些内容。

## 触发编译

1. 打开 GitHub 仓库。
2. 进入 **Actions**。
3. 选择 **Build iOS IPA**。
4. 点击 **Run workflow**。
5. 等待 `FastAPI tests` 与 `Test and build unsigned IPA` 两个 Job 变为绿色。

推送 `ios/`、`server/` 或工作流文件的改动也会自动触发。

## 工作流执行内容

1. Ubuntu Runner 运行 FastAPI 自动化测试。
2. macOS Runner 安装 XcodeGen并生成 `.xcodeproj`。
3. 动态选择可用 iPhone模拟器并运行 Swift单元测试。
4. 使用 iPhoneOS SDK构建 Release真机 App，关闭云端代码签名。
5. 检查 App主程序包含 `arm64`。
6. 生成 `Payload/*.app` 结构的待重签 IPA。
7. 校验 ZIP完整性、IPA内容和 SHA-256。
8. 上传 IPA、摘要与构建日志为 Artifact。

## Windows 下载

1. 打开成功的 Workflow Run。
2. 在页面底部找到 **Artifacts**。
3. 下载 `VideoDownloader-v4-ios-build`。
4. 解压 GitHub 下载的 ZIP。
5. 得到 `VideoDownloader-v4-unsigned.ipa` 和对应 `.sha256`。

该 IPA 尚未具备可安装签名。下一阶段必须由 Windows 上的 Sideloadly 使用用户自己的 Apple账号重签后安装到 iPhone。

## Windows 使用 Sideloadly 安装

1. 只从 [Sideloadly 官网](https://sideloadly.io/) 下载 Windows版。按官网当前要求，Windows需使用 Apple官网提供的网页版 iTunes 与 iCloud，而不是 Microsoft Store版。
2. 用数据线连接 iPhone，解锁手机；若出现“要信任此电脑吗”，选择信任并输入锁屏密码。
3. 打开 Sideloadly，确认设备下拉框已识别你的 iPhone。
4. 将 `VideoDownloader-v4-unsigned.ipa` 拖入 Sideloadly，输入你自己的 Apple账号，然后点击 **Start**。不要把 Apple账号、密码或验证码发给任何人，也不要写入仓库。
5. 安装完成后，如系统要求，前往“设置 → 隐私与安全性 → 开发者模式”，打开后按提示重启并再次确认。
6. 如首次启动提示开发者不受信任，前往“设置 → 通用 → VPN与设备管理”，选择对应 Apple账号并信任/验证；验证时保持联网。
7. 返回主屏幕打开“视频下载”。免费账号签名通常仅有效 7 天，需要在到期前用 Sideloadly重新签名；官网当前提供自动刷新功能，但要求 Windows和设备满足其连接条件。

注意：IPA安装成功不等于云端下载服务已经部署。首次使用前还需在 App“设置”中填写可公网访问的 HTTPS 服务端地址和至少 16 位 API Key；当前服务端部署仍是下一阶段工作。

参考：Sideloadly 官网说明免费账号有效期及 Windows依赖；Apple Developer 文档说明“开发者模式”；Apple支持文档说明手动安装 App 的信任与联网验证步骤。

## 失败排查

- `FastAPI tests` 失败：先查看 Python测试输出。
- XcodeGen失败：检查 `ios/project.yml`。
- Swift编译或测试失败：下载 Artifact 内的 `simulator-test.log`。
- 真机构建失败：查看 `device-build.log`。
- IPA校验失败：查看 `ipa-integrity.txt`、`ipa-contents.txt` 和 `device-architectures.txt`。
