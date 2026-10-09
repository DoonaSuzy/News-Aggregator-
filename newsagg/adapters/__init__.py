"""适配器注册表。

每个来源一个文件。``get_adapter(name)`` 按名字返回单例实例，未注册抛 ``KeyError``。
"""

from __future__ import annotations

from newsagg.adapters.base import SiteAdapter

_REGISTRY: dict[str, SiteAdapter] = {}


def register(adapter: SiteAdapter) -> SiteAdapter:
    _REGISTRY[adapter.name] = adapter
    return adapter


def get_adapter(name: str) -> SiteAdapter:
    if name not in _REGISTRY:
        raise KeyError(f"未注册的适配器: {name}")
    return _REGISTRY[name]


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


def _load_all() -> None:
    """导入所有适配器模块以完成注册。"""
    from newsagg.adapters import (  # noqa: F401
        beijing, jinwan, tianjin, hebei, shanxi, neimenggu, liaoning,
        jilin, heilongjiang, laodong, jiangsu, zhejiang, anhui, fujian,
        jiangxi, shandong, henan, changjiang, hubei, hunan, guangdong,
        gxtv, hainan, chongqing, sichuan, guizhou, yunnan, xizang,
        shaanxi, gansudaily, gansu, qinghai, ningxia, xinjiang,
    )


_loaded = False


def ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        _load_all()
        _loaded = True


__all__ = ["register", "get_adapter", "available_adapters", "ensure_loaded"]
