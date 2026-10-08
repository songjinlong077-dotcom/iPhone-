# 第四版 GitHub Actions 与 IPA 打包配置验收记录

- 日期：2026-10-08
- 阶段：第五阶段配置
- 结果：通过；GitHub Actions 已真实生成并验证待重签 IPA
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
| 首轮 Workflow Run | `37780507771`：服务端测试导入了仓库根目录 `app.py`，失败；iOS Job 按依赖约束正确跳过 |
| 修复 | 服务端测试固定在 `server/` 工作目录，并使用 `PYTHONPATH=.`，避免同名模块遮蔽 |
| 第二轮 Workflow Run | `37781140867`：服务端 6/6 通过；Xcode 16.4 因中文 `PRODUCT_NAME` 与测试宿主路径不一致而失败 |
| 第二轮修复 | 移除内部产物名覆盖，保留 `CFBundleDisplayName=视频下载`，使 Xcode 测试宿主回到 `VideoDownloader.app/VideoDownloader` |
| 第三轮 Workflow Run | `37781627794`：Xcode 编译成功并执行 2 个测试；1 个通过，1 个因 `thumbnail_url` 到 `thumbnailURL` 的缩写映射失败 |
| 第三轮修复 | Codable 存储字段改为策略可识别的 `thumbnailUrl`，同时用计算属性保留界面侧 `thumbnailURL` API |
| 第四轮 Workflow Run | `37782960088`：两个 Job 全部成功 |
| FastAPI测试 | 6/6 通过 |
| Swift测试 | 2/2 通过，`TEST SUCCEEDED` |
| 真机架构 | `arm64` |
| IPA完整性 | ZIP无错误；包含 `Payload/VideoDownloader.app/Info.plist` 与主程序；不含 `_CodeSignature` |
| Artifact | `VideoDownloader-v4-ios-build`，ID `11553496265`，到期日 2026-10-22 |
| 本地交付目录 | `04_交付物\iOS_V4_GitHub_Run_37782960088` |
| IPA SHA-256 | `25affd86f3883270b5e2eb418bfa76587cfbbb38f85ff67cef8b4fa876c00138`，云端摘要与 Windows复算一致 |

## Artifact内容验收

项目上传 GitHub后，必须取得一次全部绿色的 Workflow Run，并下载 Artifact确认其中包含：

- `VideoDownloader-v4-unsigned.ipa`
- `VideoDownloader-v4-unsigned.ipa.sha256`
- `xcode-version.txt`
- `simulator-test.log`
- `device-build.log`
- `device-architectures.txt`
- `ipa-integrity.txt`
- `ipa-contents.txt`

上述文件均已下载并检查。现在可以进入 Windows/Sideloadly实机重签安装阶段；“可安装并正常启动”的最终结论仍须以用户自己的 iPhone 实机结果为准。
