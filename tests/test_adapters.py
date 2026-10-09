"""适配器单元测试：注册完整性 + fujian 夹具解析 + 通用逻辑。"""

from __future__ import annotations

from pathlib import Path

from newsagg.adapters import ensure_loaded, get_adapter, available_adapters
from newsagg.adapters.listing import is_descending, mark_sticky
from newsagg.adapters.base import ListItem

FIXTURES = Path(__file__).parent / "fixtures"


def setup_module(module):
    ensure_loaded()


class TestRegistry:
    def test_34_adapters(self):
        assert len(available_adapters()) == 34

    def test_all_have_hosts_and_column(self):
        for name in available_adapters():
            ad = get_adapter(name)
            assert ad.allowed_hosts, f"{name} 缺少 allowed_hosts"
            assert ad.column_url, f"{name} 缺少 column_url"
            assert ad.version, f"{name} 缺少 version"

    def test_unknown_adapter_raises(self):
        import pytest
        with pytest.raises(KeyError):
            get_adapter("__nope__")

    def test_seed_adapters_present(self):
        names = set(available_adapters())
        for n in ["beijing", "jiangsu", "fujian", "chongqing", "guizhou", "xinjiang"]:
            assert n in names


class TestAllowsAndIsArticle:
    def test_allows_host(self):
        ad = get_adapter("fujian")
        assert ad.allows("https://www.fjsen.com/x")

    def test_allows_rejects_foreign(self):
        ad = get_adapter("fujian")
        assert not ad.allows("https://www.other.com/x")

    def test_is_article_accepts_content(self):
        ad = get_adapter("fujian")
        assert ad.is_article("https://www.fjsen.com/2026-10/08/content_32264105.htm")

    def test_is_article_rejects_channel(self):
        ad = get_adapter("fujian")
        assert not ad.is_article("https://www.fjsen.com/a/gov/gov.htm")
        assert not ad.is_article("https://www.fjsen.com/zhuanti/node_302959.htm")

    def test_is_article_rejects_foreign(self):
        ad = get_adapter("fujian")
        assert not ad.is_article("https://www.evil.com/2026-10/08/content_1.htm")


class TestFujianDetailFixture:
    def test_parse_detail_from_fixture(self):
        ad = get_adapter("fujian")
        html = (FIXTURES / "fujian_detail.html").read_text(encoding="utf-8")
        d = ad.parse_detail(html, url="https://www.fjsen.com/2026-10/08/content_1.htm")
        assert d.title == "测试新闻标题"
        assert len(d.paragraphs) == 3
        assert d.paragraphs[0].startswith("这是正文第一段")
        assert d.media_only is False

    def test_parse_detail_source_time(self):
        ad = get_adapter("fujian")
        html = (FIXTURES / "fujian_detail.html").read_text(encoding="utf-8")
        d = ad.parse_detail(html, url="https://www.fjsen.com/2026-10/08/content_1.htm")
        assert "2026-10-03 15:04" in d.published_text
        assert "东南新闻网" in d.source_name or "来源" in d.source_name


class TestFujianListFixture:
    def test_parse_list_from_fixture(self):
        ad = get_adapter("fujian")
        html = (FIXTURES / "fujian_list.html").read_text(encoding="utf-8")
        parsed = ad.parse_list(html, base_url=ad.column_url)
        urls = [i.url for i in parsed.items]
        # 三条真实文章被抓到
        assert "https://www.fjsen.com/2026-10/08/content_32264105.htm" in urls
        assert "https://www.fjsen.com/2026-10/08/content_32264104.htm" in urls
        # 栏目/专题/javascript 被排除
        assert not any("gov.htm" in u for u in urls)
        assert not any("node_" in u for u in urls)
        assert not any("javascript:" in u for u in urls)

    def test_list_titles_present(self):
        ad = get_adapter("fujian")
        html = (FIXTURES / "fujian_list.html").read_text(encoding="utf-8")
        parsed = ad.parse_list(html, base_url=ad.column_url)
        titles = [i.title for i in parsed.items]
        assert any("以文化滋养" in t for t in titles)


class TestListingHelpers:
    def test_mark_sticky(self):
        items = [ListItem(url="u1", title="置顶新闻"), ListItem(url="u2", title="普通新闻")]
        mark_sticky(items)
        assert items[0].sticky is True
        assert items[1].sticky is False

    def test_is_descending_default_true(self):
        assert is_descending([]) is True

    def test_is_descending_by_dates(self):
        items = [
            ListItem(url="1", list_time_text="2026-10-03"),
            ListItem(url="2", list_time_text="2026-10-02"),
        ]
        assert is_descending(items) is True


class TestGuizhouConfig:
    def test_request_interval(self):
        ad = get_adapter("guizhou")
        assert ad.request_interval == 5
