-- ============================================
-- 把 users.avatar 从 VARCHAR(255) 扩成 MEDIUMTEXT
-- 原因:小程序上传头像走 base64,单图常 >50KB,VARCHAR(255) 会截断
-- ============================================

ALTER TABLE users MODIFY COLUMN avatar MEDIUMTEXT;
