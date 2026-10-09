# newsagg —— 中国大陆 31 省官方新闻聚合工具

面向中国大陆 31 个省级行政区官方新闻站点的聚合爬虫工程。按“每省一个启用来源”的
设计增量抓取列表页 → 详情页，完成正文抽取、来源/时间归一化、去重落库，产出可导出的
结构化新闻数据。

> 定位：**教育 / 本地聚合用途**。遵守 `robots.txt`，控制抓取速率，仅抓取公开新闻内容。

---

## 1. 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 语言 | Python ≥ 3.11 | 推荐 3.13 |
| 解析 | `parsel` / Scrapy `Selector` | CSS + XPath |
| 队列 | Redis Stream（`redis-py` 8.x） | 消费组广播站点任务 |
| 存储 | MySQL 8.0（`PyMySQL`） | utf8mb4，墙钟时间 |
| 配置 | `python-dotenv` | `.env` 注入环境变量 |
| 测试 | `pytest` + `fakeredis` + `freezegun` | 无外部依赖单测 |

> 说明：项目核心为**自研的请求/解析/存储管线**（`newsagg.crawl` / `newsagg.adapters` /
> `newsagg.writer`），Scrapy 仅作为解析器与异步反应器底层被间接使用，便于精确控制
> 每站点的抓取预算与租约。

---

## 2. 架构与模块划分

```
scheduler ──┬─> MySQL(crawl_jobs)     建批 + 租约认领
            └─> Redis Stream(queue) ──> worker ──> SiteCrawler ──> MySQL(articles)
                                          │
                                          └─> classify 决定 run / wait / ack
```

| 模块 | 职责 |
| --- | --- |
| `newsagg/config.py` | 环境变量 → `Settings` 单例 |
| `newsagg/provinces.py` | 31 省行政区划代码表 |
| `newsagg/urls.py` | 各来源列表/详情 URL 归一化 |
| `newsagg/adapters/*` | 每站点解析器（34 个 adapter），共用 `base`/`_common`/`listing` |
| `newsagg/crawl/http.py` | 受控 HTTP 客户端（超时、UA、重试） |
| `newsagg/crawl/robots.py` | `robots.txt` 解析与遵守 |
| `newsagg/crawl/sampler.py` | 抓取速率 / 预算控制 |
| `newsagg/crawl/mimetypes.py` | 内容类型判定 |
| `newsagg/cleaning.py` | 标题/来源/正文清洗 + `content_hash` |
| `newsagg/timewindow.py` | 时间窗口、整点触发键、UTC/CST 归一化 |
| `newsagg/classify.py` | 投递决策（run / wait / ack） |
| `newsagg/scheduler.py` | 建批、分发、租约认领 |
| `newsagg/queue.py` | Redis Stream 封装 |
| `newsagg/worker.py` | 消费队列，驱动站点爬虫 |
| `newsagg/sitespider.py` | 单来源爬取主流程 |
| `newsagg/writer.py` | 文章去重落库 |
| `newsagg/recrawl.py` | 手动重抓 |
| `newsagg/export.py` | CSV 导出 |
| `newsagg/db.py` | 连接工厂、建表、省份/来源种子 |
| `newsagg/cli.py` | 命令行入口 |

**数据表**（`sql/schema.sql`）：`provinces` / `sources` / `source_slots` / `crawl_runs` /
`crawl_jobs` / `articles` / `article_tasks` / `job_attempts`。

**调度模型**：整点触发（`hourly_trigger_key`），自然日时间窗口；每省 1 个启用来源
对应 1 条启用槽（`source_slots`）；任务用 **5 分钟租约**（`lease_seconds`）认领，
配合事务断言令牌防止旧令牌篡改，超租约任务可被其它 worker 接管。

---

## 3. 环境要求与安装

### 3.1 前置工具

| 工具 | 版本 | 用途 |
| --- | --- | --- |
| Python | ≥ 3.11 | 运行时 |
| MySQL | ≥ 8.0 | 存储 |
| Redis | ≥ 5.0（需支持 `XADD`/Stream） | 队列 |

Windows 下可用项目自带脚本一键拉起本地 MySQL + Redis：

```powershell
pwsh scripts/start_services.ps1          # 启动
pwsh scripts/start_services.ps1 -Stop    # 停止
```

> 说明：脚本将 MySQL 数据目录放在无空格路径 `D:\newsagg_mysql_data`，Redis 用项目内置
> `.redis5` 原生 5.0.14 启动在 **6380**（系统 6379 的 Memurai 不含 `XADD`）。

### 3.2 安装 Python 依赖

```bash
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt # 运行 + 开发/测试依赖
# 或：pip install -e ".[dev]"
```

### 3.3 配置环境变量

```bash
cp .env.example .env            # 然后编辑 .env 填入 MySQL 密码
```

`.env` 关键项（默认值见 `newsagg/config.py`）：

```ini
NEWSAGG_MYSQL_HOST=127.0.0.1
NEWSAGG_MYSQL_PORT=3306
NEWSAGG_MYSQL_USER=newsagg
NEWSAGG_MYSQL_PASSWORD=        # 必填
NEWSAGG_MYSQL_DATABASE=newsagg
NEWSAGG_REDIS_URL=redis://127.0.0.1:6380/0
NEWSAGG_LOG_DIR=
NEWSAGG_WORKER_COUNT=2
```

### 3.4 初始化数据库

```bash
newsagg init-db      # 建表 + 写入 31 省与候选来源种子
newsagg selfcheck    # 校验 MySQL / Redis 连通性
```

---

## 4. 使用（CLI）

```bash
newsagg jobs                 # 建批并分发（整点调度入口）
newsagg run-worker           # 常驻 worker 消费 Stream（按 NEWSAGG_WORKER_COUNT 拉起）
newsagg tick                 # 单轮 调度 + 消费（供 cron 调用）
newsagg run-job <job_id>     # 单任务运行（不消费队列）
newsagg status               # 查看任务/队列概览
newsagg sources              # 列出所有来源与状态
newsagg recrawl <adapter> --days 7   # 手动重抓某来源
newsagg export --out out.csv # 导出文章 CSV
newsagg serve                # 前台 调度器 + worker（开发调试）
```

---

## 5. 测试

```bash
.\.venv\Scripts\python.exe -m pytest      # 93 个用例，无需外部 MySQL/Redis
```

测试覆盖：adapters 解析、清洗、时间窗口、省份/URL、分类、队列（`fakeredis`）。

---

## 6. 目录结构

```
newsagg/            主包
  adapters/         34 个省级站点解析器 + 公共基类
  crawl/            HTTP / robots / 速率 / mimetype
tests/              pytest 用例 + HTML 夹具
sql/schema.sql      建表脚本
scripts/            start_services.ps1 本地依赖启动
pyproject.toml      打包与依赖声明
requirements.txt    依赖锁定
.env.example        配置模板
```

---

## 7. 合规声明

本项目仅用于学习与本地数据聚合，请遵守目标站点 `robots.txt` 与相关法律法规，
合理控制抓取频率，勿用于商业转载或大规模抓取。
