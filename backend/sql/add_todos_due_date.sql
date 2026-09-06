-- 兼容老 DB:todos 表加 due_date 列 + 索引
-- 用于 schema.sql 没建 due_date 的老库,补上这个字段
USE habit_tracker;

-- 加列(IF NOT EXISTS 在 MySQL 8.0.29+ 支持;更安全用动态 SQL)
SET @col_exists := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'todos' AND COLUMN_NAME = 'due_date'
);
SET @sql := IF(@col_exists = 0,
  'ALTER TABLE todos ADD COLUMN due_date DATETIME NULL AFTER done',
  'SELECT "due_date already exists" AS msg'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 加索引(同理)
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'todos' AND INDEX_NAME = 'idx_due_date'
);
SET @sql := IF(@idx_exists = 0,
  'ALTER TABLE todos ADD INDEX idx_due_date (due_date)',
  'SELECT "idx_due_date already exists" AS msg'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
