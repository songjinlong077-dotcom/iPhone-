$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $project '.venv\Scripts\python.exe'
$spec = Join-Path $project 'build_config\VideoDownloader.spec'
$dist = Join-Path $project '04_交付物'
$work = Join-Path $project '03_工作过程\pyinstaller_build'

& $python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work $spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败：$LASTEXITCODE" }

$bundle = Join-Path $dist 'Windows视频下载工具_v2.1'
Copy-Item -LiteralPath (Join-Path $project 'tools') -Destination $bundle -Recurse -Force
foreach ($name in @('config', 'logs', 'downloads')) {
    $target = Join-Path $bundle $name
    if (-not (Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Path $target | Out-Null }
}
$settings = Join-Path $project 'config\settings.json'
if (Test-Path -LiteralPath $settings) {
    Copy-Item -LiteralPath $settings -Destination (Join-Path $bundle 'config\settings.json') -Force
}
Copy-Item -LiteralPath (Join-Path $project 'README.md') -Destination $bundle -Force
Write-Output "BUILD_OK=$bundle"
