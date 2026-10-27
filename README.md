# 中国大陆31省官方新闻聚合工具（News Aggregator）

采集中国大陆 31 个省级行政区的官方新闻：每个省启用 1 家「稿源名单」上的新闻网站、1 个地方新闻栏目，采集「标题、正文纯文本、发布时间、原文来源、原文链接」五类字段。正文与元数据落库到 MySQL，任务队列走 Redis Stream。

> 定位：**教育 / 本地聚合用途**。遵守 `robots.txt`，控制抓取速率，仅抓取公开新闻内容。

> ⚠️ **2026-10-27 起：对外接口已并入电力中台**
>
> 本仓库继续负责**采集**（`newsagg`）与**数据落库**（`newsagg_platform`），
> 但 `/api/v1/*` 不再由本项目对外提供——文章 / 来源 / 省份查询已收敛到
> `Power News Aggregator`，用 `channel=province` 指定本数据域。
> 本文中「数据中台（v0.2.0）」一节描述的是**合并前的旧契约**，仅作历史参考；
> 新契约见 `Power News Aggregator/docs/数据域合并与channel说明.md`。
> **不要同时对外暴露本项目的 `/docs`**：两套文档路径同名、语义不同。

---

## 技术栈

| 组件 | 版本 / 说明 |
| --- | --- |
| 语言 | Python ≥ 3.11（使用 `zoneinfo`；Scrapy 2.19 的异步蜘蛛入口 `async start()`） |
| 爬虫框架 | Scrapy 2.19（真实爬虫引擎） |
| 关系数据库 | MySQL 8.0/8.4，库字符集 `utf8mb4`，独立账号，勿用 root 运行应用 |
| 队列 | Redis（本机开发用 tporadowski Redis 5.0.14，端口 6380），Redis Stream + 消费组 |
| 驱动 | PyMySQL、redis-py |
| 配置 | python-dotenv（读取 `.env`） |
| 时区 | tzdata |
| 测试 | pytest |
| **数据中台（v0.2.0）** | **FastAPI**（异步接口）+ **Flask**（管理后台）+ **Docker/Compose**（容器化编排） |

> 说明：采集层基于 **Scrapy Spider**（`newsagg.crawl.spider`，`async start()` 异步入口），由 `crawl/settings.py` 配置并发 8、AutoThrottle 与限流槽，两个自定义中间件（`AccessPolicyMiddleware`/`PaceMiddleware`）负责 robots 决策与站点限速。每站点的抓取预算与 MySQL 租约由 `crawl/session.py` 精确控制。数据中台层（`newsplatform/`，v0.2.0 新增）基于 FastAPI + Flask + Docker，见 §3。

---

## 1. 目录结构

```
News Aggregator/
├── newsagg/                     # 主程序包，入口 python -m newsagg
│   ├── adapters/                # 34 个站点的解析规则（一源一文件）
│   ├── crawl/                   # Scrapy 蜘蛛、采集会话、下载策略
│   │   ├── spider.py            # SiteSpider：async start() 入口
│   │   ├── session.py           # CrawlSession：租约续期、布隆、窗口判定
│   │   ├── engine.py            # open_session / run_blocking / conclude
│   │   ├── settings.py          # scrapy_settings()：并发8、重试2、关Cookie
│   │   ├── middlewares.py       # AccessPolicyMiddleware / PaceMiddleware
│   │   ├── dedup.py             # UrlBloom（Redis 位图布隆）+ 跨源去重
│   │   ├── sampler.py           # 失败页样本落盘
│   │   └── mimetypes.py         # 非文本页检测
│   ├── cli.py                   # 命令行入口（20 个子命令）
│   ├── config.py                # 环境变量与 Settings
│   ├── db.py                    # 建表、种子来源、连接工厂
│   ├── repo.py                  # 全部 SQL 读写（租约、任务、文章）
│   ├── schedule.py              # 协调器：按小时建批、发布任务
│   ├── worker.py                # 工作进程主循环（领任务→抓取→结束）
│   ├── queue.py                 # Redis Stream 队列封装
│   ├── query.py                 # 文章检索（省份/日期/关键词/分页）
│   ├── export.py                # CSV 导出
│   ├── stats.py                 # 采集统计与逐来源状态
│   ├── cleaning.py              # 标题/来源/正文清洗 + 时间解析
│   ├── timewindow.py            # 时间窗口、整点触发键
│   ├── classify.py              # 投递决策（run/wait/ack）
│   ├── provinces.py             # 31 省行政区划代码表
│   ├── urls.py                  # URL 规范化与稳定哈希
│   ├── logutil.py               # 日志配置（文件轮转 + 控制台）
│   ├── errors.py                # 自定义异常
│   └── supervisor.py            # 常驻监督，维持 worker 池
├── sql/schema.sql               # 8 张表的建表语句（爬虫库 newsagg）
├── sql/platform_schema.sql      # 数据中台独立库建表（newsagg_platform）
├── tests/                       # 单元测试 + HTML 夹具
├── scripts/                     # 运维 / 诊断 / 修复脚本（见 §8）
├── deploy/                      # 数据中台一键部署脚本（init_vm/deploy/healthcheck）
├── newsplatform/                # 数据中台子系统（FastAPI+Flask+Docker，见 §3）
│   ├── main.py                  # FastAPI 入口（uvicorn/gunicorn）
│   ├── core/                    # 配置/数据库/响应/异常/鉴权/限流/日志
│   ├── api/v1/                  # 接入层路由（articles/sources/provinces/auth/health）
│   ├── services/                # 业务服务层
│   ├── repositories/            # 数据访问层（async SQLAlchemy）
│   ├── models/orm.py            # 中台 ORM（独立库表）
│   ├── admin/                   # Flask 管理后台
│   ├── Dockerfile               # FastAPI 镜像
│   ├── Dockerfile.flask         # Flask 镜像
│   ├── docker-compose.yml       # 四容器编排（fastapi/flask/mysql/redis）
│   └── requirements.txt         # 中台专属依赖
├── docs/                        # 设计文档、开发说明、采集报告、部署运维手册、上下文交接
├── pyproject.toml               # 包定义、依赖、pytest 配置
├── requirements.txt             # 锁定版本
├── .env.example                 # 环境变量模板
└── .gitignore
```

运行时还会生成 `logs/`（日志、失败页样本、CSV 导出）与 `.env`（本机密码），两者均不提交。

---

## 2. 逐文件说明

### 2.1 根目录

| 文件 | 说明 |
| --- | --- |
| `pyproject.toml` | 包名 `newsagg` 0.1.0，要求 Python ≥ 3.11；依赖 scrapy / redis / PyMySQL / python-dotenv / tzdata；dev 额外依赖 pytest；注册控制台脚本 `newsagg=newsagg.cli:main`；pytest `testpaths=["tests"]` |
| `requirements.txt` | 锁定版本：scrapy 2.19.0、redis 8.1.0、PyMySQL 1.2.3、python-dotenv 1.2.4、tzdata 2026.5、pytest 9.1.1 |
| `.env.example` | 6 个环境变量模板，复制为 `.env` 后填密码 |
| `.gitignore` | 忽略 `.venv/`、`.env`、`logs/`、`__pycache__/`、`.pytest_cache/`、`dist/`、`build/` 等 |

### 2.2 顶层模块 `newsagg/`

| 文件 | 职责 |
| --- | --- |
| `__init__.py` | 定义 `__version__`；不安装任何反应器（交由 Twisted 默认 Windows 反应器） |
| `__main__.py` | `python -m newsagg` 的入口，调用 `cli.main()` |
| `cli.py` | 全部命令行子命令：环境初始化、协调器、工作进程、查询、导出、统计、重采 |
| `config.py` | `project_root()` 定位项目根（可用 `NEWSAGG_ROOT` 覆盖）、自动 `load_dotenv`；`Settings` 数据类含 MySQL/Redis 连接、日志目录、worker 数、租约与预算默认值 |
| `db.py` | `Database` 连接工厂（utf8mb4、DictCursor、`SET time_zone='+00:00'`）；`init_database()` 执行 `sql/schema.sql` 并写入种子；`CANDIDATE_SOURCES` 定义 34 个候选来源；`ping()` 返回版本与字符集 |
| `repo.py` | 全部持久化逻辑：`get_source`、`insert_run`/`finish_run`、`create_job`/`find_open_job`、`acquire_lease`/`renew_lease`、`upsert_discovered`、`save_article`、`mark_task`、`finish_job`、`enable_source`/`resume_source`、`pause_source`/`set_cooldown` 等 |
| `schedule.py` | `run_coordinator()` 用 MySQL `GET_LOCK('newsagg_coordinator')` 保证同一小时只建一次批；`schedule_source()` 生成或复用任务；`publish_jobs()` 用 `GET_LOCK('newsagg_publish')` 投递到 Redis；`create_manual_job()` 供手动命令使用 |
| `worker.py` | Twisted reactor 主循环：`take_assignment()` 依次读 pending、`autoclaim` 新消息，经 `classify_delivery()` 判定 run/wait/ack；调用 `crawl/engine.py` 开会话、跑 SiteSpider、收尾 |
| `queue.py` | Redis Stream 封装。流名 `newsagg:site_jobs`，消费组 `newsagg-workers`；`ensure_group`、`publish`、`ack`、`read_new`、`read_pending`、`autoclaim`、`message_pending` |
| `classify.py` | `classify_delivery()`：终态/未到重试时间的任务 ack；租约有效但属他人则 wait；否则 run |
| `timewindow.py` | 北京时间窗口计算。`build_window()`：首次或当天首次 7 天 `full_rescan`，否则回看 48 小时且夹在 7 天内 `incremental`；`hourly_trigger_key()`、`classify_moment()`、`to_cst_naive`/`to_utc_naive` |
| `cleaning.py` | 清洗与时间解析：`clean_title`、`clean_source`、`clean_paragraphs`、`parse_published`（6 种时间格式，输出精度 second/minute/date/unknown）、`content_hash`、`quality_flags`、`csv_cell`（防 CSV 公式注入） |
| `urls.py` | `normalize_url()`：去片段、主机名小写、剔除 `utm_*`/spm/from/scene；`url_hash()` 为规范化 URL 的 SHA-256 |
| `query.py` | 文章检索：`search_articles()`（省份/日期/关键词/时间未知筛选 + 分页）、`matching_ids`、`fetch_ids`、`get_article`、`parse_day`、`format_cst`、`flags_text` |
| `export.py` | `export_csv()`：按查询条件导出 UTF-8 BOM CSV，12 列中文表头，单元格经 `csv_cell` 转义 |
| `stats.py` | `collect_stats()` + `render_stats()`：启用来源数、正文有效/日期确认/五字段完整数、完整率、待处理积压，逐来源输出状态、文章数、最近任务与停止原因 |
| `provinces.py` | 31 个省级行政区代码与名称；`NAME_TO_CODE`/`CODE_TO_NAME`；`resolve_province()` 支持代码或名称输入 |
| `logutil.py` | `setup_logging()`：`newsagg` logger 输出到 `logs/newsagg.log`（按天轮转，保留 14 份）与控制台；`configure_stdio()` 强制 UTF-8 |
| `errors.py` | 自定义异常：`LeaseRejected`（旧令牌）、`LeaseBusy`（他人重试持有租约）、`JobTerminal`（任务已终态）、`NotDue`（重试未到） |
| `supervisor.py` | `supervise()`：常驻监督，维持 `worker_count`（默认 2）个 `python -m newsagg worker` 子进程，退出后自动重启 |

### 2.3 采集子包 `newsagg/crawl/`

| 文件 | 职责 |
| --- | --- |
| `spider.py` | `SiteSpider`：`async start()` 是真实入口（Scrapy 2.13+ 必须），同时保留 `start_requests()`；`parse_list` 翻页 + 落库候选，`parse_detail` 处理重定向/404/410/非文本/解析失败、多页正文拼接；`_guard()` 在租约丢失、被封、超预算时关闭蜘蛛；`on_error` 分类失败原因并写失败页样本 |
| `session.py` | `CrawlSession`：一次任务的全部运行时状态。租约续期线程（默认 5 分钟租约、60 秒续租）、列表检查点读写、候选去重与窗口判定、`store_detail()` 落库、`fail_task()`、`note_block()`（403/405/412/429 触发停机与冷却）、`decide()` 产出终态与重试分钟数、`apply_block_policy()` |
| `engine.py` | `worker_identity()`（主机名+PID）；`open_session()` 取租约并构造会话；`conclude()` 提交结果后才 XACK；`run_blocking()` 供 `crawl-once` 同步跑；`runner()` 返回 `CrawlerRunner` |
| `settings.py` | `scrapy_settings()`：并发 8、`DOWNLOAD_TIMEOUT` 30、AutoThrottle（目标并发 8，最大延迟 60）、关 Cookie、重试 2 次（500/502/503/504/522/524/408）、关闭 Scrapy 重定向中间件、注册两个自定义中间件、`DOWNLOAD_SLOTS` 给 guizhou 单独限流 |
| `middlewares.py` | `AccessPolicyMiddleware`（560）：放行 robots.txt 本身，页面返回 403/405/412/429 则记录阻断并 `closeSpider`；`PaceMiddleware`（590）：把指定来源固定到独立下载槽，每次响应后把间隔设回，防止 AutoThrottle 改短 |
| `__init__.py` | 空 |

### 2.4 适配器子包 `newsagg/adapters/`

一个来源一个文件。`base.py` 定义数据结构与协议：`ListItem`、`ListParse`、`DetailParse`、`SiteAdapter`（含 `allowed_hosts`、`parse_list`、`parse_detail`）。`listing.py` 提供 `mark_sticky()`（识别置顶稿）与 `is_descending()`（判断列表是否倒序）。`__init__.py` 是注册表，`get_adapter(name)` 按名字返回实例，未注册抛 `KeyError`。

共 34 个适配器（其中 31 个已启用，3 个为备用候选）。下表以代码为准，与设计文档第 15 节一致。

| 省级行政区 | 媒体 | 适配器 | 状态 |
| --- | --- | --- | --- |
| 北京 | 千龙网 | `beijing` | 启用 |
| 天津 | 今晚网 | `jinwan` | 启用 |
| 天津 | 北方网 | `tianjin` | 候选（原「天津要闻」已停更） |
| 河北 | 河北新闻网 | `hebei` | 启用 |
| 山西 | 黄河新闻网 | `shanxi` | 启用 |
| 内蒙古 | 正北方网 | `neimenggu` | 启用 |
| 辽宁 | 东北新闻网 | `liaoning` | 启用 |
| 吉林 | 中国吉林网 | `jilin` | 启用 |
| 黑龙江 | 黑龙江新闻网 | `heilongjiang` | 启用 |
| 上海 | 劳动报 | `laodong` | 启用 |
| 江苏 | 中国江苏网 | `jiangsu` | 启用 |
| 浙江 | 浙江在线 | `zhejiang` | 启用 |
| 安徽 | 安徽新闻网 | `anhui` | 启用 |
| 福建 | 东南网 | `fujian` | 启用 |
| 江西 | 大江网 | `jiangxi` | 启用 |
| 山东 | 大众网 | `shandong` | 启用 |
| 河南 | 大河网 | `henan` | 启用 |
| 湖北 | 长江网 | `changjiang` | 启用 |
| 湖北 | 荆楚网 | `hubei` | 候选 |
| 湖南 | 红网 | `hunan` | 启用 |
| 广东 | 南方网 | `guangdong` | 启用 |
| 广西 | 广西网络广播电视台 | `gxtv` | 启用 |
| 海南 | 南海网 | `hainan` | 启用 |
| 重庆 | 华龙网 | `chongqing` | 启用 |
| 四川 | 四川新闻网 | `sichuan` | 启用 |
| 贵州 | 当代先锋网 | `guizhou` | 启用（单独限流 5 秒，忽略 robots） |
| 云南 | 云南网 | `yunnan` | 启用 |
| 西藏 | 中国西藏新闻网 | `xizang` | 启用 |
| 陕西 | 华商网 | `shaanxi` | 启用 |
| 甘肃 | 每日甘肃网 | `gansudaily` | 启用 |
| 甘肃 | 中国甘肃网 | `gansu` | 候选 |
| 青海 | 青海新闻网 | `qinghai` | 启用 |
| 宁夏 | 银川新闻网 | `ningxia` | 启用 |
| 新疆 | 新疆网 | `xinjiang` | 启用 |

适配器类需具备：`name`（等于 `sources.adapter_name`）、`version`、`allowed_hosts`、`column_url`、`allows()`、`is_article()`、`parse_list()`、`parse_detail()`。贵州适配器额外有 `request_interval = 5`。

### 2.5 SQL `sql/`

`schema.sql` 定义 8 张表。运行时刻字段写 UTC 墙钟，带 `_cst` 的是北京时间墙钟，不随会话时区换算。

| 表 | 作用 | 关键字段/约束 |
| --- | --- | --- |
| `provinces` | 31 个省级行政区 | `code` 主键 |
| `sources` | 来源站点 | 唯一键 `adapter_name`；`verification_status` 枚举 candidate/verified/enabled/paused；租约（`lease_token`/`lease_owner`/`lease_until_utc`）、冷却、暂停原因、最近发现/全扫时间 |
| `source_slots` | 每省只保留一个启用槽 | `province_code` 主键 |
| `crawl_runs` | 每小时批次 | 唯一键 `trigger_key` |
| `crawl_jobs` | 站点任务 | 唯一键 `(source_id, trigger_key, job_type)`；`job_type` 枚举 incremental/full_rescan/manual_recrawl；`status` 枚举 queued/running/succeeded/partial/failed/retry_wait；计数与检查点 |
| `articles` | 正文与元数据 | 唯一键 `(source_id, url_hash)`；`time_precision` 枚举 unknown/date/minute/second；`quality_flags` JSON |
| `article_tasks` | 详情页待抓队列 | 唯一键 `(source_id, discovered_url_hash)`；状态、跳过原因、重试时间、失败分类 |
| `job_attempts` | 每次尝试的审计 | 唯一键 `(job_id, attempt_no)`；`log_path` 指向失败页样本 |

### 2.6 测试 `tests/`

| 文件 | 说明 |
| --- | --- |
| `test_adapters.py` | 适配器注册表、fujian 夹具解析、通用逻辑 |
| `test_classify.py` | `classify_delivery` 投递决策 |
| `test_cleaning.py` | 清洗、时间解析、CSV 公式前缀转义 |
| `test_dedup.py` | URL 布隆去重 |
| `test_provinces_urls.py` | 省份解析、URL 规范化 |
| `test_queue.py` | Redis Stream 队列操作（fakeredis） |
| `test_repository.py` | 全部 SQL 契约（假连接） |
| `test_timewindow.py` | 时间窗口计算 |
| `test_query.py` | 文章检索、分页、过滤条件 |
| `test_export.py` | CSV 导出、筛选、格式 |
| `test_cli.py` | 命令行参数解析、dispatch |
| `fixtures/` | HTML 夹具：fujian_list/detail |

所有测试可离线运行，无需外部 MySQL/Redis 依赖。

### 2.7 脚本 `scripts/`

`register_tasks.ps1`：注册两个 Windows 计划任务。因为路径含空格，脚本先取 Python 的 8.3 短路径再交给 `schtasks`。

- `NewsAggCoordinator` —— 每小时执行 `python -m newsagg coordinator`
- `NewsAggSupervisor` —— 登录时执行 `python -m newsagg supervisor`；无权限时打印手动启动命令

### 2.8 文档 `docs/`

| 文件 | 说明 |
| --- | --- |
| `development.md` | 开发说明：已验证环境版本、安装步骤、进程配合、时间与 URL 规则、Scrapy 踩坑记录、适配器约定、31 个启用来源及篇数、验收要求 |
| `superpowers/specs/2026-10-03-provincial-news-aggregator-design.md` | 首版设计文档，设计约定以此为准 |
| `research/2026-10-09-31-province-source-candidates.md` | 31 省来源候选的初始核验记录 |

---

## 3. 数据流

每小时 Windows 计划任务 `NewsAggCoordinator` → `python -m newsagg coordinator`：

- `GET_LOCK('newsagg_coordinator')`，同一小时不重复建批
- 为每个已启用来源生成/复用一条 `crawl_jobs`
- `publish_jobs()` 投递 `job_id` → Redis Stream `newsagg:site_jobs`

登录后或手动 `python -m newsagg supervisor`：

- 维持 2 个 `python -m newsagg worker`
  - 消费组 `newsagg-workers`，一个进程一次领一个站点任务
  - `acquire_lease`（MySQL 租约）→ SiteSpider 抓列表与详情 → 文章写入 `articles` → `finish_job` → XACK

关键约定：

- Redis 消息在 MySQL 提交成功后才 XACK；重复投递靠 `(source_id, url_hash)` 唯一键挡住。
- 同一站点的执行权在 MySQL 租约里（5 分钟，每 60 秒续租）。写文章、推进检查点、结束任务时核对 `lease_token`，旧进程的过期令牌不能覆盖结果。
- 任务状态 `queued → running → succeeded / partial / failed`，重试等待为 `retry_wait`。`succeeded` 表示列表发现已结束；`partial` 表示保存了一部分但不能说已采满 7 天。

---

## 3A. 数据中台（v0.2.0 新增）

采集层把文章写入爬虫库 `newsagg`；**数据中台**是独立的对外服务子系统（`newsplatform/`），用独立库 `newsagg_platform`、独立缓存、独立环境变量前缀 `PLATFORM_`，与爬虫解耦。爬虫数据通过 `scripts/export_platform_data.py` 一次性 ETL 导入，或后续由爬虫经接口/直连持续同步。

### 架构与分工

| 组件 | 容器 | 端口 | 框架 | 职责 |
|------|------|------|------|------|
| 核心接口服务 | `newsagg-fastapi` | 8000 | FastAPI + Uvicorn(Gunicorn) | 文章/来源/省份/统计/鉴权，异步高并发 |
| 管理后台 | `newsagg-flask` | 5000 | Flask + Gunicorn | 来源状态看板、采集概览 |
| 数据库 | `newsagg-mysql` | 3306(内网) | MySQL 8.4 | 独立库 `newsagg_platform` |
| 缓存/限流 | `newsagg-redis` | 6379(内网) | Redis 7 | 缓存与计数 |

分层：**接入层** `api/v1/`（路由+参数校验）→ **服务层** `services/`（业务编排）→ **数据访问层** `repositories/`（async SQLAlchemy）→ **模型层** `models/orm.py`；横切能力在 `core/`：统一响应信封、全局异常、JWT 鉴权、slowapi 限流、request_id 结构化日志。

### 统一响应与鉴权

所有接口返回统一信封：

```json
{ "code": 0, "message": "ok", "data": {}, "request_id": "ab12cd34", "timestamp": "2026-10-10T03:00:00+00:00" }
```

错误码对齐 HTTP 语义（400/401/404/429/500/503）；每个响应带 `X-Request-ID`。登录 `POST /api/v1/auth/login`（开发环境播种 `admin/admin123`）获取 Bearer 令牌。

### 对外接口（自动文档）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` `/health/ready` | 存活 / 就绪探针 |
| POST | `/api/v1/auth/login` | 登录获取 JWT |
| GET | `/api/v1/articles` | 文章列表（省份/来源/关键词/日期/分页） |
| GET | `/api/v1/articles/{id}` | 文章详情（含正文） |
| GET | `/api/v1/provinces` | 31 省覆盖与计数 |
| GET | `/api/v1/sources` | 来源列表 |
| GET | `/api/v1/stats/overview` | 总览统计 |

接口文档由 FastAPI 原生 OpenAPI 自动生成：`/docs`（Swagger UI）、`/redoc`、`/openapi.json`，全部对外接口自动纳入。

### 部署（Docker Compose）

```bash
# 虚拟机初始化（装 Docker/Compose、防火墙、SSH 免密引导）
sudo bash deploy/init_vm.sh
# 一键部署四容器（生成随机密码的 .env.platform → 构建 → 启动 → 健康检查）
sudo bash deploy/deploy.sh
# 连通性 + 接口 + 容器健康验证
sudo bash deploy/healthcheck.sh 127.0.0.1
```

详见 `docs/数据中台部署运维手册.md`。pip 用清华源、Docker 用镜像加速器，适配国内网络。

### 数据接入

- **一次性 ETL**：本机 `python scripts/export_platform_data.py -o newsagg_platform_import.sql` 从爬虫库导出中台格式 SQL，上传后在容器内 `mysql ... newsagg_platform < newsagg_platform_import.sql` 导入。
- **持续同步**：可扩展爬虫侧在采集完结后直连中台库 `newsagg_mysql_data`/容器写入，或新增 `POST` 写入接口 + `ingest_batches` 留痕。

---

## 4. 安装与运行

### 4.1 环境准备

需要 Python 3.11+（用到 `zoneinfo` 与 Scrapy 2.19 的异步蜘蛛入口）、MySQL 8.0（库字符集 utf8mb4）、Redis 兼容服务。
MySQL 使用独立库与账号，不要用 root 跑应用。

`.env`（从 `.env.example` 复制，密码只放这里）：

```ini
NEWSAGG_MYSQL_HOST=127.0.0.1
NEWSAGG_MYSQL_PORT=3306
NEWSAGG_MYSQL_USER=newsagg
NEWSAGG_MYSQL_PASSWORD=
NEWSAGG_MYSQL_DATABASE=newsagg
NEWSAGG_REDIS_URL=redis://127.0.0.1:6380/0
NEWSAGG_LOG_DIR=
```

账号需要能在 `newsagg` 库建表、读写、执行 `GET_LOCK`。

### 4.2 首次跑通

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # 填好数据库密码
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m newsagg init-db
.\.venv\Scripts\python.exe -m newsagg check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m newsagg crawl-once --adapter jiangsu
.\.venv\Scripts\python.exe -m newsagg query --province 江苏
.\.venv\Scripts\python.exe -m newsagg stats
```

`init-db` 执行 `sql/schema.sql`，写入 31 个省级行政区，并按 `db.py` 的 `CANDIDATE_SOURCES` 插入尚不存在的来源；已存在的 `adapter_name` 不会被覆盖。

### 4.3 命令行

| 子命令 | 说明 |
| --- | --- |
| `init-db` | 建表并写入省份与候选来源 |
| `check` | 检查 MySQL 与 Redis 连通性 |
| `coordinator` | 安排一轮站点任务（每小时一次） |
| `jobs` | 建批并分发（同 coordinator） |
| `worker` | 运行一个采集工作进程 |
| `run-worker` | 前台拉起 NEWSAGG_WORKER_COUNT 个 worker |
| `supervisor` | 保持 2 个工作进程运行 |
| `tick` | 单轮 建批 + 消费（供 cron 调用） |
| `crawl-once <job_id> [--refresh]` | 同步跑单任务 |
| `crawl-once --adapter X [--refresh]` | 按 adapter 新建任务并立即抓取 |
| `run-job <job_id> [--refresh]` | 单任务运行（不消费队列） |
| `status` | 查看任务/队列概览 |
| `sources` | 列出所有来源与状态 |
| `enable-source <adapter>` | 验收通过后启用来源 |
| `resume-source <adapter>` | 清除暂停与冷却 |
| `query` | 查询文章，支持 `--province`、`--from`、`--to`、`--keyword`、`--body-only`、`--unknown-time`、`--page`、`--page-size` |
| `show <article_id>` | 查看单篇文章详情与正文 |
| `export --out PATH` | 按查询条件导出 CSV |
| `stats` | 采集统计 |
| `recrawl <adapter> --days 7` | 手动重抓某来源 |
| `recrawl <adapter> --from YYYY-MM-DD --to YYYY-MM-DD` | 按日期重查正文 |
| `serve` | 前台 协调器 + worker（开发调试） |

示例：

```powershell
python -m newsagg export --province 江苏 --from 2026-09-28 --to 2026-10-03 --out logs\jiangsu.csv
```

CSV 使用 UTF-8 BOM，以 `=`、`+`、`-`、`@` 开头的单元格会加前缀，避免被表格软件当成公式。

---

## 5. 时间与 URL 规则

- 近 7 天是北京时间的「任务建立当天 + 前面 6 个自然日」，不是滚动 168 小时。窗口在建任务时冻结。例如 2026-10-03 15:00 建的任务，窗口是 2026-09-27 00:00 至 2026-10-03 15:00。
- 每天第一次触发做 7 天列表回扫（full rescan）；同日后续触发做增量（incremental），从上次成功发现时间往前看 48 小时，且不早于当前 7 天起点。列表发现未完成时，不推进 `last_discovery_success_at_utc`。
- 文章身份是来源 id + 规范化 URL 的 SHA-256。规范化只做：去片段、主机名小写、删 `utm_*`/spm/from/scene；未知查询参数保留，不改 http/https。
- 正文时间优先于列表时间。只有日期的稿件 `published_at_cst` 为空，精度记 `date`。纯图片、纯视频、无实质文字的直播页记 `non_text_content` 并跳过，不进 `articles`。

---

## 6. 接入新来源

1. 打开首页，确认标题或页脚就是稿源名单上的那一家。
2. 只跟随页面里真实出现、文字指向本省新闻的链接（全国要闻、央视外链、电视节目页不算）。
3. 用真实详情页确认标题、正文段落、来源、时间。
4. 在 `newsagg/adapters/` 新建文件，实现 `name` / `version` / `allowed_hosts` / `column_url` / `allows()` / `is_article()` / `parse_list()` / `parse_detail()`；注册到 `adapters/__init__.py`；把来源字典加到 `db.py` 的 `CANDIDATE_SOURCES`。
5. `init-db`，再 `crawl-once --adapter 名称`。
6. 库里有文章且抽查与网页一致后，才 `enable-source`。同一省只保留一个启用槽（`source_slots`）。

换源时保留原候选行，新建另一个 `adapter_name`，不要把未通过的站当作已启用。

单站验收：至少核对 5 篇不同日期的文字新闻，标题、正文段落、来源、时间、链接都要与当场打开的网页一致。夹具测试不能代替这一步。

---

## 7. 已知注意点

- 江苏要闻的嵌入列表到不了窗口第一天 0 点，任务保持 partial；该站正文由 JS 注入，
  纯 HTTP 抓到的是模板壳页，用 `scripts/render_harvest.py` 渲染补齐。
- 重庆栏目页没有更早的历史入口，可见范围从当次列表最旧一条算起。
- 贵州当代先锋网（`www.ddxfw.cn`）的「贵州」列表被自身 robots.txt 禁止，按要求仍
  采集该栏并单独限流 5 秒/并发 1（`DOWNLOAD_SLOTS`）。**本机实测 http/https 均
  `RemoteDisconnected` 不可达**，任务会空跑结束，恢复可达后无需改代码。
- 江西大江网需 `DEFAULT:@SECLEVEL=1` 的 TLS 套件才能握手（证书仍校验）。已由适配器
  的 `tls_ciphers` 声明、引擎在**该来源的任务进程内**下发
  `DOWNLOADER_CLIENT_TLS_CIPHERS`，其余来源仍用 OpenSSL 默认套件。
- 青海栏目 https 会 302 到 http，栏目地址直接写返回 200 的 http 地址。
  该站部分稿件是**纯视频稿**（正文区只有 `<video>`），无文字属正常，不是解析失败。
- 上海用劳动报站内 shsldb 稿件；上观新闻静态页只有模板占位符。
- 海南南海网的列表与正文都在 `rm-nhwapp-1.hinews.cn/v_page.html?newsId=` 上由 JS 注入，
  需渲染采集；广西广电（gxtv）同理，多数稿件是视频稿。
- 四川 `world.newssc.org` 的详情页是 266 字节的 JS 跳转壳，真实稿件在新华
  `h.xinhuaxmt.com`；蜘蛛会跟随一层 JS 跳转后再解析。
- 单栏目页候选太少（十来条）的来源，用适配器的 `extra_column_urls` 追加同站频道
  （要闻/时政/本地…），爬虫会把它们一起当作起始页。
- User-Agent：`newsagg/0.1 (educational local aggregator)`（诊断脚本另用 Chrome UA）。

---

## 8. 测试与健康检查

### 8.1 单元测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

所有测试可离线运行，无需外部 MySQL/Redis 依赖。

### 8.2 健康检查脚本

| 脚本 | 说明 |
| --- | --- |
| `simple_health_check.py` | 基础 4 项检查：MySQL、Redis、来源数、队列积压 |
| `system_health_check.py` | 扩展检查：逐省来源明细、停用原因、队列采样 |

```powershell
.\.venv\Scripts\python.exe simple_health_check.py
.\.venv\Scripts\python.exe system_health_check.py
```

---

## 9. 参考文档

- `docs/设计文档-省级新闻聚合.md` —— 首版设计；来源清单权威版本，已按代码校准
- `docs/development.md` —— 开发说明与启用来源整理时篇数
- `docs/采集链路修复与全量采集报告-2026-10-09.md` —— 采集链路修复与全量采集报告
- `docs/数据中台部署运维手册.md` —— 数据中台（FastAPI+Flask+Docker）部署与运维
- `docs/上下文交接-2026-10-09.md` —— 上下文交接（接手参考）
- `docs/爬虫修复工作包.md` / `docs/CONTEXT_HANDOFF.md` —— 历史修复工作包与早期交接

来源名称对照国家网信办 2025 版互联网新闻信息稿源单位名单：
[2025版互联网新闻信息稿源单位名单_中央网络安全和信息化委员会](https://www.cac.gov.cn/2025-08/14/c_1756886951643180.htm)
