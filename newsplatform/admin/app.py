"""Flask 管理后台应用工厂。

职责：来源状态看板、采集概览、健康页。生产用 Gunicorn 运行：
``gunicorn -w 2 -b 0.0.0.0:5000 'newsplatform.admin.app:create_app()'``
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template

from newsplatform.core.config import get_settings

logger = logging.getLogger("newsplatform.admin")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = get_settings().jwt_secret

    @app.get("/")
    def index():
        try:
            return render_template("index.html", app_name=get_settings().app_name)
        except Exception:  # noqa: BLE001
            # 模板缺失时退化为 JSON，保证后台不空
            return jsonify({"app": get_settings().app_name, "status": "ok"})

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "alive"})

    @app.get("/api/status")
    def status():
        """转调 FastAPI 总览，便于后台统一展示。"""
        import os
        import urllib.request
        base = os.environ.get("FASTAPI_INTERNAL_URL", "http://fastapi:8000")
        url = f"{base}/api/v1/stats/overview"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                import json
                return app.response_class(resp.read(), mimetype="application/json")
        except Exception as exc:  # noqa: BLE001
            logger.warning("fastapi unreachable: %s", exc)
            return jsonify({"code": 503, "message": "fastapi unreachable"}), 503

    return app


__all__ = ["create_app"]
