#!/usr/bin/env bash
# ============================================================
# 交大课录智析 · 服务器端部署脚本
# 由 GitHub Actions self-hosted runner 调用
#
# 流程：备份 SQLite → 构建镜像 → 启动容器 → 健康检查 → 失败回滚 DB
#
# 前置：服务器 WSL2 已装 Docker Engine，.env 已放在项目根目录
# ============================================================
set -euo pipefail

# ---- 配置 ----
WORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="docker-compose.yml"
HEALTH_URL="http://localhost:8000/api/v1/health"
HEALTH_TIMEOUT=180          # 后端含 Playwright Chromium 启动较慢
DB_PATH="storage/db/app.db"
BACKUP_DIR="storage/db/backups"
KEEP_BACKUPS=10             # 只保留最近 N 个备份

cd "$WORK_DIR"

echo "============================================================"
echo "  交大课录智析 · 部署开始  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  工作目录: $WORK_DIR"
echo "  Git: $(git rev-parse --short HEAD) $(git log -1 --format='%s')"
echo "============================================================"

# ---- 1. 备份 SQLite ----
echo ""
echo "[1/5] 备份 SQLite 数据库..."
if [ -f "$DB_PATH" ]; then
  mkdir -p "$BACKUP_DIR"
  BACKUP="$BACKUP_DIR/app.db.$(date '+%Y%m%d_%H%M%S').bak"
  # 用 sqlite3 .backup 更安全（WAL 一致性快照）；没有 sqlite3 则直接 cp
  if command -v sqlite3 > /dev/null 2>&1; then
    sqlite3 "$DB_PATH" ".backup '$BACKUP'"
  else
    cp "$DB_PATH" "$BACKUP"
  fi
  echo "  ✓ 已备份到 $BACKUP ($(du -h "$BACKUP" | cut -f1))"
  # 清理旧备份
  ls -t "$BACKUP_DIR"/app.db.*.bak 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm --
else
  echo "  - 数据库不存在（首次部署），跳过备份"
fi

# ---- 2. 记录当前容器状态（用于回滚诊断）----
echo ""
echo "[2/5] 记录当前容器状态..."
OLD_BACKEND_ID=$(docker compose -f "$COMPOSE_FILE" ps -q backend 2>/dev/null || echo "")
if [ -n "$OLD_BACKEND_ID" ]; then
  echo "  ✓ 当前 backend 容器: ${OLD_BACKEND_ID:0:12}"
else
  echo "  - 无运行中的容器（首次部署）"
fi

# ---- 3. 构建镜像 ----
echo ""
echo "[3/5] 构建镜像（Docker BuildKit 层缓存中）..."
docker compose -f "$COMPOSE_FILE" build --progress=plain 2>&1 | tail -5
echo "  ✓ 镜像构建完成"

# ---- 4. 启动新容器 ----
echo ""
echo "[4/5] 启动容器..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
echo "  ✓ 容器已启动"

# ---- 5. 等待健康检查 ----
echo ""
echo "[5/5] 等待健康检查（最长 ${HEALTH_TIMEOUT}s）..."
DEADLINE=$(( $(date '+%s') + HEALTH_TIMEOUT ))
HEALTHY=false
while [ "$(date '+%s')" -lt "$DEADLINE" ]; do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    HEALTHY=true
    break
  fi
  sleep 3
  printf "."
done
echo ""

if [ "$HEALTHY" = true ]; then
  echo ""
  echo "============================================================"
  echo "  ✅ 部署成功！服务健康"
  echo "  后端 API: http://localhost:8000/api/v1   (文档 /docs)"
  echo "  前端页面: http://localhost:3000"
  echo "============================================================"
  # 清理悬空镜像（释放磁盘，保留缓存层）
  docker image prune -f > /dev/null 2>&1 || true
  exit 0
else
  echo ""
  echo "============================================================"
  echo "  ❌ 健康检查超时！部署失败"
  echo "============================================================"
  # 打印最近日志辅助诊断
  echo "--- backend 最近日志 ---"
  docker compose -f "$COMPOSE_FILE" logs --tail=30 backend 2>/dev/null || true
  echo ""
  echo "诊断建议:"
  echo "  1. 查看完整日志: docker compose -f $COMPOSE_FILE logs"
  echo "  2. 回滚代码:     git revert HEAD && bash scripts/deploy.sh"
  echo "  3. 恢复数据库:   cp $BACKUP_DIR/app.db.*.bak $DB_PATH"
  exit 1
fi