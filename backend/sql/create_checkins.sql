-- ============================================================
-- checkins 表(打卡记录)
-- ------------------------------------------------------------
-- 这张表原本没有建表脚本 —— 是早期手工建的,导致 sql/ 目录
-- 无法从零还原数据库(20 张表里只有 19 张有 DDL)。
-- 这里补上,DDL 取自线上实际结构。
--
-- 说明:
-- - uniq_user_date 唯一索引是打卡幂等的第一道保障(INSERT 冲突即视为已打卡)
-- - auto 列已包含在本脚本内,sql/checkins_add_auto.sql 因此不再需要
--   (那个脚本用的 ADD COLUMN IF NOT EXISTS 是 MariaDB 语法,MySQL 8 不支持)
-- ============================================================

CREATE TABLE IF NOT EXISTS checkins (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    checkin_date DATE NOT NULL,
    note VARCHAR(255) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    auto TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=前端自动触发,0=用户手动',
    PRIMARY KEY (id),
    UNIQUE KEY uniq_user_date (user_id, checkin_date),
    CONSTRAINT checkins_ibfk_1 FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
