# GitHub 云端编译与 IPA 下载说明

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

## 失败排查

- `FastAPI tests` 失败：先查看 Python测试输出。
- XcodeGen失败：检查 `ios/project.yml`。
- Swift编译或测试失败：下载 Artifact 内的 `simulator-test.log`。
- 真机构建失败：查看 `device-build.log`。
- IPA校验失败：查看 `ipa-integrity.txt`、`ipa-contents.txt` 和 `device-architectures.txt`。
