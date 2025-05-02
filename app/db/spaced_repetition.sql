-- Spaced Repetition System Tables

-- Table to track questions that were answered incorrectly for spaced repetition
CREATE TABLE IF NOT EXISTS spaced_repetition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_review TIMESTAMP NOT NULL, -- When to show this question again
    repetition_count INTEGER DEFAULT 1, -- How many times it's been reviewed
    difficulty_level INTEGER DEFAULT 3, -- 1-5 scale where 5 is hardest
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (question_id) REFERENCES questions(id),
    UNIQUE(user_id, question_id)
);

-- Table to store user performance data by topic for analytics dashboard
CREATE TABLE IF NOT EXISTS topic_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    correct_count INTEGER DEFAULT 0,
    incorrect_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id),
    UNIQUE(user_id, chapter_id)
);

-- Table to store daily activity for heatmap visualization
CREATE TABLE IF NOT EXISTS user_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    activity_date DATE NOT NULL,
    quiz_count INTEGER DEFAULT 0,
    question_count INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, activity_date)
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_spaced_rep_user_next ON spaced_repetition(user_id, next_review);
CREATE INDEX IF NOT EXISTS idx_topic_perf_user ON topic_performance(user_id);
CREATE INDEX IF NOT EXISTS idx_user_activity_date ON user_activity(user_id, activity_date); 