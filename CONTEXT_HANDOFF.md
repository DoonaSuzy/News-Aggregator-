# 项目上下文交接文档（CONTEXT_HANDOFF）

> **用途**：供任何接手本项目的 agent 或开发者快速获得完整上下文。
> 接手指令：*「先读本文件，然后继续开发」*
> 最后更新：2026-10-09

---

## 一、项目定位

中国大陆 **31 个省级行政区** 官方新闻聚合工具。每省一个启用媒体源
（`source_slots` 唯一槽位），定时抓取列表页 + 详情页，文章落库 MySQL，
支持查询、导出 CSV、统计。

---

## 二、技术栈（已实测验证落地）

| 组件 | 版本/说明 | 落点 |
|------|-----------|------|
| Python | 3.11+（本机 3.13.15） | pyproject |
| Scrapy | 2.19.0（真实爬虫引擎） | newsagg/crawl/ |
| Twisted | 26.4.0（默认 Windows 反应器） | — |
| PyMySQL | DictCursor | newsagg/db.py |
| redis-py | 8.1，Stream 队列（protocol=2 兼容 Redis 5.0） | newsagg/queue.py |
| MySQL | 8.0/8.4，7 表，utf8mb4 | sql/schema.sql |
| Redis | 本机 tporadowski Redis 5.0.14（非文档措辞的 Memurai） | .redis5/ |

五类字段（标题/正文/时间/来源/链接）+ 每省一启用槽均已实现。

---

## 三、⚠️ 关键平台结论（必读，勿回退）

**Windows + Python 3.13 + Twisted 26.4.0 下，`AsyncioSelectorReactor` 会让
Scrapy 2.19 的异步蜘蛛 `async start()` 永久挂起**（事件循环未与 Twisted
对接，首请求永不调度；反应器空转）。

诊断定位链（已在最小化冒烟测试中逐层隔离证实）：
1. `requests` 直抓正常 → 网络/解析层无问题
2. `async start()` + asyncio 反应器 → 挂死
3. `async start()` + **默认反应器** → 完整成功（200，85KB）

**修复**（勿回退）：
- `newsagg/__init__.py`：不安装任何反应器，交由 Twisted 默认 Windows 反应器
- `newsagg/crawl/settings.py`：**不覆盖 `TWISTED_REACTOR`**

同时确认 Scrapy 2.19 契约：`Spider.start()` 必须是**异步生成器**
（`spidermw.py` 的 `process_start` 校验 `__aiter__`）。

---

## 四、去重能力（已实现）

1. **URL 指纹去重**：`normalize_url()`（去 utm/spm/from/scene、小写主机、
   去片段）+ SHA-256 → 唯一键 `uk_articles_source_hash(source_id, url_hash)`
2. **布隆过滤器**（`newsagg/crawl/dedup.py`）：Redis 位图
   `SETBIT/GETBIT`，跨任务运行期 URL 快速判重；由
   `engine.open_session()` 从 Redis 客户端构造，注入 `CrawlSession`
3. **多源同文去重**：`repo.save_article` 跨来源 `content_hash`（正文
   SHA-256）查询，命中打 `duplicate_of:<首发省>` 质量标记
   （真实数据已生效，如文章 1026 → `duplicate_of:shanxi`）
4. **元数据自愈**：`save_article` 在正文 content_hash 未变时也会刷新
   title/source/published 列；`crawl-once <job_id> --refresh` 可绕过布隆强制重抓

---

## 五、核心文件结构

```
newsagg/
├── crawl/                  # Scrapy 爬虫子包
│   ├── spider.py           # SiteSpider：async start() 入口、parse_list/parse_detail、_guard
│   ├── session.py          # CrawlSession：租约续期线程、布隆、窗口判定、store_detail、note_block
│   ├── engine.py           # open_session / run_blocking / conclude / runner
│   ├── settings.py         # scrapy_settings()：并发8、重试2、关Cookie/重定向、自定义中间件
│   ├── middlewares.py      # AccessPolicyMiddleware(560) / PaceMiddleware(590)
│   └── dedup.py            # UrlBloom（Redis 位图布隆）
├── adapters/               # 34 个省级媒体适配器（fujian/beijing/jiangsu…）
│   ├── base.py             # Adapter 抽象：allowed_hosts/column_url/is_article/parse_list/parse_detail
│   └── _common.py          # 通用解析（标题/来源/时间/正文选择器 + 回退）
├── repo.py                 # ⭐ 唯一 SQL 落点（来源/批次/任务/租约/文章/收尾）
├── queue.py                # Redis Stream 封装（流 newsagg:site_jobs，组 newsagg-workers）
├── worker.py               # 消费队列 → classify_delivery(run/wait/ack) → 子进程 run-job
├── classify.py             # 投递分类：终态 ack / 他人租约 wait / 否则 run
├── scheduler.py            # 建批（GET_LOCK 幂等）、时间窗口
├── timewindow.py           # 7 天窗口 = 当天+前6自然日；增量回看 48h
├── cleaning.py             # clean_title/clean_source/clean_paragraphs/parse_published/csv_cell
├── dedup 相关：urls.py / crawl/dedup.py
├── query.py / stats.py / export.py / recrawl.py
├── supervisor.py           # 保持 N 个 worker 运行
└── cli.py                  # 命令行入口
sql/schema.sql              # 7 表：provinces/sources/source_slots/crawl_runs/crawl_jobs/job_attempts/article_tasks + articles
tests/                      # 128 个单元测试（含 fixtures 离线回归）
```

---

## 六、CLI 速查

```
python -m newsagg init-db / check
python -m newsagg tick [--force]          # 建批 + 消费一轮（cron 友好）
python -m newsagg run-worker              # 拉起 worker_count 个 worker
python -m newsagg crawl-once <job_id> [--refresh]   # 同步跑单任务（engine.run_blocking）
python -m newsagg run-job <job_id>        # 单任务（不消费队列）
python -m newsagg stats / sources / status
python -m newsagg query --province 江苏 --keyword X ...
python -m newsagg show <article_id>
python -m newsagg export --out PATH
python -m newsagg enable-source / resume-source / recrawl
```

> ⚠️ 文档措辞偏差：设计文档写 `crawl-once --adapter X`，实际 CLI 签名是
> `crawl-once <job_id>`（+ 可选 `--refresh`）。未影响功能，待统一。

---

## 七、字段质量（修复后实测，fujian）

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 空标题 | ~70% | 8/191 |
| 来源名 | 信息块污染（"2026-10-08 20:08 来源：人民日报 责任编辑：…"） | 干净："人民日报客户端"、"新华社"、"央视网"、"东南网" |
| 正文/时间 | 大面积缺失 | 完整段落 + 分钟级时间 |

修复点：来源提取剥离时间/编辑 pollution；详情解析回退列表页标题；
`cleaning.py` 新增 `extract_source` / `looks_like_source`。

端到端验证：
```
RESULT job_id=36 stats={'status':'partial','discovered':144,
                        'saved':115,'requests':144,'stop_reason':'finished'}
```

---

## 八、开发规范（强制）

1. **不要**重新引入 `AsyncioSelectorReactor`（见第三节）
2. 所有 SQL 只写在 `repo.py`，业务层不直接写 SQL
3. 爬虫统一走 `crawl/engine.py` 的 `run_blocking`，不直接调 Scrapy API
4. 新增适配器必须：实现 base 全部方法 + 注册 `adapters/__init__.py` +
   加入 `db.py` 的 CANDIDATE_SOURCES + 编写测试（参考 tests/test_adapters.py）
5. 数据库结构变更必须同步 `sql/schema.sql`
6. 新功能必须带单元测试；提交前 `pytest -q` 全绿（当前 128 个全过）
7. 环境：`.env`（DB/Redis/UA 配置），Windows 控制台需 `PYTHONIOENCODING=utf-8`

---

## 九、待办优先级（2026-10-09 更新）

### 已完成
1. **Phase 1.1 CLI 签名对齐（2026-10-09）**
   - ✅ `query` 命令新增 --from/--to/--page--page-size/--body-only；--date/limit/offset 保留兼容
   - ✅ `export` 新增可选 ArticleFilter（与 query 共用 build_where）
   - ✅ `crawl-once` 支持 `--adapter X`（新建本地任务不投队列，job_id 二选一）
   - ✅ `recrawl` 支持日期区间（--from/--to，与 --days 互斥）
   - ✅ `enable-source`/`resume-source` 支持 `--adapter` 双兼容
   - ✅ query.py 修复分页双截断 bug（取消 SQL 层分页 + Python 切片一次）
   - ✅ 删除 `newsagg/recrawl.py`（死代码，create_manual_job 已提供能力）

### 进行中
1. Phase 1.5：CLI 新功能单元测试 + pytest 全绿
2. Phase 1.2：scripts/register_tasks.ps1（计划任务注册，8.3 短路径）
3. Phase 1.3：健康检查脚本整理 → scripts/health_check.py
4. Phase 1.4：README 按设计文档骨架重写 + docs/development.md

### 后续待办
5. Phase 2 批次 A：beijing/jiangxi/guizhou（list_fetch_failed）修复
6. Phase 2 批次 B：12 个零产出来源修复
7. Phase 2 批次 C：7 个低产出来源修复
8. Phase 3 更新 CONTEXT_HANDOFF + 最终报告

---

## 十、运行环境事实（2026-10-09）

- 工作目录：`D:\project\News Aggregator`（venv: `.venv\`）
- MySQL 8.4：`C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe`，
  用户 `newsagg` / `newsagg_dev_password` / 库 `newsagg`
- Redis 5.0.14 本机运行（`.redis5`，6380端口，非 Memurai）
- 已知坑：PowerShell 会把子进程 stderr 当错误（用 Start-Process + 重定向
  文件再读）；崩溃运行会留下未过期租约（需清理 `sources.lease_*` 后重跑）

## 十一、架构对齐记录

### CLI 变更
| 命令 | 新签名 | 行为兼容性 |
|---|---|---|
| `crawl-once` | `--adapter X` 或 `job_id` | 旧命令名 + job_id 仍支持；--adapter 新建本地任务立即抓 |
| `recrawl` | `--adapter X [--from YYY-MM-DD] [--to YYY-MM-DD]` | --days 仍支持；--from/--to 优先级更高（互斥） |
| `query` | `--from --to --page --page-size --body-only` | 旧 `--date --limit --offset` 保留兼容；分页修复避免重复截断 |
| `export` | `--out PATH [--province --from --to]` | 无 Filter 时仍全量导出，支持与 query 一致的筛选 |

### 文档
- README.md：按设计文档骨架重写中（待完成）
- docs/development.md：计划从本文件提炼 §3/§7/§8 创建

---

## 十二、技能爬取修复策略

### 22 个病站分析
- 3 个 list_fetch_failed：beijing（/news 路径失效）、jiangxi（需 SECLEVEL=1）、guizhou（robots+5s 限流）
- 12 个零产出：liaoning、jilin、henan、changjiang、hunan、guangdong、gxtv、chongqing、sichuan、xizang、shaanxi、gansudaily
- 7 个低产出：jinwan(4)、hebei(3)、laodong(1)、zhejiang(1)、anhui(6)、hainan(2)、yunnan(2)

### 修复方法（纯 HTTP 逆向优先）
1. 每站采样：web-content-fetcher/spider-king 抓栏首页 → 判定静态/JS/失效
2. 定位真栏目页（要闻/滚动/地方）或 JSON API → 修复适配器
   - 若首页无静态链接 → 找栏目页 / 滚动列表 / JS API
   - JS 渲染站点：取接口直连，不引浏览器（gxtv、南方网等）
3. `crawl-once --adapter X` 实测 → 抽查落库字段 → 能留样的补测试
4. 新踩坑记录到 README §已知注意点
