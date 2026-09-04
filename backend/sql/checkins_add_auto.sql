-- 给 checkins 表加 auto 字段(区分自动/手动打卡)
-- auto = 1:前端自动触发(登录后首页 onShow),不触发成就解锁
-- auto = 0(或 NULL):用户手动,正常走 check_and_unlock

ALTER TABLE checkins
  ADD COLUMN IF NOT EXISTS auto TINYINT(1) NOT NULL DEFAULT 0
  COMMENT '1=前端自动触发,0=用户手动';
