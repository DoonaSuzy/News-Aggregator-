# 开发说明

## 已验证环境版本

| 组件 | 版本 | 验证日期 |
| --- | --- | --- |
| Python | 3.13.15 | 2026-10-09 |
| Scrapy | 2.19.0 | 2026-10-09 |
| Twisted | 26.4.0 | 2026-10-09 |
| MySQL | 8.4 | 2026-10-09 |
| Redis | 5.0.14（tporadowski） | 2026-10-09 |
| PyMySQL | 1.2.3 | 2026-10-09 |
| redis-py | 8.1.0 | 2026-10-09 |

## 安装步骤

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m newsagg init-db
.\.venv\Scripts\python.exe -m newsagg check
```

## 进程配合

```
计划任务 NewsAggCoordinator（每小时）
  └─> python -m newsagg coordinator
        ├─> MySQL: GET_LOCK + 建 crawl_jobs
        └─> Redis Stream: XADD job_id

计划任务 NewsAggSupervisor（登录时）
  └─> python -m newsagg supervisor
        ├─> python -m newsagg worker  (进程 1)
        └─> python -m newsagg worker  (进程 2)
              └─> classify_delivery → RUN → 子进程 run-job
```

## 时间与 URL 规则

- **时间窗口**：近 7 天 = 当天 + 前 6 个自然日（北京时间），非滚动 168 小时。
- **增量回看**：48 小时，夹在 7 天窗口内。
- **URL 规范化**：去片段、主机名小写、剔除 `utm_*`/spm/from/scene；未知参数保留。
- **文章身份**：`source_id` + `SHA-256(normalized_url)`。

## Scrapy 踩坑记录

1. **AsyncioSelectorReactor 在 Windows + Python 3.13 + Twisted 26.4.0 下导致 Scrapy 2.19 异步蜘蛛永久挂起**。解决方案：不安装任何反应器，交由 Twisted 默认 Windows 反应器。
2. **Scrapy 2.19 契约**：`Spider.start()` 必须是异步生成器（`spidermw.py` 的 `process_start` 校验 `__aiter__`）。
3. **Twisted 反应器不可在同一进程重启**，所以每个任务在独立子进程中运行。
4. **RobotsTxtMiddleware 在 Scrapy 层面关闭**，由 `AccessPolicyMiddleware` 统一处理。
5. **AutoThrottle 会覆盖自定义延迟**，`PaceMiddleware` 在每次响应后重置间隔。
6. **REDIRECT_ENABLED = False**，重定向由蜘蛛自行处理。
7. **Redis 协议兼容**：使用 `protocol=2`（RESP2）兼容 Redis 5.0。
8. **Redis 端口**：本机使用 6380（tporadowski Redis 5.0.14），非系统 6379 的 Memurai。
9. **PowerShell 子进程 stderr**：会被当错误，需用 Start-Process + 重定向文件。

## 适配器约定

- 每个来源一个文件，实现 `name`/`version`/`allowed_hosts`/`column_url`/`allows()`/`is_article()`/`parse_list()`/`parse_detail()`。
- 注册到 `adapters/__init__.py` 的 `_load_all()`。
- 来源字典加入 `db.py` 的 `CANDIDATE_SOURCES`。
- 贵州适配器额外有 `request_interval = 5`。

## 31 个启用来源

见 README §2.4 适配器状态表。

## 验收要求

- 单站至少核对 5 篇不同日期的文字新闻。
- 标题、正文段落、来源、时间、链接与当场打开的网页一致。
- `pytest -q` 全绿。
- 新适配器必须：实现方法 + 注册 + 测试用例。
