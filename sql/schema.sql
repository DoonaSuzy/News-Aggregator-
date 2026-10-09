-- News Aggregator 建表脚本（MySQL 8.0，utf8mb4）
-- 运行时刻字段写 UTC 墙钟（naive），带 _cst 的是北京时间墙钟，不随会话时区换算。

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS provinces (
    code CHAR(2) NOT NULL,
    name VARCHAR(32) NOT NULL,
    PRIMARY KEY (code),
    UNIQUE KEY uk_provinces_name (name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS sources (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    adapter_name VARCHAR(64) NOT NULL,
    province_code CHAR(2) NULL,
    media_name VARCHAR(128) NOT NULL,
    column_url VARCHAR(512) NOT NULL,
    verification_status ENUM('candidate', 'verified', 'enabled', 'paused') NOT NULL DEFAULT 'candidate',
    lease_token VARCHAR(64) NULL,
    lease_owner VARCHAR(128) NULL,
    lease_until_utc DATETIME NULL,
    cooldown_until_utc DATETIME NULL,
    pause_reason VARCHAR(255) NULL,
    last_discovery_success_at_utc DATETIME NULL,
    last_full_rescan_at_utc DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sources_adapter (adapter_name),
    KEY idx_sources_status (verification_status),
    KEY idx_sources_province (province_code),
    CONSTRAINT fk_sources_province FOREIGN KEY (province_code) REFERENCES provinces (code)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS source_slots (
    province_code CHAR(2) NOT NULL,
    source_id BIGINT UNSIGNED NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (province_code),
    UNIQUE KEY uk_source_slots_source (source_id),
    CONSTRAINT fk_slots_province FOREIGN KEY (province_code) REFERENCES provinces (code),
    CONSTRAINT fk_slots_source FOREIGN KEY (source_id) REFERENCES sources (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS crawl_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    trigger_key VARCHAR(20) NOT NULL,
    started_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at_utc DATETIME NULL,
    job_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_runs_trigger (trigger_key)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_id BIGINT UNSIGNED NOT NULL,
    trigger_key VARCHAR(20) NOT NULL,
    job_type ENUM('incremental', 'full_rescan', 'manual_recrawl') NOT NULL,
    status ENUM('queued', 'running', 'succeeded', 'partial', 'failed', 'retry_wait') NOT NULL DEFAULT 'queued',
    window_start_cst DATETIME NULL,
    window_end_cst DATETIME NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    discovered_count INT NOT NULL DEFAULT 0,
    saved_count INT NOT NULL DEFAULT 0,
    checkpoint_cst DATETIME NULL,
    retry_at_utc DATETIME NULL,
    stop_reason VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_jobs_source_trigger_type (source_id, trigger_key, job_type),
    KEY idx_jobs_status (status),
    KEY idx_jobs_trigger (trigger_key),
    CONSTRAINT fk_jobs_source FOREIGN KEY (source_id) REFERENCES sources (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_id BIGINT UNSIGNED NOT NULL,
    url_hash CHAR(64) NOT NULL,
    url VARCHAR(1024) NOT NULL,
    title VARCHAR(512) NOT NULL,
    body_text MEDIUMTEXT NOT NULL,
    source_name VARCHAR(128) NULL,
    published_at_utc DATETIME NULL,
    published_at_cst DATETIME NULL,
    time_precision ENUM('unknown', 'date', 'minute', 'second') NOT NULL DEFAULT 'unknown',
    content_hash CHAR(64) NULL,
    quality_flags JSON NULL,
    discovered_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_articles_source_hash (source_id, url_hash),
    KEY idx_articles_published (published_at_cst),
    KEY idx_articles_source_time (source_id, published_at_cst),
    CONSTRAINT fk_articles_source FOREIGN KEY (source_id) REFERENCES sources (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS article_tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_id BIGINT UNSIGNED NOT NULL,
    job_id BIGINT UNSIGNED NULL,
    discovered_url_hash CHAR(64) NOT NULL,
    url VARCHAR(1024) NOT NULL,
    status ENUM('pending', 'done', 'skipped', 'failed') NOT NULL DEFAULT 'pending',
    skip_reason VARCHAR(255) NULL,
    failure_class VARCHAR(64) NULL,
    retry_at_utc DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tasks_source_hash (source_id, discovered_url_hash),
    KEY idx_tasks_status (status),
    CONSTRAINT fk_tasks_source FOREIGN KEY (source_id) REFERENCES sources (id),
    CONSTRAINT fk_tasks_job FOREIGN KEY (job_id) REFERENCES crawl_jobs (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS job_attempts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    job_id BIGINT UNSIGNED NOT NULL,
    attempt_no INT NOT NULL,
    owner VARCHAR(128) NULL,
    started_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at_utc DATETIME NULL,
    outcome ENUM('succeeded', 'partial', 'failed', 'aborted') NULL,
    log_path VARCHAR(512) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_attempts_job_no (job_id, attempt_no),
    CONSTRAINT fk_attempts_job FOREIGN KEY (job_id) REFERENCES crawl_jobs (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci;

