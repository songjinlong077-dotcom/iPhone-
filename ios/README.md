# Video Downloader V4 iOS 客户端

这是原生 SwiftUI 客户端，不是网页或 PWA。最低系统版本为 iOS 16。

## 已实现源码

- HTTPS 服务器地址与 API Key 设置。
- API Key 使用 iPhone Keychain 保存。
- 视频 URL 解析、缩略图、平台、作者、时长和清晰度展示。
- 最高画质/兼容 MP4、云端任务创建、进度轮询、取消和重试。
- 历史任务列表。
- 将完成文件导出到系统文件 App。
- 请求相册追加权限并保存兼容视频。

## 生成 Xcode 工程

项目使用 `project.yml` 作为可审计的 XcodeGen 配置。macOS 环境执行：

```bash
brew install xcodegen
cd ios
xcodegen generate
xcodebuild -project VideoDownloader.xcodeproj -scheme VideoDownloader -destination 'platform=iOS Simulator,name=iPhone 16' test
```

Windows 不生成或伪造 `.xcodeproj`；下一阶段由 GitHub Actions 的 macOS Runner 生成工程、编译和执行测试。

## 使用前设置

App 内填写部署后的 HTTPS API 根地址和至少 16 位 API Key。客户端不内置真实服务器地址或密钥。
