-- 用户偏好设置表
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INT PRIMARY KEY,
    target_calories INT DEFAULT 1800,
    home_layout JSON NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
