-- ============================================================
-- Phase 1 性能索引
-- ------------------------------------------------------------
-- 只加「按真实查询反推」的复合索引,不做无脑全表加索引。
-- 所有语句可重复执行(脚本会先查 information_schema 再决定是否 ALTER)。
--
-- 对照表(左:索引;右:它服务的查询)
--
-- todos(user_id, done, due_date)
--   → GET /api/todos?done=&date=       (repositories/todo_repo.list_for_user)
--   → 首页 dashboard 当天待办
--   实测(3 万行):47.42 ms → 0.46 ms(约 103x)
--   注:查询仍写成 `due_date = ? OR due_date IS NULL`。
--   曾经按"OR 会让索引失效"改成 UNION ALL,实测反而 0.57 ms 比 OR 的 0.46 ms 慢,
--   MySQL 对 OR 会做 index merge。所以收益来自索引本身,不是查询改写。
-- todos(user_id, done, created_at)
--   → GET /api/todos (无 date 过滤时的 ORDER BY created_at DESC)
-- transactions(user_id, time)
--   → /transactions/daily-stats、/summary、stats 的 60 天范围扫描
--   → ORDER BY time DESC
--   实测(3 万行,按月聚合):YEAR()/MONTH() 无索引 108.74 ms
--                              → 时间区间 + 索引 9.58 ms(约 11.3x)
--   注意:只加索引不改写查询只有 2.4x,必须同时把 YEAR()/MONTH() 换成半开区间。
-- transactions(user_id, type, time)
--   → 支出按天聚合(expense_by_date)、近 7 天收支汇总
-- goals(user_id, done)
--   → 成就 metric done_goal
-- reminders(user_id, enabled, time)
--   → 成就 metric early_reminder
--
-- 已有、无需再加:
--   checkins(user_id, checkin_date) UNIQUE   ← 打卡幂等
--   achievements(user_id, type)     UNIQUE   ← 防重复解锁
--   meals(user_id, date)                     ← 热量聚合
-- ============================================================

ALTER TABLE todos ADD INDEX idx_user_done_due (user_id, done, due_date);
ALTER TABLE todos ADD INDEX idx_user_done_created (user_id, done, created_at);
ALTER TABLE transactions ADD INDEX idx_user_time (user_id, time);
ALTER TABLE transactions ADD INDEX idx_user_type_time (user_id, type, time);
ALTER TABLE goals ADD INDEX idx_user_done (user_id, done);
ALTER TABLE reminders ADD INDEX idx_user_enabled_time (user_id, enabled, time);
