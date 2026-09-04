-- 周报/月报表
CREATE TABLE IF NOT EXISTS reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    type VARCHAR(20) NOT NULL,
    period VARCHAR(20) NOT NULL,
    title VARCHAR(100),
    content TEXT,
    stats JSON,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_user_period (user_id, type, period),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
