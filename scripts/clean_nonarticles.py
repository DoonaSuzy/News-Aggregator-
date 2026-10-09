"""识别并清理非文章污染：专题页/栏目页/电子版/视频/图集/联系页。

这些页面被当作候选抓进来但没有实质新闻正文，属于数据污染。本脚本先
dry-run 统计各来源的非文章数与特征，--apply 时从 articles 表删除。

判定规则（标题或 URL 命中任一非文章特征即标记）：
- 专题/活动页：标题含 专题|专题页|回顾|盛典|评选|直播|发布会
- 电子版/报纸版面：URL 含 /tbtj/、电子版、版面
- 视频/图集：URL 含 /shipin/ /video/ /photo/，或 host 为 v.*/rm-*
- 功能/联系页：标题含 投诉电话|举报电话|联系我们|网站地图|关于我们
- 门户首页/部门页：标题等于省/市/部门名（无具体新闻标题）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.db import Database

# 标题命中即非文章（保守：只用明确的栏目/直播/功能页标记，避免误杀
# 「专题培训」「专题研究」「…新闻发布会举行」这类真实新闻）
# 标题命中即非文章（极保守：只保留明确的「功能/联系/版面/门户」页，
# 不碰「直播|...新闻发布会」「社会责任报告」「学习原声」「一图读懂」等真实内容）
_TITLE_BAD = re.compile(
    r"(联系我们|网站地图|关于我们|版面导航|客户端下载|下载客户端|"
    r"投诉电话|举报电话|返回首页|遗失声明)",
)
# 空正文才判定的标题型污染（专题集合页/发布会页/征集专栏）：
# 以「专题|专栏|发布会」开头+分隔符，属栏目入口而非单篇稿件。真实新闻
# 即便含「专题」「发布会」也多在句中（如「…新闻发布会举行」），故锚定行首。
_TITLE_EMPTY_BAD = re.compile(
    r"^\s*(专题|专栏)\s*[｜|丨·、]|^\s*.*(新闻发布会|直播回顾|启动仪式)\s*_?\S{0,12}$",
)
# 门户/频道/部门页标题兜底（JS 壳页/频道页常以纯标识词当标题）
_PORTAL_TITLE = re.compile(
    r"^(南海网客户端|极目新闻|中国西藏新闻网|千龙网|客户端|手机版|网站首页)\s*$",
)
# URL 命中即非文章（结构性，高置信度）
_URL_BAD = re.compile(
    r"(/shipin/|/video/|/photo/|/tbtj/|/zt/|/zhuanti/|/special/|"
    r"/fbh_zhibo/|/fbh_zhibo_|/jmythshare/|/proback_shared|/node_[0-9a-z]+/?$|"
    r"/tj/|/pk/|/ztfbt/|/hd/|rm-nhwapp|/contact|/sitemap|/about|/download|"
    r"\.pdf$|/$)",
    re.I,
)


def is_non_article(title: str, url: str, body: str = "") -> str:
    """返回命中原因，空串表示是文章。

    判定原则：
    - 标题功能页（联系我们/举报电话/网站地图…）始终算非文章，无歧义。
    - URL 结构命中（视频/专题/电子版面…）只在**正文为空**时才算非文章；
      有正文说明抓到的是真实稿件，绝不因 URL 路径误删。
    - 门户/频道壳页标题（南海网客户端等）同样只在正文为空时判定。
    """
    t = title or ""
    u = url or ""
    has_body = bool((body or "").strip())
    if _TITLE_BAD.search(t):
        return "title"
    if _URL_BAD.search(u) and not has_body:
        return "url"
    if not has_body and _PORTAL_TITLE.search(t):
        return "portal"
    # 空正文的专题集合页/发布会页：标题以「专题/专栏」开头或整条是发布会标题
    if not has_body and _TITLE_EMPTY_BAD.search(t):
        return "topic"
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际删除（默认 dry-run）")
    ap.add_argument("--include-functional", action="store_true",
                    help="同时删除带正文的功能页（联系我们/举报电话…）；默认保护")
    ap.add_argument("--min-title-len", type=int, default=4,
                    help="标题短于此长度且无正文视为门户/部门页")
    args = ap.parse_args(argv)

    conn = Database().connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, a.title, a.url, a.body_text, s.adapter_name "
                "FROM articles a JOIN sources s ON s.id = a.source_id"
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    non_articles: list[tuple[int, str, str]] = []
    by_source: dict[str, int] = {}
    # 带正文但标题命中功能页（联系我们/举报电话…）——边界项，默认不删
    functional_with_body: list[tuple[int, str, str, str]] = []
    for r in rows:
        title = r["title"] or ""
        url = r["url"] or ""
        body = r["body_text"] or ""
        reason = is_non_article(title, url, body)
        if not reason:
            continue
        # 标题功能页命中但仍有正文 → 归入边界项，默认保护
        if reason == "title" and body.strip():
            functional_with_body.append(
                (int(r["id"]), r["adapter_name"], title, reason)
            )
            continue
        non_articles.append((int(r["id"]), r["adapter_name"], reason))
        by_source[r["adapter_name"]] = by_source.get(r["adapter_name"], 0) + 1

    print(f"总文章 {len(rows)}")
    print(f"  · 空正文非文章（默认清理）：{len(non_articles)}")
    print(f"  · 带正文功能页（边界，默认保护）：{len(functional_with_body)}")
    print("=== 按来源分布（默认清理项）===")
    for name, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"{name:14} {n}")

    # 抽样展示
    print("\n=== 抽样（前 20 条，默认清理项）===")
    for aid, name, reason in non_articles[:20]:
        row = next(r for r in rows if int(r["id"]) == aid)
        print(f"#{aid} [{reason}] {name:12} | {str(row['title'])[:40]}")

    if functional_with_body:
        print("\n=== 带正文功能页（默认保留，--include-functional 才删）===")
        for aid, name, title, reason in functional_with_body:
            print(f"#{aid} [{reason}] {name:12} | {str(title)[:40]}")

    targets = list(non_articles)
    if args.include_functional:
        for aid, name, title, reason in functional_with_body:
            targets.append((aid, name, reason))

    if args.apply:
        if not targets:
            print("\n无可删除项")
            return 0
        ids = [aid for aid, _, _ in targets]
        conn = Database().connect()
        try:
            with conn.cursor() as cur:
                # 分批删除
                for i in range(0, len(ids), 500):
                    batch = ids[i:i + 500]
                    ph = ",".join(["%s"] * len(batch))
                    cur.execute(f"DELETE FROM articles WHERE id IN ({ph})", batch)
            conn.commit()
        finally:
            conn.close()
        print(f"\n已删除 {len(ids)} 条非文章")
    else:
        print("\n（dry-run，加 --apply 实际删除）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
