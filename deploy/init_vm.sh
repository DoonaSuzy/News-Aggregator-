#!/usr/bin/env bash
# =============================================================================
# 目标 Ubuntu 虚拟机基础环境初始化
# 适用：Ubuntu 20.04/22.04/24.04（目标机 192.168.101.84，用户 zhu）
# 用法：在虚拟机上以具备 sudo 的用户执行  bash init_vm.sh
# 说明：安装 Docker + Compose 插件、开放必要端口、配置 SSH 免密登录（可选）
# =============================================================================
set -euo pipefail

log() { echo -e "\033[1;32m[init]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }

# 需要开放的端口（可用环境变量覆盖）
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
FLASK_PORT="${FLASK_PORT:-5000}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
REDIS_PORT="${REDIS_PORT:-6379}"
SSH_PORT="${SSH_PORT:-22}"

if [[ $EUID -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

# --- 1. 系统更新与基础工具 ---------------------------------------------------
log "更新 apt 索引并安装基础工具..."
$SUDO apt-get update -y
$SUDO apt-get install -y ca-certificates curl gnupg lsb-release ufw git

# --- 2. 安装 Docker（官方源）------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  log "Docker 已安装：$(docker --version)"
else
  log "安装 Docker Engine..."
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update -y
  $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  log "Docker 安装完成：$(docker --version)"
fi

# 将当前用户加入 docker 组（免 sudo 运行 docker）
if [[ -n "${SUDO:-}" ]]; then
  if ! id -nG "$USER" | grep -qw docker; then
    log "把 $USER 加入 docker 组（需重新登录生效）..."
    $SUDO usermod -aG docker "$USER"
    warn "请执行 'newgrp docker' 或重新登录后再运行 docker 命令。"
  fi
fi

# --- 3. 启动并开机自启 -------------------------------------------------------
log "启用 docker 服务..."
$SUDO systemctl enable docker
$SUDO systemctl start docker

# --- 4. 防火墙规则（ufw）-----------------------------------------------------
if command -v ufw >/dev/null 2>&1; then
  log "配置防火墙（开放 SSH/${FASTAPI_PORT}/${FLASK_PORT}）..."
  $SUDO ufw allow "${SSH_PORT}/tcp" || true
  $SUDO ufw allow "${FASTAPI_PORT}/tcp" || true
  $SUDO ufw allow "${FLASK_PORT}/tcp" || true
  # MySQL/Redis 默认不对公网开放（容器内网通信）；如需外部调试再手动放开：
  #   sudo ufw allow 3306/tcp
  #   sudo ufw allow 6379/tcp
  if ! $SUDO ufw status | grep -qw active; then
    warn "ufw 未激活。如需启用：sudo ufw enable"
  fi
fi

# --- 5. SSH 免密登录（可选）--------------------------------------------------
# 用法：本机已有 ~/.ssh/id_rsa.pub，执行：
#   ssh-copy-id -i ~/.ssh/id_rsa.pub zhu@192.168.101.84
# 若尚未生成密钥，可取消下面注释生成本机密钥对：
#   ssh-keygen -t ed25519 -C "newsagg-deploy"

log "基础环境初始化完成 ✅"
cat <<EOF

下一步：
  1) 确保 docker 可用（新组需重新登录）：  docker run --rm hello-world
  2) 配置免密登录（本机执行）：
       ssh-copy-id -i ~/.ssh/id_rsa.pub zhu@192.168.101.84
  3) 上传代码并部署：  见 deploy/deploy.sh

开放端口：SSH ${SSH_PORT}、FastAPI ${FASTAPI_PORT}、Flask ${FLASK_PORT}
EOF
