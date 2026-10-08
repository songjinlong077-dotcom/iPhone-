# Video Downloader V4 FastAPI 服务端

## 本地启动

```powershell
cd 'D:\workspace\projects\Project002_Windows视频下载工具\server'
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:VIDEO_API_KEY='请替换为至少16位随机密钥'
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

除 `GET /health` 外，接口必须携带 `Authorization: Bearer <VIDEO_API_KEY>`。

## 测试

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 安全说明

- API Key 仅从环境变量读取，仓库不保存真实密钥。
- 拒绝本机、内网、保留 IP、带凭据 URL 和非 HTTP(S) URL。
- 任务使用独立目录，并限制并发数、文件大小和保留时间。
- 当前 DNS 校验是第一道 SSRF 防线；生产部署还应在容器/防火墙层阻止访问云元数据和内网网段。
- 只处理用户有权下载、平台允许访问且不受 DRM 保护的内容。
