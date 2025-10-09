import pytest
from app.utils.spaced_repetition import (
    add_to_spaced_repetition,
    mark_question_reviewed,
    set_review_schedule,
    _save_config,
    load_global_schedule,
    DEFAULT_REVIEW,
    FASTER_REVIEW
)
from app.utils.db import get_user_db_connection
from datetime import datetime, timedelta
import os

# Fixture to ensure a clean config file for each test
@pytest.fixture
def clean_config_file(monkeypatch):
    # Use a temporary config file for tests to avoid interfering with other tests or a real instance
    temp_dir = 'instance'
    temp_config_path = os.path.join(temp_dir, 'test_sr_config.json')

    # Ensure the directory exists
    os.makedirs(temp_dir, exist_ok=True)

    # Monkeypatch the config path to use our temporary file
    monkeypatch.setattr('app.utils.spaced_repetition.CONFIG_FILE_PATH', temp_config_path)

    # Clean up any existing config file before the test
    if os.path.exists(temp_config_path):
        os.remove(temp_config_path)

    yield temp_config_path  # Provide the path to the test if needed

    # Clean up the config file after the test
    if os.path.exists(temp_config_path):
        os.remove(temp_config_path)


def test_mark_question_reviewed_uses_latest_schedule(app, clean_config_file):
    """
    GIVEN the global spaced repetition schedule config file is changed
    WHEN mark_question_reviewed is called
    THEN it should use the most recently updated schedule to calculate the next review date.
    """
    with app.app_context():
        # 1. Setup: Ensure the initial state is the default schedule
        set_review_schedule('default')

        # Create a user and add a question to their SR list
        conn = get_user_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)", ('sr_user', 'sr@test.com', 'SR User', 'user', 1, 'hash'))
        user_id = cursor.lastrowid
        conn.commit()

        question_id = 1
        # This call uses the default schedule, which is fine for setup
        add_to_spaced_repetition(user_id, question_id, difficulty=3)

        # 2. Directly change the config file to 'faster'. This simulates an admin changing the
        # schedule in a separate process, so the in-memory `INTERVALS` variable is now stale.
        _save_config({'schedule_type': 'faster'})

        # 3. Mark the question as reviewed (correctly).
        # The buggy version of this function will not reload the schedule from the file.
        mark_question_reviewed(user_id, question_id, is_correct=True)

        # 4. Fetch the updated record
        updated_sr_item = conn.execute(
            'SELECT next_review FROM spaced_repetition WHERE user_id = ? AND question_id = ?',
            (user_id, question_id)
        ).fetchone()
        conn.close()

        # 5. Assert that the next_review date was calculated using the NEW schedule (FASTER_REVIEW)
        # With the bug, it will have been calculated using the old one (DEFAULT_REVIEW), and this test will fail.

        # Expected calculation for the *correct* behavior:
        # - Original difficulty was 3. is_correct=True -> new difficulty becomes 2.
        # - Original repetition count was 1. is_correct=True -> new repetition count becomes 2.
        # - The interval should come from FASTER_REVIEW[difficulty=2][rep_count_index=1] = 0.0208 days.
        expected_interval = timedelta(days=FASTER_REVIEW[2][1])

        # The buggy code will use DEFAULT_REVIEW[2][1], which is 2 days.

        next_review_date = datetime.strptime(updated_sr_item['next_review'], '%Y-%m-%d %H:%M:%S.%f')
        time_difference = next_review_date - datetime.now()

        # The assertion should fail here. We check if the calculated interval is close to the expected FASTER one.
        assert abs((time_difference - expected_interval).total_seconds()) < 5, \
            f"Next review interval is not based on the updated schedule. Expected ~{expected_interval}, but got ~{time_difference}."