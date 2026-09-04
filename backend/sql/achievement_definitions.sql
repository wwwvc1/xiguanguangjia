-- 成就定义表(管理员配置)
CREATE TABLE IF NOT EXISTS achievement_definitions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(64) NOT NULL UNIQUE COMMENT '唯一标识,如 todo_count_10',
  name VARCHAR(100) NOT NULL COMMENT '显示名',
  description VARCHAR(255) COMMENT '达成说明',
  icon VARCHAR(16) DEFAULT '🏅' COMMENT 'emoji 图标',
  metric_type VARCHAR(64) NOT NULL COMMENT '评估类型:todo_count/done_todo/goal/done_goal/tx/meal/early_reminder/tx_income_total/tx_expense_total/savings_days',
  target_value INT NOT NULL DEFAULT 1 COMMENT '达成阈值',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  sort_order INT NOT NULL DEFAULT 0 COMMENT '展示顺序,小的在前',
  created_by INT NULL COMMENT '创建者 admin id',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_active (is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='成就定义';

-- 把旧的 7 个硬编码成就迁移到新表(可重复执行,IGNORE 重复 code)
INSERT IGNORE INTO achievement_definitions (code, name, description, icon, metric_type, target_value, is_active, sort_order) VALUES
  ('first_todo',      '起步',       '创建第一条待办',                 '🌱', 'todo_count',        1,  1, 10),
  ('todo_10',         '执行者',     '完成 10 条待办',                  '✅', 'done_todo',         10, 1, 20),
  ('todo_50',         '自律者',     '完成 50 条待办',                  '🏅', 'done_todo',         50, 1, 30),
  ('first_goal',      '有目标的人', '创建第一个目标',                  '🎯', 'goal_count',        1,  1, 40),
  ('goal_done',       '梦想成真',   '完成第一个目标',                  '🏆', 'done_goal',         1,  1, 50),
  ('bookkeeper',      '记账达人',   '记录 10 笔收支',                  '📒', 'tx_count',          10, 1, 60),
  ('foodie',          '美食家',     '记录 5 餐饮食',                   '🍱', 'meal_count',        5,  1, 70),
  ('early_bird',      '早起的人',   '添加一个早于 7:00 的提醒',         '🌅', 'early_reminder',    1,  1, 80);
