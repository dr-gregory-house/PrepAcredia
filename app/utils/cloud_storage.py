import os
from google.cloud import storage
from flask import current_app
import logging
import time
import threading

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_db_from_bucket():
    """Download the user SQLite database file from GCS bucket to local /tmp directory"""
    bucket_name = os.environ.get('GCS_BUCKET_NAME', 'prepacredia-db')
    source_blob_name = os.environ.get('GCS_USER_DB_NAME', 'user.db')
    destination_file_name = current_app.config['USER_DB_PATH']
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(destination_file_name), exist_ok=True)
    
    try:
        # Initialize the GCS client
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        
        # Check if the blob exists in the bucket
        if blob.exists():
            # Compare generation/updated time with local file mtime to avoid needless overwrite
            remote_updated = blob.updated
            local_mtime = None
            try:
                if os.path.exists(destination_file_name):
                    local_mtime = os.path.getmtime(destination_file_name)
            except Exception:
                local_mtime = None

            should_download = True
            if remote_updated and local_mtime:
                try:
                    # blob.updated is aware datetime; compare to epoch
                    should_download = remote_updated.timestamp() > local_mtime
                except Exception:
                    should_download = True

            if should_download:
                logger.info(f"Downloading database from gs://{bucket_name}/{source_blob_name} to {destination_file_name}")
                blob.download_to_filename(destination_file_name)
                logger.info("Database download completed")
            else:
                logger.info("Local database is up-to-date with GCS; skipping download")
        else:
            logger.warning(f"Database file {source_blob_name} not found in bucket {bucket_name}. A new database will be created.")
    except Exception as e:
        logger.error(f"Error downloading database: {str(e)}")
        # If download fails, we'll continue with initialization which will create a new DB
        # This handles the first-time case as well

def upload_db_to_bucket():
    """Upload the user SQLite database file from local /tmp directory to GCS bucket"""
    bucket_name = os.environ.get('GCS_BUCKET_NAME', 'pedia-sqlite-db')
    destination_blob_name = os.environ.get('GCS_USER_DB_NAME', 'user.db')
    source_file_name = current_app.config['USER_DB_PATH']
    
    if not os.path.exists(source_file_name):
        logger.error(f"Local database file {source_file_name} not found")
        return
    
    try:
        # Initialize the GCS client
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        
        # Optional: set precondition to avoid overwriting newer remote versions if racing
        logger.info(f"Uploading database from {source_file_name} to gs://{bucket_name}/{destination_blob_name}")
        blob.upload_from_filename(source_file_name)
        logger.info("Database upload completed")
    except Exception as e:
        logger.error(f"Error uploading database: {str(e)}") 


class SyncManager:
    """Centralized manager to control DB sync behavior and timing."""

    def __init__(self):
        self._last_upload_epoch = 0.0
        self._last_uploaded_mtime = 0.0
        self._last_hourly_upload_epoch = 0.0
        self._lock = threading.Lock()

    def _get_db_path(self, app):
        return app.config.get('USER_DB_PATH')

    def _get_local_mtime(self, db_path):
        try:
            return os.path.getmtime(db_path) if db_path and os.path.exists(db_path) else 0.0
        except Exception:
            return 0.0

    def _debounce_seconds(self, app):
        return int(app.config.get('SYNC_DEBOUNCE_SECONDS', 10))

    def _hourly_interval(self, app):
        return int(app.config.get('SYNC_HOURLY_INTERVAL', 3600))

    def on_startup(self, app):
        """Run at app startup within app context."""
        try:
            if os.environ.get('K_SERVICE') and app.config.get('SYNC_ON_STARTUP', True):
                download_db_from_bucket()
        except Exception as e:
            logger.error(f"Startup download failed: {str(e)}")

        # Initialize internal timestamps from local file
        db_path = self._get_db_path(app)
        self._last_uploaded_mtime = self._get_local_mtime(db_path)
        now = time.time()
        self._last_upload_epoch = max(self._last_upload_epoch, now)
        self._last_hourly_upload_epoch = max(self._last_hourly_upload_epoch, now)

    def on_request_end(self, app, db_changed, user_active):
        """Called after each request. Decides whether to upload now (debounced) or due to hourly policy."""
        try:
            db_path = self._get_db_path(app)
            current_mtime = self._get_local_mtime(db_path)
            now = time.time()

            need_upload = False

            # Upload if DB changed or file mtime advanced
            if db_changed or (current_mtime > max(self._last_uploaded_mtime, 0.0)):
                need_upload = True

            # Hourly upload on activity
            if user_active and app.config.get('SYNC_HOURLY_ON_ACTIVITY', True):
                if now - self._last_hourly_upload_epoch >= self._hourly_interval(app):
                    need_upload = True
                    self._last_hourly_upload_epoch = now

            # Debounce
            if not need_upload or (now - self._last_upload_epoch) < self._debounce_seconds(app):
                return

            def _bg_upload():
                try:
                    # Ensure app context in background thread
                    with app.app_context():
                        upload_db_to_bucket()
                    # Update state on success
                    with self._lock:
                        self._last_uploaded_mtime = current_mtime
                        self._last_upload_epoch = time.time()
                except Exception as e:
                    logger.error(f"Background upload failed: {str(e)}")

            try:
                threading.Thread(target=_bg_upload, daemon=True).start()
            except Exception:
                # If thread fails, ignore
                pass
        except Exception as e:
            logger.error(f"on_request_end error: {str(e)}")

    def on_shutdown(self, app):
        """Best-effort upload on shutdown if enabled."""
        try:
            if app.config.get('SYNC_ON_SHUTDOWN', True):
                # Best-effort synchronous upload
                upload_db_to_bucket()
                # Update timestamps
                db_path = self._get_db_path(app)
                with self._lock:
                    self._last_uploaded_mtime = self._get_local_mtime(db_path)
                    self._last_upload_epoch = time.time()
        except Exception as e:
            logger.error(f"Shutdown upload failed: {str(e)}")