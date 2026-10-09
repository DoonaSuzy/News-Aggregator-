"""数据中台（platform）。

独立于爬虫 ``newsagg`` 的对外服务子系统：
- FastAPI 核心业务接口（异步、高并发）
- Flask 轻量管理后台
- 独立库 ``newsagg_platform``、独立缓存、独立环境变量前缀 ``PLATFORM_``
"""

__version__ = "0.1.0"
