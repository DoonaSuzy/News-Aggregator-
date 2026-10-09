#!/usr/bin/env bash
# =============================================================================
# 一键部署数据中台到目标虚拟机
# 用法（在虚拟机仓库根目录执行）：  bash deploy/deploy.sh
# 前置：已完成 init_vm.sh；当前目录为仓库根（含 newsplatform/ 与 sql/）
# 说明：生成 .env.platform → 构建并启动四容器 → 等待健康 → 输出访问信息
# =============================================================================
set -euo pipefail

log() { echo -e "\033[1;32m[deploy]\033[0m $*"; }
err() { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="newsplatform/.env.platform"
EXAMPLE="newsplatform/.env.platform.example"

# --- 1. 准备环境变量 ---------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  log "未发现 $ENV_FILE，从模板生成..."
  cp "$EXAMPLE" "$ENV_FILE"
  # 生成随机 JWT 密钥（长度 >= 32）
  JWT="$(openssl rand -hex 24 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d '\n')"
  # 生成随机数据库密码
  DBPWD="$(openssl rand -hex 16 2>/dev/null || head -c 24 /dev/urandom | base64 | tr -d '\n')"
  sed -i "s|^PLATFORM_JWT_SECRET=.*|PLATFORM_JWT_SECRET=${JWT}|" "$ENV_FILE"
  sed -i "s|^PLATFORM_DB_PASSWORD=.*|PLATFORM_DB_PASSWORD=${DBPWD}|" "$ENV_FILE"
  sed -i "s|^MYSQL_ROOT_PASSWORD=.*|MYSQL_ROOT_PASSWORD=${DBPWD}_root|" "$ENV_FILE"
  warn "已生成随机密码写入 $ENV_FILE（该文件勿提交版本库）。"
fi

# --- 2. 构建并启动 -----------------------------------------------------------
log "构建镜像并启动服务（首次可能较慢）..."
docker compose --env-file "$ENV_FILE" -f newsplatform/docker-compose.yml up -d --build

# --- 3. 等待健康 -------------------------------------------------------------
log "等待 FastAPI 就绪..."
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
FLASK_PORT="${FLASK_PORT:-5000}"
VM_IP="$(hostname -I | awk '{print $1}')"

for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${FASTAPI_PORT}/api/v1/health" >/dev/null 2>&1; then
    log "FastAPI 健康 ✅"
    break
  fi
  sleep 3
  [[ $i -eq 30 ]] && err "FastAPI 30 次探测仍未就绪，请检查：docker compose logs fastapi"
done

# --- 4. 输出访问信息 ---------------------------------------------------------
log "部署完成 ✅"
cat <<EOF

服务访问：
  FastAPI 文档(Swagger):  http://${VM_IP}:${FASTAPI_PORT}/docs
  FastAPI ReDoc:          http://${VM_IP}:${FASTAPI_PORT}/redoc
  Flask 管理后台:         http://${VM_IP}:${FLASK_PORT}/
  健康检查:               http://${VM_IP}:${FASTAPI_PORT}/api/v1/health

常用运维命令：
  查看日志:   docker compose -f newsplatform/docker-compose.yml logs -f
  查看状态:   docker compose -f newsplatform/docker-compose.yml ps
  停止:       docker compose -f newsplatform/docker-compose.yml down
  水平扩展:   docker compose -f newsplatform/docker-compose.yml up -d --scale fastapi=3
EOF
