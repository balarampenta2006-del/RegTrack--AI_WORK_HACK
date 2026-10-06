CREATE TABLE companies (
    id              BIGINT       NOT NULL AUTO_INCREMENT,
    name            VARCHAR(190) NOT NULL,
    industry        VARCHAR(120) NULL,
    website         VARCHAR(255) NULL,
    description     TEXT         NULL,
    jurisdictions   VARCHAR(255) NULL,
    created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_companies_name (name)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE users (
    id             BIGINT       NOT NULL AUTO_INCREMENT,
    email          VARCHAR(190) NOT NULL,
    password_hash  VARCHAR(100) NOT NULL,
    full_name      VARCHAR(190) NOT NULL,
    role           VARCHAR(32)  NOT NULL DEFAULT 'COMPLIANCE_OFFICER',
    company_id     BIGINT       NULL,
    enabled        TINYINT(1)   NOT NULL DEFAULT 1,
    last_login_at  DATETIME(6)  NULL,
    created_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_email (email),
    KEY idx_users_company (company_id),
    CONSTRAINT fk_users_company FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE SET NULL
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE company_profiles (
    id                        BIGINT       NOT NULL AUTO_INCREMENT,
    company_id                BIGINT       NOT NULL,
    industry_sectors          TEXT         NULL,
    regulatory_bodies         VARCHAR(255) NULL,
    jurisdictions             VARCHAR(255) NULL,
    compliance_contact_email  VARCHAR(190) NULL,
    notification_enabled      TINYINT(1)   NOT NULL DEFAULT 1,
    notes                     TEXT         NULL,
    created_at                DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at                DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_company_profiles_company (company_id),
    CONSTRAINT fk_company_profiles_company FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE regulation_sources (
    id                   BIGINT       NOT NULL AUTO_INCREMENT,
    code                 VARCHAR(32)  NOT NULL,
    name                 VARCHAR(190) NOT NULL,
    agency               VARCHAR(64)  NULL,
    base_url             VARCHAR(255) NULL,
    watch_url            VARCHAR(512) NULL,
    change_detection_id  VARCHAR(128) NULL,
    active               TINYINT(1)   NOT NULL DEFAULT 1,
    created_at           DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_sources_code (code)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE regulations (
    id              BIGINT       NOT NULL AUTO_INCREMENT,
    source_id       BIGINT       NOT NULL,
    title           VARCHAR(512) NOT NULL,
    identifier      VARCHAR(120) NULL,
    url             VARCHAR(512) NOT NULL,
    category        VARCHAR(120) NULL,
    published_date  DATE         NULL,
    effective_date  DATE         NULL,
    created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_regulations_url (url),
    KEY idx_regulations_source (source_id),
    CONSTRAINT fk_regulations_source FOREIGN KEY (source_id) REFERENCES regulation_sources (id) ON DELETE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE regulation_versions (
    id             BIGINT       NOT NULL AUTO_INCREMENT,
    regulation_id  BIGINT       NOT NULL,
    version_no     INT          NOT NULL,
    content        MEDIUMTEXT   NULL,
    content_hash   VARCHAR(64)  NULL,
    storage_path   VARCHAR(512) NULL,
    source_url     VARCHAR(512) NULL,
    fetched_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    is_current     TINYINT(1)   NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_versions_regulation_version (regulation_id, version_no),
    KEY idx_versions_regulation (regulation_id),
    CONSTRAINT fk_versions_regulation FOREIGN KEY (regulation_id) REFERENCES regulations (id) ON DELETE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE change_events (
    id               BIGINT       NOT NULL AUTO_INCREMENT,
    source_id        BIGINT       NULL,
    regulation_id    BIGINT       NULL,
    old_version_id   BIGINT       NULL,
    new_version_id   BIGINT       NULL,
    status           VARCHAR(32)  NOT NULL DEFAULT 'RECEIVED',
    payload_url      VARCHAR(512) NULL,
    payload_json     MEDIUMTEXT   NULL,
    error            TEXT         NULL,
    received_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    processed_at     DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY idx_events_status (status),
    KEY idx_events_received (received_at),
    KEY idx_events_source (source_id),
    CONSTRAINT fk_events_source FOREIGN KEY (source_id) REFERENCES regulation_sources (id) ON DELETE SET NULL,
    CONSTRAINT fk_events_regulation FOREIGN KEY (regulation_id) REFERENCES regulations (id) ON DELETE SET NULL
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE alerts (
    id               BIGINT       NOT NULL AUTO_INCREMENT,
    company_id       BIGINT       NOT NULL,
    change_event_id  BIGINT       NOT NULL,
    relevance        VARCHAR(16)  NOT NULL DEFAULT 'NONE',
    summary          TEXT         NULL,
    affected_areas   TEXT         NULL,
    effective_date   DATE         NULL,
    required_action  TEXT         NULL,
    status           VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    email_recipients VARCHAR(512) NULL,
    email_sent_at    DATETIME(6)  NULL,
    created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_alerts_company_status (company_id, status),
    KEY idx_alerts_event (change_event_id),
    CONSTRAINT fk_alerts_company FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
    CONSTRAINT fk_alerts_event FOREIGN KEY (change_event_id) REFERENCES change_events (id) ON DELETE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE audit_logs (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    actor_email  VARCHAR(190) NULL,
    actor_role   VARCHAR(32)  NULL,
    action       VARCHAR(64)  NOT NULL,
    entity_type  VARCHAR(64)  NULL,
    entity_id    BIGINT       NULL,
    details      TEXT         NULL,
    ip_address   VARCHAR(64)  NULL,
    created_at   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_audit_created (created_at),
    KEY idx_audit_action (action)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;
