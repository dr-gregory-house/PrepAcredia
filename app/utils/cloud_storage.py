import os
from google.cloud import storage
from flask import current_app
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_db_from_bucket():
    """Download the user SQLite database file from GCS bucket to local /tmp directory"""
    bucket_name = os.environ.get('GCS_BUCKET_NAME', 'pedia-sqlite-db')
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
            logger.info(f"Downloading database from gs://{bucket_name}/{source_blob_name} to {destination_file_name}")
            blob.download_to_filename(destination_file_name)
            logger.info("Database download completed")
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
        
        logger.info(f"Uploading database from {source_file_name} to gs://{bucket_name}/{destination_blob_name}")
        blob.upload_from_filename(source_file_name)
        logger.info("Database upload completed")
    except Exception as e:
        logger.error(f"Error uploading database: {str(e)}") 