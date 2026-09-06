-- ============================================
-- 习惯管家 - 三期迁移:管理后台 + 自定义 LLM
-- 适用 MySQL 8.0+ (使用 information_schema 检查后 ALTER)
-- 应用方式: mysql -u root -p habit_db < migration_phase3.sql
-- ============================================

-- 通用过程:加列(如不存在)
DROP PROCEDURE IF EXISTS add_col_if_missing;
DELIMITER //
CREATE PROCEDURE add_col_if_missing(
    IN p_table VARCHAR(64),
    IN p_col VARCHAR(64),
    IN p_def TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table
          AND COLUMN_NAME = p_col
    ) THEN
        SET @sql = CONCAT('ALTER TABLE ', p_table, ' ADD COLUMN ', p_col, ' ', p_def);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- 通用过程:加索引(如不存在) - p_index_def 包含完整子句,如 "UNIQUE INDEX idx_name (col)" 或 "INDEX idx_name (col)"
DROP PROCEDURE IF EXISTS add_index_if_missing;
DELIMITER //
CREATE PROCEDURE add_index_if_missing(
    IN p_table VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_full_def TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table
          AND INDEX_NAME = p_index_name
    ) THEN
        SET @sql = CONCAT('ALTER TABLE ', p_table, ' ADD ', p_full_def);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- 1. users 表扩展
CALL add_col_if_missing('users', 'is_admin', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_col_if_missing('users', 'is_active', 'TINYINT(1) NOT NULL DEFAULT 1');
CALL add_col_if_missing('users', 'username', 'VARCHAR(64) NULL');
CALL add_col_if_missing('users', 'password_hash', 'VARCHAR(255) NULL');
CALL add_col_if_missing('users', 'last_login_at', 'DATETIME NULL');

-- users 索引
CALL add_index_if_missing('users', 'idx_users_username', 'UNIQUE INDEX idx_users_username (username)');
CALL add_index_if_missing('users', 'idx_users_is_admin', 'INDEX idx_users_is_admin (is_admin)');
CALL add_index_if_missing('users', 'idx_users_is_active', 'INDEX idx_users_is_active (is_active)');

-- 2. LLM 模型表
CREATE TABLE IF NOT EXISTS llm_models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    base_url VARCHAR(255) NOT NULL,
    api_key VARCHAR(512) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    is_system_default TINYINT(1) NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    owner_user_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_owner (owner_user_id, is_active),
    INDEX idx_default (is_system_default)
);

-- 3. 知识库文档表
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    chunk_count INT NOT NULL DEFAULT 0,
    file_size INT NOT NULL DEFAULT 0,
    status ENUM('pending', 'indexed', 'failed') NOT NULL DEFAULT 'pending',
    error_msg TEXT NULL,
    uploaded_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_uploader (uploaded_by, created_at)
);

-- 4. 操作日志表
CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(32) NULL,
    resource_id INT NULL,
    details JSON NULL,
    ip VARCHAR(64) NULL,
    user_agent VARCHAR(255) NULL,
    status ENUM('success', 'failed') NOT NULL DEFAULT 'success',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id, created_at),
    INDEX idx_action (action, created_at),
    INDEX idx_created (created_at)
);

-- 5. AI 聊天记录
CREATE TABLE IF NOT EXISTS ai_chat_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    role ENUM('user', 'assistant', 'tool', 'system') NOT NULL,
    content TEXT NOT NULL,
    tool_calls JSON NULL,
    model VARCHAR(128) NULL,
    prompt_tokens INT NULL,
    completion_tokens INT NULL,
    total_tokens INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_session (user_id, session_id, created_at),
    INDEX idx_created (created_at),
    INDEX idx_model_tokens (model, created_at, total_tokens)
);

-- 6. 用户配额
CREATE TABLE IF NOT EXISTS user_quotas (
    user_id INT PRIMARY KEY,
    ai_calls_remaining INT NOT NULL DEFAULT 100,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 7. user_settings 加 active_model_id
CALL add_col_if_missing('user_settings', 'active_model_id', 'INT NULL');

-- 8. 初始化:从 .env 创建一个系统默认模型占位(API Key 待管理员替换)
INSERT INTO llm_models (name, base_url, api_key, model_name, is_system_default, is_active, owner_user_id)
SELECT 'Agnes 官方(默认)', 'https://apihub.agnes-ai.com/v1', 'MIGRATION_PLACEHOLDER', 'agnes-2.0-flash', 1, 1, NULL
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM llm_models WHERE is_system_default = 1);

-- 清理过程
DROP PROCEDURE IF EXISTS add_col_if_missing;
DROP PROCEDURE IF EXISTS add_index_if_missing;
