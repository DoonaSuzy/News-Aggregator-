"""文章 / 来源 / 统计接口离线测试。"""

from __future__ import annotations


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "alive"

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["code"] == 0


class TestArticles:
    def test_list_ok(self, client):
        r = client.get("/api/v1/articles")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["meta"]["total"] == 2
        titles = [i["title"] for i in data["items"]]
        assert "江苏新闻一" in titles

    def test_list_filter_province(self, client):
        r = client.get("/api/v1/articles", params={"province": "江苏"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["province_name"] == "江苏"

    def test_list_filter_province_code(self, client):
        r = client.get("/api/v1/articles", params={"province": "35"})
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["adapter_name"] == "fujian"

    def test_list_bad_province(self, client):
        r = client.get("/api/v1/articles", params={"province": "不存在省"})
        assert r.status_code == 400
        assert r.json()["code"] == 400

    def test_list_keyword(self, client):
        r = client.get("/api/v1/articles", params={"keyword": "福建"})
        items = r.json()["data"]["items"]
        assert len(items) == 1

    def test_detail_has_body(self, client):
        r = client.get("/api/v1/articles/1")
        assert r.status_code == 200
        assert r.json()["data"]["body_text"] == "正文一"

    def test_detail_not_found(self, client):
        r = client.get("/api/v1/articles/999")
        assert r.status_code == 404
        assert r.json()["code"] == 404

    def test_list_excludes_body(self, client):
        r = client.get("/api/v1/articles")
        items = r.json()["data"]["items"]
        assert all(i["body_text"] is None for i in items)


class TestSourcesStats:
    def test_sources(self, client):
        r = client.get("/api/v1/sources")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 2

    def test_provinces(self, client):
        r = client.get("/api/v1/provinces")
        data = r.json()["data"]
        names = {p["name"]: p for p in data}
        assert names["江苏"]["source_count"] == 1
        assert names["江苏"]["article_count"] == 1

    def test_overview(self, client):
        r = client.get("/api/v1/stats/overview")
        d = r.json()["data"]
        assert d["total_articles"] == 2
        assert d["enabled_sources"] == 2
        assert d["provinces_with_data"] == 2


class TestAuth:
    def test_login_ok(self, client):
        r = client.post("/api/v1/auth/login",
                        json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        assert r.json()["data"]["access_token"]

    def test_login_bad(self, client):
        r = client.post("/api/v1/auth/login",
                        json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_protected_with_token(self, client):
        tok = client.post("/api/v1/auth/login",
                          json={"username": "admin", "password": "admin123"}
                          ).json()["data"]["access_token"]
        r = client.get("/api/v1/articles/1",
                       headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200


class TestDocs:
    def test_openapi(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/api/v1/articles" in paths
        assert "/api/v1/auth/login" in paths
