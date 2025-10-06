import os
import tempfile
import shutil
import pytest
import sqlite3


class TestConfig:
    SECRET_KEY = 'test'
    DEBUG = False
    TESTING = True
    # Use temporary files/directories per-test session
    CONTENT_DB_PATH = ''  # will be set in fixture
    USER_DB_PATH = ''  # will be set in fixture
    TEMP_DIR = ''  # will be set in fixture


@pytest.fixture(scope='session')
def _session_tmp_paths():
    base_dir = tempfile.mkdtemp(prefix='pediamcq-tests-')
    try:
        content_db = os.path.join(base_dir, 'master.db')
        user_db = os.path.join(base_dir, 'user.db')
        temp_dir = os.path.join(base_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        yield content_db, user_db, temp_dir, base_dir
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


@pytest.fixture()
def app(_session_tmp_paths, monkeypatch):
    # Ensure cloud-run behaviors are disabled
    monkeypatch.delenv('K_SERVICE', raising=False)

    # Point config to temporary files
    content_db, user_db, temp_dir, _ = _session_tmp_paths

    # Create an empty content DB file if missing so read-only open falls back
    if not os.path.exists(content_db):
        open(content_db, 'a').close()

    # Ensure spaced repetition config files are kept under temp instance dir
    inst_dir = os.path.join(_session_tmp_paths[3], 'instance')
    os.makedirs(inst_dir, exist_ok=True)
    monkeypatch.setenv('FLASK_INSTANCE_PATH', inst_dir)

    from app.app import create_app

    class _Cfg(TestConfig):
        CONTENT_DB_PATH = content_db
        USER_DB_PATH = user_db
        TEMP_DIR = temp_dir

    # Seed minimal content DB schema and one question with options
    _seed_content_db(content_db)

    application = create_app(_Cfg)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed_content_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY, question_text_ru TEXT, question_text_en TEXT, explanation TEXT, speciality TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS options (id INTEGER PRIMARY KEY AUTOINCREMENT, question_id INTEGER, letter TEXT, text_ru TEXT, text_en TEXT, is_correct INTEGER)')
        # Insert one question if empty
        cur = conn.execute('SELECT COUNT(*) FROM questions')
        if cur.fetchone()[0] == 0:
            conn.execute('INSERT INTO questions (id, question_text_ru, question_text_en, explanation, speciality) VALUES (?,?,?, ?, ?)', (1, 'Q RU', 'Q EN', 'Because...', 'General'))
            conn.executemany(
                'INSERT INTO options (question_id, letter, text_ru, text_en, is_correct) VALUES (?,?,?,?,?)',
                [
                    (1, 'A', 'Option A RU', 'Option A EN', 0),
                    (1, 'B', 'Option B RU', 'Option B EN', 1),
                    (1, 'C', 'Option C RU', 'Option C EN', 0),
                    (1, 'D', 'Option D RU', 'Option D EN', 0),
                ]
            )
        conn.commit()
    finally:
        conn.close()


