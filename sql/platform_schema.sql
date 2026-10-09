-- 数据中台独立库建表脚本（MySQL 8.0，utf8mb4）
-- 库名：newsagg_platform（与爬虫 newsagg 库解耦）
-- 运行时刻字段写 UTC 墙钟（naive），_cst 为北京时间墙钟。
--
-- 用法：
--   mysql -u root -p < sql/platform_schema.sql
--   mysql -u platform -pnewsagg_platform_pwd newsagg_platform < sql/platform_schema.sql

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS provinces (
    code VARCHAR(8) NOT NULL,
    name VARCHAR(32) NOT NULL,
    PRIMARY KEY (code),
    UNIQUE KEY uk_provinces_name (name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS sources (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    adapter_name VARCHAR(64) NOT NULL,
    media_name VARCHAR(128) NOT NULL,
    province_code VARCHAR(8) NULL,
    column_url VARCHAR(512) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'enabled',
    article_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    last_sync_at_utc DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sources_adapter (adapter_name),
    KEY idx_sources_province (province_code),
    KEY idx_sources_status (status),
    CONSTRAINT fk_sources_province FOREIGN KEY (province_code) REFERENCES provinces (code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_id BIGINT UNSIGNED NOT NULL,
    url_hash VARCHAR(64) NOT NULL,
    url VARCHAR(1024) NOT NULL,
    title VARCHAR(512) NOT NULL DEFAULT '',
    body_text LONGTEXT NULL,
    source_name VARCHAR(128) NOT NULL DEFAULT '',
    published_at_utc DATETIME NULL,
    published_at_cst DATETIME NULL,
    time_precision VARCHAR(16) NOT NULL DEFAULT 'unknown',
    content_hash VARCHAR(64) NOT NULL DEFAULT '',
    quality_flags VARCHAR(255) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_article_source_hash (source_id, url_hash),
    KEY idx_articles_published (published_at_cst),
    CONSTRAINT fk_articles_source FOREIGN KEY (source_id) REFERENCES sources (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS users (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'viewer',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ingest_batches (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    trigger_key VARCHAR(32) NOT NULL,
    origin VARCHAR(64) NOT NULL DEFAULT 'crawler',
    total INT UNSIGNED NOT NULL DEFAULT 0,
    inserted INT UNSIGNED NOT NULL DEFAULT 0,
    updated INT UNSIGNED NOT NULL DEFAULT 0,
    skipped INT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    message VARCHAR(255) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_batches_trigger (trigger_key)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;
