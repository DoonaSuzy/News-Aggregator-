"""cli 模块单元测试：build_parser / dispatch / 子命令调用。"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from newsagg.cli import build_parser, main, _dispatch


class TestBuildParser:
    def test_query_args(self):
        parser = build_parser()
        args = parser.parse_args(["query", "--province", "江苏", "--date", "2026-10-08",
                                 "--keyword", "经济", "--limit", "10", "--offset", "5"])
        assert args.command == "query"
        assert args.province == "江苏"
        assert args.date == "2026-10-08"
        assert args.keyword == "经济"
        assert args.limit == 10
        assert args.offset == 5

    def test_query_new_args(self):
        parser = build_parser()
        args = parser.parse_args(["query", "--from", "2026-10-01", "--to", "2026-10-08",
                                 "--page", "2", "--page-size", "20", "--body-only"])
        assert args.date_from == "2026-10-01"
        assert args.date_to == "2026-10-08"
        assert args.page == 2
        assert args.page_size == 20
        assert args.body_only is True

    def test_export_args(self):
        parser = build_parser()
        args = parser.parse_args(["export", "--out", "test.csv"])
        assert args.command == "export"
        assert args.out == "test.csv"

    def test_crawl_once_args(self):
        parser = build_parser()
        args = parser.parse_args(["crawl-once", "--adapter", "jiangsu", "--refresh"])
        assert args.command == "crawl-once"
        assert args.adapter == "jiangsu"
        assert args.refresh is True

    def test_crawl_once_job_id(self):
        parser = build_parser()
        args = parser.parse_args(["crawl-once", "42"])
        assert args.job_id == 42

    def test_recrawl_args(self):
        parser = build_parser()
        args = parser.parse_args(["recrawl", "jiangsu", "--days", "7"])
        assert args.command == "recrawl"
        assert args.adapter == "jiangsu"
        assert args.days == 7

    def test_recrawl_date_range(self):
        parser = build_parser()
        args = parser.parse_args(["recrawl", "jiangsu", "--from", "2026-10-01", "--to", "2026-10-08"])
        assert args.date_from == "2026-10-01"
        assert args.date_to == "2026-10-08"

    def test_enable_source_args(self):
        parser = build_parser()
        args = parser.parse_args(["enable-source", "jiangsu"])
        assert args.command == "enable-source"
        assert args.adapter == "jiangsu"

    def test_stats_args(self):
        parser = build_parser()
        args = parser.parse_args(["stats"])
        assert args.command == "stats"


class TestDispatch:
    def test_unknown_command_returns_2(self):
        parser = build_parser()
        args = parser.parse_args(["query"])
        args.command = "__unknown__"
        with patch("newsagg.cli._cmd_query") as m:
            result = _dispatch(args)
            assert result == 2
            m.assert_not_called()

    def test_init_db_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["init-db"])
        with patch("newsagg.cli._cmd_init_db", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()

    def test_check_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["check"])
        with patch("newsagg.cli._cmd_selfcheck", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()

    def test_query_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["query", "--province", "江苏"])
        with patch("newsagg.cli._cmd_query", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()

    def test_export_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["export", "--out", "x.csv"])
        with patch("newsagg.cli._cmd_export", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()

    def test_crawl_once_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["crawl-once", "--adapter", "jiangsu"])
        with patch("newsagg.cli._cmd_crawl_once", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()

    def test_recrawl_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["recrawl", "jiangsu", "--days", "7"])
        with patch("newsagg.cli._cmd_recrawl", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()

    def test_stats_dispatches(self):
        parser = build_parser()
        args = parser.parse_args(["stats"])
        with patch("newsagg.cli._cmd_stats", return_value=0) as m:
            result = _dispatch(args)
            assert result == 0
            m.assert_called_once()


class TestCmdQuery:
    def test_output_format(self):
        from newsagg.cli import _cmd_query
        mock_row = {
            "id": 1, "province_name": "江苏", "media_name": "中国江苏网",
            "published_at_cst": None, "title": "测试", "url": "http://x.com",
            "quality_flags": "[]",
        }
        mock_query = MagicMock()
        mock_query.search_articles.return_value = ([mock_row], 1)
        with patch("newsagg.query.ArticleQuery", return_value=mock_query), \
             patch("newsagg.db.Database") as mock_db:
            args = MagicMock()
            args.province = None
            args.date = None
            args.keyword = None
            args.unknown_time = False
            args.limit = 20
            args.offset = 0
            args.date_from = None
            args.date_to = None
            args.page = None
            args.page_size = None
            args.body_only = False
            result = _cmd_query(args)
            assert result == 0
            mock_query.search_articles.assert_called_once()


class TestCmdExport:
    def test_calls_export_csv(self):
        from newsagg.cli import _cmd_export
        with patch("newsagg.export.export_csv", return_value="/tmp/out.csv") as m:
            result = _cmd_export("/tmp/out.csv")
            assert result == 0
            m.assert_called_once_with("/tmp/out.csv")


class TestCmdCrawlOnce:
    def test_calls_run_blocking(self):
        from newsagg.cli import _cmd_crawl_once
        with patch("newsagg.crawl.engine.run_blocking", return_value={"status": "succeeded"}) as m:
            result = _cmd_crawl_once(job_id=42, refresh=False)
            assert result == 0
            m.assert_called_once()

    def test_no_job_id_returns_1(self):
        from newsagg.cli import _cmd_crawl_once
        result = _cmd_crawl_once(job_id=None, adapter=None)
        assert result == 1

    def test_adapter_creates_job(self):
        from newsagg.cli import _cmd_crawl_once
        with patch("newsagg.schedule.create_manual_job", return_value=99), \
             patch("newsagg.crawl.engine.run_blocking", return_value={"status": "succeeded"}) as m:
            result = _cmd_crawl_once(adapter="jiangsu")
            assert result == 0
            m.assert_called_once_with(99, refresh=False)


class TestCmdRecrawl:
    def test_calls_create_manual_job(self):
        from newsagg.cli import _cmd_recrawl
        with patch("newsagg.schedule.create_manual_job", return_value=42) as m:
            result = _cmd_recrawl("jiangsu", days=7)
            assert result == 0
            m.assert_called_once_with("jiangsu", days=7)


class TestCmdEnableSource:
    def test_calls_enable_source(self):
        from newsagg.cli import _cmd_enable_source
        mock_repo = MagicMock()
        mock_repo.enable_source.return_value = True
        with patch("newsagg.repo.Repository") as mock_repo_cls, \
             patch("newsagg.db.Database"):
            mock_repo_cls.return_value = mock_repo
            result = _cmd_enable_source("jiangsu")
            assert result == 0
            mock_repo.enable_source.assert_called_once()


class TestCmdResumeSource:
    def test_calls_resume_source(self):
        from newsagg.cli import _cmd_resume_source
        mock_repo = MagicMock()
        with patch("newsagg.repo.Repository") as mock_repo_cls, \
             patch("newsagg.db.Database"):
            mock_repo_cls.return_value = mock_repo
            result = _cmd_resume_source("jiangsu")
            assert result == 0
            mock_repo.resume_source.assert_called_once()
