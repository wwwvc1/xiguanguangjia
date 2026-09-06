-- ai_chat_logs 加 token 统计字段(每个 LLM 调用记一次)
USE habit_tracker;

SET @c1 := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_chat_logs' AND COLUMN_NAME = 'prompt_tokens');
SET @sql := IF(@c1 = 0,
  'ALTER TABLE ai_chat_logs ADD COLUMN prompt_tokens INT NULL AFTER model',
  'SELECT "prompt_tokens exists" AS msg');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @c2 := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_chat_logs' AND COLUMN_NAME = 'completion_tokens');
SET @sql := IF(@c2 = 0,
  'ALTER TABLE ai_chat_logs ADD COLUMN completion_tokens INT NULL AFTER prompt_tokens',
  'SELECT "completion_tokens exists" AS msg');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @c3 := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_chat_logs' AND COLUMN_NAME = 'total_tokens');
SET @sql := IF(@c3 = 0,
  'ALTER TABLE ai_chat_logs ADD COLUMN total_tokens INT NULL AFTER completion_tokens',
  'SELECT "total_tokens exists" AS msg');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 加索引方便按模型聚合
SET @i1 := (SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_chat_logs' AND INDEX_NAME = 'idx_model_tokens');
SET @sql := IF(@i1 = 0,
  'ALTER TABLE ai_chat_logs ADD INDEX idx_model_tokens (model, created_at, total_tokens)',
  'SELECT "idx_model_tokens exists" AS msg');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
