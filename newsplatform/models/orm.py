"""数据中台 ORM 模型（独立库 ``newsagg_platform``）。

与爬虫库解耦：这里定义中台对外服务的标准数据模型。
爬虫后续通过接口/直连把数据写入这些表。
运行时刻字段写 UTC（naive），``*_cst`` 为北京时间（naive）。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, Integer,
    SmallInteger, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


#: 自增主键：MySQL 用 BIGINT，SQLite 用 INTEGER（保证 rowid 自增）
_AutoBigInt = BigInteger().with_variant(Integer, "sqlite")


class Province(Base):
    __tablename__ = "provinces"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    sources: Mapped[List["Source"]] = relationship(back_populates="province")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(_AutoBigInt, primary_key=True, autoincrement=True)
    adapter_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    media_name: Mapped[str] = mapped_column(String(128), nullable=False)
    province_code: Mapped[Optional[str]] = mapped_column(
        String(8), ForeignKey("provinces.code"), nullable=True
    )
    column_url: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", nullable=False)
    article_count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_sync_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    province: Mapped[Optional[Province]] = relationship(
        back_populates="sources", lazy="joined"
    )
    articles: Mapped[List["Article"]] = relationship(back_populates="source")

    __table_args__ = (
        Index("idx_sources_province", "province_code"),
        Index("idx_sources_status", "status"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(_AutoBigInt, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id"), nullable=False
    )
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(128), default="")
    published_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at_cst: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    time_precision: Mapped[str] = mapped_column(String(16), default="unknown")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    quality_flags: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="articles", lazy="joined")

    __table_args__ = (
        Index("uk_article_source_hash", "source_id", "url_hash", unique=True),
        Index("idx_articles_published", "published_at_cst"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class IngestBatch(Base):
    """数据接入批次（爬虫对接留痕）。"""

    __tablename__ = "ingest_batches"

    id: Mapped[int] = mapped_column(_AutoBigInt, primary_key=True, autoincrement=True)
    trigger_key: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str] = mapped_column(String(64), default="crawler")
    total: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    message: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


__all__ = ["Base", "Province", "Source", "Article", "User", "IngestBatch"]
