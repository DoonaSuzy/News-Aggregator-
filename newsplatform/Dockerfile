# ---- FastAPI 核心服务镜像（多阶段构建）----
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 运行用户（非 root）
RUN useradd -m -u 10001 appuser

WORKDIR /app

# 先装依赖（利用层缓存）
COPY newsplatform/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

# 复制代码
COPY newsplatform/ /app/newsplatform/
COPY sql/platform_schema.sql /app/sql/platform_schema.sql

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查（存活探针）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"

# 生产用 gunicorn 管理 uvicorn worker，支持多 worker
CMD ["gunicorn", "newsplatform.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "2", "-b", "0.0.0.0:8000", \
     "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
