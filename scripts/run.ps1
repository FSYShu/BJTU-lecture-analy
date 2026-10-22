# ============================================================
# 交大课录智析 · Windows 一体化脚本
#
# 用法：
#   powershell scripts/run.ps1              # 本地模式：初始化 + 启动（默认，无需 Docker）
#   powershell scripts/run.ps1 -Docker      # Docker 模式：初始化 + 容器部署
#   powershell scripts/run.ps1 -SetupOnly   # 仅环境初始化
#   powershell scripts/run.ps1 -SkipSetup   # 跳过初始化，直接启动/部署
# ============================================================

param(
    [switch]$Docker,
    [switch]$SetupOnly,
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
$WORK_DIR    = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$COMPOSE_FILE = "docker-compose.yml"
$HEALTH_URL   = "http://localhost:8000/api/v1/health"
$HEALTH_TIMEOUT = 180
$DB_PATH      = "storage/db/app.db"
$BACKUP_DIR   = "storage/db/backups"
$KEEP_BACKUPS = 10

Set-Location $WORK_DIR

# ---- 公共函数 ----
function Format-FileSize($size) {
    if ($size -ge 1MB) { "{0:N1}MB" -f ($size / 1MB) }
    elseif ($size -ge 1KB) { "{0:N1}KB" -f ($size / 1KB) }
    else { "$size B" }
}
function Write-Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)       { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg)     { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-Err($msg)      { Write-Host "  ✗ $msg" -ForegroundColor Red }
function Update-EnvVar($file, $key, $value) {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    $lines = [System.IO.File]::ReadAllText($file, $utf8) -split "`r?`n"
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^#?\s*$key=") { $lines[$i] = "$key=$value"; $found = $true; break }
    }
    if (-not $found) { $lines += "$key=$value" }
    [System.IO.File]::WriteAllText($file, ($lines -join "`n") + "`n", $utf8)
}

$gitHash = (git rev-parse --short HEAD 2>$null)
$gitMsg  = (git log -1 --format='%s' 2>$null)
$modeLabel = if ($Docker) { "Docker 容器" } else { "本地直跑" }

Write-Host "============================================================" -ForegroundColor White
Write-Host "  交大课录智析 · $modeLabel模式 · $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor White
Write-Host "  工作目录: $WORK_DIR" -ForegroundColor White
Write-Host "  Git: $gitHash $gitMsg" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White

# ============================================================
# 阶段一：环境初始化
# ============================================================
if (-not $SkipSetup) {
    Write-Host "`n========== 阶段一：环境初始化 ==========" -ForegroundColor Magenta

    if ($Docker) {
        # ---- Docker 模式初始化 ----
        Write-Step "1/4" "检查 Docker Desktop..."
        $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
        if ($dockerCmd) {
            Write-Ok "Docker 已安装"
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Docker 引擎未运行，尝试启动..."
                $ddPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
                if (Test-Path $ddPath) {
                    Start-Process $ddPath
                    Write-Host "  等待启动..." -NoNewline
                    $deadline = (Get-Date).AddSeconds(120)
                    while ((Get-Date) -lt $deadline) {
                        docker info 2>$null | Out-Null
                        if ($LASTEXITCODE -eq 0) { break }
                        Start-Sleep 3; Write-Host -NoNewline "."
                    }
                    Write-Host ""
                    docker info 2>$null | Out-Null
                    if ($LASTEXITCODE -eq 0) { Write-Ok "引擎已启动" }
                    else { Write-Err "启动超时，请手动启动"; exit 1 }
                } else { Write-Err "未找到 Docker Desktop"; exit 1 }
            } else { Write-Ok "引擎运行中" }
        } else {
            Write-Warn "Docker 未安装"
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Write-Err "winget 不可用"; exit 1 }
            if ((Read-Host "  winget 安装 Docker Desktop？(y/N)") -eq "y") {
                winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
                Write-Warn "请重启电脑后重新运行"; exit 0
            } else { exit 0 }
        }

        Write-Step "2/4" "配置镜像加速器..."
        $daemonJsonPath = "$env:USERPROFILE\.docker\daemon.json"
        $mirror = "https://docker.1panel.live"
        $needConfig = $true
        if (Test-Path $daemonJsonPath) {
            try { $d = Get-Content $daemonJsonPath -Raw | ConvertFrom-Json; if ($d.'registry-mirrors' -contains $mirror) { Write-Ok "已配置"; $needConfig = $false } } catch {}
        }
        if ($needConfig -and (Read-Host "  配置 $mirror (Y/n)") -ne "n") {
            if (Test-Path $daemonJsonPath) { $d = Get-Content $daemonJsonPath -Raw | ConvertFrom-Json } else { $d = @{} }
            $d | Add-Member -NotePropertyName 'registry-mirrors' -NotePropertyValue @($mirror) -Force
            $d | ConvertTo-Json -Depth 10 | Set-Content $daemonJsonPath -Encoding UTF8
            Write-Ok "已写入"; Write-Warn "请在 Docker Desktop 中 Apply & Restart"
            if ((Read-Host "  已重启？(y/N)") -ne "y") { exit 0 }
        }
    } else {
        # ---- 本地模式初始化 ----
        Write-Step "1/6" "检查 Python 3.12+..."
        $pyCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pyCmd) {
            $pyVer = (python --version 2>&1).ToString()
            Write-Ok $pyVer
            if ($pyVer -notmatch "3\.1[2-9]") { Write-Err "需要 Python 3.12+，当前 $pyVer"; exit 1 }
        } else {
            Write-Warn "Python 未安装"
            if ((Read-Host "  winget 安装 Python 3.12？(y/N)") -eq "y") {
                winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
                Write-Warn "请重新打开终端后重新运行"; exit 0
            } else { Write-Err "Python 是必须依赖"; exit 1 }
        }

        Write-Step "2/6" "检查 uv + 后端依赖..."
        $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uvCmd) {
            $uvLocal = Join-Path $env:USERPROFILE ".local\bin"
            if (Test-Path (Join-Path $uvLocal "uv.exe")) {
                $env:Path = "$uvLocal;$env:Path"
                $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
            }
        }
        if (-not $uvCmd) {
            Write-Warn "uv 未安装，正在安装..."
            powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
            $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        }
        Write-Ok "uv $(uv --version 2>&1)"
        $env:UV_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
        Write-Ok "PyPI 镜像: 清华"
        Push-Location "$WORK_DIR\backend"
        uv sync --python 3.12 --frozen --dev
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "尝试安装 Python 3.12..."
            uv python install 3.12
            uv sync --python 3.12 --frozen --dev
        }
        if ($LASTEXITCODE -ne 0) { Write-Err "后端依赖安装失败"; Pop-Location; exit 1 }
        Pop-Location
        Write-Ok "后端依赖已安装（Python 3.12）"

        Write-Step "3/6" "检查 Node.js 20+ + 前端依赖..."
        $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
        if ($nodeCmd) {
            $nodeVer = (node --version 2>&1).ToString()
            Write-Ok "Node $nodeVer"
            if ($nodeVer -notmatch "v2[0-9]") { Write-Warn "建议 Node 20+，当前 $nodeVer" }
        } else {
            Write-Warn "Node.js 未安装"
            if ((Read-Host "  winget 安装 Node.js LTS？(y/N)") -eq "y") {
                winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
                Write-Warn "请重新打开终端后重新运行"; exit 0
            } else { Write-Err "Node.js 是必须依赖"; exit 1 }
        }
        if (-not (Test-Path "$WORK_DIR\frontend\node_modules")) {
            Push-Location "$WORK_DIR\frontend"
            npm config set registry https://registry.npmmirror.com
            npm install
            if ($LASTEXITCODE -ne 0) { Write-Err "前端依赖安装失败"; Pop-Location; exit 1 }
            Pop-Location
            Write-Ok "前端依赖已安装"
        } else { Write-Ok "前端依赖已存在" }

        Write-Step "4/6" "检查 ffmpeg..."
        $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
        if ($ffmpeg) { Write-Ok "ffmpeg 已安装" }
        else {
            Write-Warn "ffmpeg 未安装"
            if ((Read-Host "  winget 安装 ffmpeg？(y/N)") -eq "y") {
                winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
                Write-Warn "请重新打开终端后重新运行"; exit 0
            } else { Write-Warn "跳过（音视频处理功能将不可用）" }
        }

        Write-Step "5/6" "安装 Playwright Chromium..."
        Push-Location "$WORK_DIR\backend"
        uv run playwright install chromium
        Pop-Location
        Write-Ok "Playwright Chromium 已安装"
    }

    # ---- 公共：配置 .env + API Key ----
    $stepEnv = if ($Docker) { "3/4" } else { "6/6" }
    Write-Step $stepEnv "配置 .env..."
    $envPath = Join-Path $WORK_DIR ".env"
    $envExamplePath = Join-Path $WORK_DIR ".env.example"
    $needApiKeys = $true
    if (Test-Path $envPath) {
        if ((Read-Host "  .env 已存在，覆盖？(y/N)") -eq "y") { Copy-Item $envExamplePath $envPath -Force; Write-Ok ".env 已覆盖" }
        else { Write-Warn "保留现有 .env，跳过 API Key 填入"; $needApiKeys = $false }
    } else { Copy-Item $envExamplePath $envPath; Write-Ok ".env 已创建" }

    if ($needApiKeys) {
        Write-Host ""
        Write-Host "  填入 API Key（回车跳过可选项）" -ForegroundColor Cyan

        Write-Host "`n  硅基流动 API Key（必填）" -ForegroundColor White
        Write-Host "  获取: https://cloud.siliconflow.cn/account/ak" -ForegroundColor DarkGray
        $sfKey = ""
        while (-not $sfKey) { $sfKey = Read-Host "  SILICONFLOW_API_KEY"; if (-not $sfKey) { Write-Warn "必填项" } }
        Update-EnvVar $envPath "SILICONFLOW_API_KEY" $sfKey
        Write-Ok "SILICONFLOW_API_KEY 已填入"

        if ($envVal -eq "prod") {
            Update-EnvVar $envPath "CORS_ORIGINS" "http://localhost:3000,http://127.0.0.1:3000"
            Write-Ok "CORS 已调整为生产环境"
        }
    }

    Write-Host ""
    Write-Host "  ✅ 环境初始化完成" -ForegroundColor Green
    if ($SetupOnly) {
        $next = if ($Docker) { "powershell scripts/run.ps1 -Docker -SkipSetup" } else { "powershell scripts/run.ps1 -SkipSetup" }
        Write-Host "`n  下一步: $next" -ForegroundColor White
        exit 0
    }
}

# ============================================================
# 阶段二：启动 / 部署
# ============================================================

if ($Docker) {
    Write-Host "`n========== 阶段二：Docker 部署 ==========" -ForegroundColor Magenta

    Write-Step "1/5" "备份 SQLite..."
    if (Test-Path $DB_PATH) {
        New-Item -ItemType Directory -Force -Path $BACKUP_DIR | Out-Null
        $backup = Join-Path $BACKUP_DIR "app.db.$(Get-Date -Format 'yyyyMMdd_HHmmss').bak"
        $sqlite3 = Get-Command sqlite3 -ErrorAction SilentlyContinue
        if ($sqlite3) { & sqlite3 $DB_PATH ".backup '$backup'" } else { Copy-Item $DB_PATH $backup -Force }
        Write-Ok "已备份 ($((Format-FileSize (Get-Item $backup).Length)))"
        Get-ChildItem (Join-Path $BACKUP_DIR "app.db.*.bak") -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -Skip $KEEP_BACKUPS | Remove-Item -Force -ErrorAction SilentlyContinue
    } else { Write-Warn "首次部署，跳过备份" }

    Write-Step "2/5" "记录容器状态..."
    $oldId = (docker compose -f $COMPOSE_FILE ps -q backend 2>$null)
    if ($oldId -and $oldId.Trim()) { Write-Ok "当前容器: $($oldId.Trim().Substring(0,12))" }
    else { Write-Warn "首次部署" }

    Write-Step "3/5" "构建镜像..."
    docker compose -f $COMPOSE_FILE build --progress=plain 2>&1 | Select-Object -Last 5
    if ($LASTEXITCODE -ne 0) { Write-Err "构建失败"; exit 1 }
    Write-Ok "构建完成"

    Write-Step "4/5" "启动容器..."
    docker compose -f $COMPOSE_FILE up -d --remove-orphans
    if ($LASTEXITCODE -ne 0) { Write-Err "启动失败"; exit 1 }
    Write-Ok "容器已启动"

    Write-Step "5/5" "健康检查..."
    $deadline = (Get-Date).AddSeconds($HEALTH_TIMEOUT)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        try { Invoke-RestMethod -Uri $HEALTH_URL -TimeoutSec 5 -ErrorAction Stop | Out-Null; $healthy = $true; break }
        catch { Start-Sleep 3; Write-Host -NoNewline "." }
    }
    Write-Host ""
    if ($healthy) {
        Write-Host "`n  ✅ 部署成功！" -ForegroundColor Green
        Write-Host "  后端: http://localhost:8000/api/v1  前端: http://localhost:3000" -ForegroundColor Green
        docker image prune -f 2>$null | Out-Null
    } else {
        Write-Host "`n  ❌ 健康检查超时！" -ForegroundColor Red
        docker compose -f $COMPOSE_FILE logs --tail=30 backend 2>$null
        Write-Host "  回滚: git revert HEAD; powershell scripts/run.ps1 -Docker -SkipSetup"
        exit 1
    }
} else {
    Write-Host "`n========== 阶段二：本地启动 ==========" -ForegroundColor Magenta

    $logDir = Join-Path $WORK_DIR "storage\logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $backendDir = Join-Path $WORK_DIR "backend"
    $frontendDir = Join-Path $WORK_DIR "frontend"

    $backendLog = Join-Path $logDir "backend.log"
    $frontendLog = Join-Path $logDir "frontend.log"
    if (Test-Path $backendLog) { Clear-Content $backendLog }
    if (Test-Path $frontendLog) { Clear-Content $frontendLog }

    Write-Step "1/2" "启动后端（后台静默）..."
    $backendProc = Start-Process -FilePath "cmd" -ArgumentList "/c", "uv run python run.py 2>&1" `
        -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $backendLog
    Write-Ok "后端 PID=$($backendProc.Id) (http://localhost:8000)"

    Write-Step "2/2" "启动前端（后台静默）..."
    $frontendProc = Start-Process -FilePath "cmd" -ArgumentList "/c", "npm run dev 2>&1" `
        -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $frontendLog
    Write-Ok "前端 PID=$($frontendProc.Id) (http://localhost:5173)"

    Write-Host ""
    Write-Host "  等待后端就绪..." -NoNewline
    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try { Invoke-RestMethod -Uri $HEALTH_URL -TimeoutSec 3 -ErrorAction Stop | Out-Null; $ready = $true; break }
        catch { Start-Sleep 2; Write-Host -NoNewline "." }
    }
    Write-Host ""

    Write-Host "============================================================" -ForegroundColor Green
    if ($ready) { Write-Host "  ✅ 后端已就绪！" -ForegroundColor Green }
    else { Write-Host "  ! 后端仍在启动中" -ForegroundColor Yellow }
    Write-Host "  后端 API: http://localhost:8000/api/v1   (文档 /docs)" -ForegroundColor Green
    Write-Host "  前端页面: http://localhost:5173" -ForegroundColor Green
    Write-Host "  日志: $backendLog / $frontendLog" -ForegroundColor DarkGray
    Write-Host "============================================================" -ForegroundColor Green

    $bkPos = 0; $fePos = 0
    try {
        Write-Host "`n  服务运行中，按 Ctrl+C 停止所有服务" -ForegroundColor Cyan
        Write-Host "  实时日志（[后端]蓝色 / [前端]紫色）`n" -ForegroundColor DarkGray
        while ($true) {
            if ($backendProc.HasExited -and $frontendProc.HasExited) { break }
            if (Test-Path $backendLog) {
                $lines = Get-Content $backendLog -ErrorAction SilentlyContinue
                if ($lines -and $lines.Count -gt $bkPos) {
                    for ($i = $bkPos; $i -lt $lines.Count; $i++) {
                        Write-Host "[后端] " -ForegroundColor Blue -NoNewline
                        Write-Host $lines[$i] -ForegroundColor Gray
                    }
                    $bkPos = $lines.Count
                }
            }
            if (Test-Path $frontendLog) {
                $lines = Get-Content $frontendLog -ErrorAction SilentlyContinue
                if ($lines -and $lines.Count -gt $fePos) {
                    for ($i = $fePos; $i -lt $lines.Count; $i++) {
                        Write-Host "[前端] " -ForegroundColor Magenta -NoNewline
                        Write-Host $lines[$i] -ForegroundColor Gray
                    }
                    $fePos = $lines.Count
                }
            }
            Start-Sleep -Milliseconds 500
        }
    } finally {
        Write-Host "`n  正在停止服务..." -ForegroundColor Yellow
        if ($backendProc -and -not $backendProc.HasExited) { taskkill /PID $backendProc.Id /T /F 2>$null; Write-Ok "后端已停止" }
        if ($frontendProc -and -not $frontendProc.HasExited) { taskkill /PID $frontendProc.Id /T /F 2>$null; Write-Ok "前端已停止" }
        Write-Host "  服务已全部停止" -ForegroundColor Green
    }
}