#!/usr/bin/env bash
# =============================================================================
# 部署后健康检查：连通性 + 接口可用性 + 容器状态
# 用法：bash deploy/healthcheck.sh [host]  （默认 127.0.0.1）
# =============================================================================
set -uo pipefail

HOST="${1:-127.0.0.1}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
FLASK_PORT="${FLASK_PORT:-5000}"
BASE="http://${HOST}:${FASTAPI_PORT}"

pass=0; fail=0
check() { # name, url, [expect_substr]
  local name="$1" url="$2" expect="${3:-}"
  local code body
  body="$(curl -fsS --max-time 8 "$url" 2>/dev/null)"; code=$?
  if [[ $code -eq 0 ]] && { [[ -z "$expect" ]] || echo "$body" | grep -q "$expect"; }; then
    echo "  ✅ $name"; pass=$((pass+1))
  else
    echo "  ❌ $name  (url=$url)"; fail=$((fail+1))
  fi
}

echo "== HTTP 接口 =="
check "存活探针 /health"        "${BASE}/api/v1/health"        "alive"
check "就绪探针 /health/ready"   "${BASE}/api/v1/health/ready"  "ready"
check "OpenAPI 文档"            "${BASE}/openapi.json"         "paths"
check "文章列表 /articles"       "${BASE}/api/v1/articles"      "meta"
check "省份覆盖 /provinces"      "${BASE}/api/v1/provinces"     "北京"
check "来源列表 /sources"        "${BASE}/api/v1/sources"       "adapter_name"
check "总览统计 /stats/overview" "${BASE}/api/v1/stats/overview" "total_articles"
check "Flask 后台 /healthz"      "http://${HOST}:${FLASK_PORT}/healthz" "alive"

echo "== 容器状态 =="
if command -v docker >/dev/null 2>&1; then
  docker compose -f newsplatform/docker-compose.yml ps --format \
    "table {{.Service}}\t{{.Status}}" 2>/dev/null || docker ps --format "table {{.Names}}\t{{.Status}}"
else
  echo "  (docker 不在 PATH，跳过)"
fi

echo ""
echo "结果：通过 ${pass}，失败 ${fail}"
[[ $fail -eq 0 ]] && echo "🎉 全部健康检查通过" || echo "⚠️  存在失败项，请检查日志：docker compose logs -f"
