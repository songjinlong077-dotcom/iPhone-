# 第四版 GitHub Actions 与 IPA 打包配置验收记录

- 日期：2026-10-08
- 阶段：第五阶段配置
- 结果：工作流与打包脚本完成静态验证，等待首次 GitHub macOS 实跑
- 仓库可见性决策：公开仓库（用户于 2026-10-08 确认）

## 已完成

- `.github/workflows/ios-build.yml`
  - Ubuntu运行 FastAPI测试。
  - macOS 15安装 XcodeGen。
  - 动态选择可用 iPhone模拟器。
  - 运行 Swift单元测试。
  - 使用 iPhoneOS SDK构建 Release真机 App。
  - 关闭云端代码签名。
  - 上传 IPA、SHA-256和构建日志为 Artifact。
- `ios/scripts/build_unsigned_ipa.sh`
  - 校验主程序存在。
  - 使用 `lipo` 校验 arm64。
  - 移除可能残留的代码签名。
  - 创建 `Payload/*.app` IPA结构。
  - 使用 `unzip` 校验完整性和内容。
- 根目录 `.gitignore`
  - 排除密钥、Cookie路径、下载历史、视频、日志、虚拟环境、大型 Windows二进制和构建产物。
- 根目录 `.gitattributes`
  - 强制 Bash、YAML、Swift和 Python使用 LF，Windows批处理使用 CRLF。
- Windows端 Artifact下载说明。

## 静态验证结果

| 项目 | 结果 |
|---|---|
| GitHub Actions YAML解析 | 通过 |
| XcodeGen YAML解析 | 通过 |
| Job依赖关系 | `server-tests` 成功后才执行 `ios-build` |
| macOS Runner | `macos-15` |
| 官方 Actions | `checkout@v7`、`setup-python@v7`、`upload-artifact@v4` |
| 仓库权限 | 只读 `contents: read` |
| 并发控制 | 同分支新构建取消旧构建 |
| 超时 | 服务端15分钟，iOS 45分钟 |
| 嵌入凭据扫描 | 未发现 Apple ID、API Key或私钥 |
| Git暂存大文件 | 无超过 1 MiB的文件 |
| macOS脚本换行 | Git属性确认 `eol=lf` |
| Bash语法检查 | 当前 Windows没有 Bash，未执行 |
| 本地 Git仓库 | 已初始化 `codex/v4-ios` 分支并通过暂存清单检查 |
| macOS真实构建 | 尚未执行：没有 GitHub remote |

## 下一验收门

项目上传 GitHub后，必须取得一次全部绿色的 Workflow Run，并下载 Artifact确认其中包含：

- `VideoDownloader-v4-unsigned.ipa`
- `VideoDownloader-v4-unsigned.ipa.sha256`
- `xcode-version.txt`
- `simulator-test.log`
- `device-build.log`
- `device-architectures.txt`
- `ipa-integrity.txt`
- `ipa-contents.txt`

只有真实 macOS Runner通过后，才可进入 Windows/Sideloadly实机安装阶段。
