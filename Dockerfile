# ---- 省级采集镜像：只含采集层（newsagg），不含中台 ----
#
# 为什么单独一个镜像而不是复用中台镜像：
# 中台镜像里的 `newsagg` 是**另一套适配器框架**（BaseAdapter 继承体系），
# 与本仓库的 `SiteAdapter` Protocol 不兼容——两边 adapter_name 交集为 0，
# 用中台镜像根本认不出省级那 34 个源。在合并完成前，只能各跑各的。
#
# pip 走清华源：部署机在国内网络下直连 PyPI 会超时（与中台镜像同一处理）。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# 非 root 运行；固定 uid 便于挂载卷的属主对齐
RUN useradd -m -u 10001 appuser

WORKDIR /app

# 依赖先装（层缓存：改业务代码不触发重装）
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

COPY newsagg/ /app/newsagg/

RUN chown -R appuser:appuser /app
USER appuser

# 不写 HEALTHCHECK：本镜像只跑 CLI（coordinator / supervisor），
# 不监听端口，镜像级健康检查会永久 unhealthy（中台镜像踩过这个坑）。

# 默认打印状态；实际角色由 compose 的 command 覆盖
CMD ["python", "-m", "newsagg", "status"]
