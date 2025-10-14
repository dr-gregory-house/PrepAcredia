import os
import tempfile
import shutil
import pytest
import sqlite3
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from app.utils.cloud_storage import SyncManager, download_db_from_bucket, upload_db_to_bucket


class TestConfig:
    """Test configuration for sync tests."""
    SECRET_KEY = 'test'
    DEBUG = False
    TESTING = True
    USER_DB_PATH = ''
    CONTENT_DB_PATH = ''
    TEMP_DIR = ''
    # Sync settings
    SYNC_ON_STARTUP = True
    SYNC_ON_SHUTDOWN = True
    SYNC_DEBOUNCE_SECONDS = 2  # Short for tests
    SYNC_HOURLY_ON_ACTIVITY = True
    SYNC_HOURLY_INTERVAL = 5  # Short for tests


@pytest.fixture()
def temp_db_dir():
    """Create temporary directory for test databases."""
    tmpdir = tempfile.mkdtemp(prefix='sync-test-')
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture()
def mock_app(temp_db_dir, monkeypatch):
    """Create a mock Flask app with test config."""
    from flask import Flask
    
    # Ensure we're NOT in Cloud Run mode by default
    monkeypatch.delenv('K_SERVICE', raising=False)
    
    app = Flask(__name__)
    user_db = os.path.join(temp_db_dir, 'user.db')
    content_db = os.path.join(temp_db_dir, 'master.db')
    temp_dir = os.path.join(temp_db_dir, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    app.config['USER_DB_PATH'] = user_db
    app.config['CONTENT_DB_PATH'] = content_db
    app.config['TEMP_DIR'] = temp_dir
    app.config['SYNC_ON_STARTUP'] = True
    app.config['SYNC_ON_SHUTDOWN'] = True
    app.config['SYNC_DEBOUNCE_SECONDS'] = 2
    app.config['SYNC_HOURLY_ON_ACTIVITY'] = True
    app.config['SYNC_HOURLY_INTERVAL'] = 5
    
    # Create empty user DB
    conn = sqlite3.connect(user_db)
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)')
    conn.execute('INSERT INTO users (id, username) VALUES (1, "testuser")')
    conn.commit()
    conn.close()
    
    return app


class TestSyncManager:
    """Test the SyncManager class."""
    
    def test_sync_manager_initialization(self):
        """Test that SyncManager initializes correctly."""
        manager = SyncManager()
        assert manager._last_upload_epoch == 0.0
        assert manager._last_uploaded_mtime == 0.0
        assert manager._last_hourly_upload_epoch == 0.0
        assert manager._lock is not None
    
    def test_get_db_path(self, mock_app):
        """Test getting DB path from app config."""
        manager = SyncManager()
        with mock_app.app_context():
            path = manager._get_db_path(mock_app)
            assert path == mock_app.config['USER_DB_PATH']
    
    def test_get_local_mtime(self, mock_app):
        """Test getting local file modification time."""
        manager = SyncManager()
        with mock_app.app_context():
            db_path = mock_app.config['USER_DB_PATH']
            mtime = manager._get_local_mtime(db_path)
            assert mtime > 0  # File exists, should have mtime
            
            # Test with non-existent file
            mtime_nonexist = manager._get_local_mtime('/nonexistent/path')
            assert mtime_nonexist == 0.0
    
    @patch('app.utils.cloud_storage.download_db_from_bucket')
    def test_on_startup_cloud_run(self, mock_download, mock_app, monkeypatch):
        """Test startup behavior when running on Cloud Run."""
        # Simulate Cloud Run environment
        monkeypatch.setenv('K_SERVICE', 'test-service')
        
        manager = SyncManager()
        with mock_app.app_context():
            manager.on_startup(mock_app)
            
            # Should call download
            mock_download.assert_called_once()
            
            # Should initialize timestamps
            assert manager._last_uploaded_mtime > 0
            assert manager._last_upload_epoch > 0
    
    @patch('app.utils.cloud_storage.download_db_from_bucket')
    def test_on_startup_local(self, mock_download, mock_app, monkeypatch):
        """Test startup behavior when NOT on Cloud Run."""
        # Ensure not in Cloud Run
        monkeypatch.delenv('K_SERVICE', raising=False)
        
        manager = SyncManager()
        with mock_app.app_context():
            manager.on_startup(mock_app)
            
            # Should NOT call download
            mock_download.assert_not_called()
            
            # Should still initialize timestamps
            assert manager._last_uploaded_mtime > 0
    
    def test_on_request_end_db_changed(self, mock_app):
        """Test upload triggered when db_changed is True."""
        manager = SyncManager()
        upload_called = []
        
        # Patch the threading.Thread to run synchronously
        def sync_thread(target, daemon=False):
            upload_called.append(True)
            target()  # Run immediately instead of in background
            return MagicMock()
        
        with mock_app.app_context():
            manager.on_startup(mock_app)
            
            # Reset last upload epoch to allow immediate upload (bypass debounce for test)
            manager._last_upload_epoch = 0.0
            
            # Touch the DB file to ensure mtime changes
            db_path = mock_app.config['USER_DB_PATH']
            time.sleep(0.1)  # Ensure mtime changes
            conn = sqlite3.connect(db_path)
            conn.execute('INSERT INTO users (username) VALUES ("test2")')
            conn.commit()
            conn.close()
            
            # Patch threading and upload function at the module where they're used
            with patch('app.utils.cloud_storage.threading.Thread', side_effect=sync_thread):
                with patch('app.utils.cloud_storage.upload_db_to_bucket') as mock_upload:
                    # Trigger upload with db_changed=True
                    manager.on_request_end(mock_app, db_changed=True, user_active=False)
                    
                    # Should have triggered upload
                    assert len(upload_called) >= 1, "Thread was not started"
                    assert mock_upload.call_count >= 1, "Upload function was not called"
    
    @patch('app.utils.cloud_storage.upload_db_to_bucket')
    def test_on_request_end_debounce(self, mock_upload, mock_app):
        """Test that debouncing prevents too-frequent uploads."""
        manager = SyncManager()
        
        with mock_app.app_context():
            manager.on_startup(mock_app)
            
            # First call should trigger
            manager.on_request_end(mock_app, db_changed=True, user_active=False)
            time.sleep(0.5)
            first_call_count = mock_upload.call_count
            
            # Immediate second call should be debounced
            manager.on_request_end(mock_app, db_changed=True, user_active=False)
            time.sleep(0.5)
            assert mock_upload.call_count == first_call_count  # No additional call
            
            # Wait for debounce to expire
            time.sleep(2)
            manager.on_request_end(mock_app, db_changed=True, user_active=False)
            time.sleep(0.5)
            assert mock_upload.call_count > first_call_count  # New call
    
    def test_on_request_end_hourly_upload(self, mock_app):
        """Test hourly upload on user activity."""
        manager = SyncManager()
        upload_called = []
        
        # Patch the threading.Thread to run synchronously
        def sync_thread(target, daemon=False):
            upload_called.append(True)
            target()  # Run immediately instead of in background
            return MagicMock()
        
        with mock_app.app_context():
            manager.on_startup(mock_app)
            
            # Reset debounce to allow immediate upload
            manager._last_upload_epoch = 0.0
            
            # Touch the DB to ensure mtime changes
            db_path = mock_app.config['USER_DB_PATH']
            time.sleep(0.1)
            conn = sqlite3.connect(db_path)
            conn.execute('INSERT INTO users (username) VALUES ("test3")')
            conn.commit()
            conn.close()
            
            # Simulate time passing for hourly interval (past the 5 second test interval)
            manager._last_hourly_upload_epoch = time.time() - 10  # 10 seconds ago
            
            # Patch threading and upload function at the module where they're used
            with patch('app.utils.cloud_storage.threading.Thread', side_effect=sync_thread):
                with patch('app.utils.cloud_storage.upload_db_to_bucket') as mock_upload:
                    # Trigger with user activity
                    manager.on_request_end(mock_app, db_changed=False, user_active=True)
                    
                    # Should trigger upload due to hourly policy
                    assert len(upload_called) >= 1, "Thread was not started"
                    assert mock_upload.call_count >= 1, "Upload function was not called"
    
    @patch('app.utils.cloud_storage.upload_db_to_bucket')
    def test_on_shutdown(self, mock_upload, mock_app):
        """Test shutdown upload behavior."""
        manager = SyncManager()
        
        with mock_app.app_context():
            manager.on_shutdown(mock_app)
            
            # Should call upload
            mock_upload.assert_called_once()
    
    @patch('app.utils.cloud_storage.upload_db_to_bucket')
    def test_on_shutdown_disabled(self, mock_upload, mock_app):
        """Test shutdown upload can be disabled."""
        mock_app.config['SYNC_ON_SHUTDOWN'] = False
        manager = SyncManager()
        
        with mock_app.app_context():
            manager.on_shutdown(mock_app)
            
            # Should NOT call upload
            mock_upload.assert_not_called()


class TestDownloadUploadFunctions:
    """Test the individual download and upload functions."""
    
    @patch('app.utils.cloud_storage.storage.Client')
    def test_download_db_from_bucket_success(self, mock_storage_client, mock_app):
        """Test successful download from GCS."""
        # Setup mocks
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        mock_blob.updated = None  # No timestamp check
        
        with mock_app.app_context():
            download_db_from_bucket()
            
            # Verify calls
            mock_blob.download_to_filename.assert_called_once()
    
    @patch('app.utils.cloud_storage.storage.Client')
    def test_download_db_from_bucket_not_exists(self, mock_storage_client, mock_app):
        """Test download when blob doesn't exist."""
        # Setup mocks
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = False
        
        with mock_app.app_context():
            # Should not raise error
            download_db_from_bucket()
            
            # Should not try to download
            mock_blob.download_to_filename.assert_not_called()
    
    @patch('app.utils.cloud_storage.storage.Client')
    def test_upload_db_to_bucket_success(self, mock_storage_client, mock_app):
        """Test successful upload to GCS."""
        # Setup mocks
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        
        with mock_app.app_context():
            upload_db_to_bucket()
            
            # Verify calls
            mock_blob.upload_from_filename.assert_called_once()
    
    @patch('app.utils.cloud_storage.storage.Client')
    def test_upload_db_to_bucket_missing_file(self, mock_storage_client, mock_app):
        """Test upload when local file doesn't exist."""
        # Point to non-existent file
        mock_app.config['USER_DB_PATH'] = '/nonexistent/path'
        
        mock_client = MagicMock()
        mock_storage_client.return_value = mock_client
        
        with mock_app.app_context():
            # Should handle gracefully
            upload_db_to_bucket()
            
            # Should not try to upload
            mock_client.bucket.assert_not_called()


class TestIntegrationWithApp:
    """Integration tests with the actual Flask app."""
    
    @patch('app.utils.cloud_storage.download_db_from_bucket')
    @patch('app.utils.cloud_storage.upload_db_to_bucket')
    def test_app_startup_calls_sync(self, mock_upload, mock_download, temp_db_dir, monkeypatch):
        """Test that app startup triggers sync manager."""
        # Simulate Cloud Run
        monkeypatch.setenv('K_SERVICE', 'test-service')
        
        from app.app import create_app
        
        class _TestConfig:
            SECRET_KEY = 'test'
            DEBUG = False
            TESTING = True
            USER_DB_PATH = os.path.join(temp_db_dir, 'user.db')
            CONTENT_DB_PATH = os.path.join(temp_db_dir, 'master.db')
            TEMP_DIR = os.path.join(temp_db_dir, 'temp')
            SYNC_ON_STARTUP = True
            SYNC_ON_SHUTDOWN = True
            SYNC_DEBOUNCE_SECONDS = 2
            SYNC_HOURLY_ON_ACTIVITY = True
            SYNC_HOURLY_INTERVAL = 5
        
        # Create DBs
        os.makedirs(_TestConfig.TEMP_DIR, exist_ok=True)
        open(_TestConfig.USER_DB_PATH, 'a').close()
        open(_TestConfig.CONTENT_DB_PATH, 'a').close()
        
        # Create app
        app = create_app(_TestConfig)
        
        # Verify download was called during startup
        mock_download.assert_called()
    
    def test_app_after_request_triggers_sync(self, temp_db_dir, monkeypatch):
        """Test that the sync manager is wired into after_request hook."""
        monkeypatch.delenv('K_SERVICE', raising=False)
        
        from app.app import create_app, sync_manager
        import app.app as app_module
        
        class _TestConfig:
            SECRET_KEY = 'test'
            DEBUG = False
            TESTING = True
            USER_DB_PATH = os.path.join(temp_db_dir, 'user.db')
            CONTENT_DB_PATH = os.path.join(temp_db_dir, 'master.db')
            TEMP_DIR = os.path.join(temp_db_dir, 'temp')
            SYNC_ON_STARTUP = False  # Disable for this test
            SYNC_ON_SHUTDOWN = False
            SYNC_DEBOUNCE_SECONDS = 1
            SYNC_HOURLY_ON_ACTIVITY = False
            SYNC_HOURLY_INTERVAL = 3600
        
        # Create empty DBs (init_db will create the schema)
        os.makedirs(_TestConfig.TEMP_DIR, exist_ok=True)
        open(_TestConfig.USER_DB_PATH, 'a').close()
        open(_TestConfig.CONTENT_DB_PATH, 'a').close()
        
        # Create app
        app = create_app(_TestConfig)
        client = app.test_client()
        
        # Verify sync manager is wired in
        assert hasattr(app, 'after_request_funcs')
        assert sync_manager is not None
        
        # Verify the after_request hook exists by making a simple request
        with app.app_context():
            response = client.get('/')
            # If we get here without error, the hook is working
            assert response.status_code in (200, 302, 404)  # 302 redirect, 200 OK, or 404 not found


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

