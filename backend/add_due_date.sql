-- 为 todos 表添加 due_date 字段
-- 在 MySQL 中执行此文件：source add_due_date.sql;

USE habit_tracker;

-- 检查字段是否存在，不存在则添加
SET @col_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'habit_tracker'
      AND TABLE_NAME = 'todos'
      AND COLUMN_NAME = 'due_date'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE todos ADD COLUMN due_date DATE DEFAULT NULL',
    'SELECT "due_date column already exists" AS msg'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
