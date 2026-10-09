"""江西 —— 大江网（需TLS SECLEVEL=1）（jiangxi）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class JiangxiAdapter(GenericAdapter):
    name = "jiangxi"
    version = "1.0"
    allowed_hosts = ("www.jxnews.com.cn", "jxnews.com.cn", "jxcn.cn")
    column_url = "https://www.jxnews.com.cn/"
    # 大江网的 TLS 只接受低安全等级套件，默认上下文握手失败
    # （SSLV3_ALERT_HANDSHAKE_FAILURE）；证书校验仍由 Scrapy 正常执行。
    tls_ciphers = "DEFAULT:@SECLEVEL=1"


register(JiangxiAdapter())
