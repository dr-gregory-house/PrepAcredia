import os
import json
import random
import uuid
from flask import current_app

def generate_quiz_id():
    """Generate a unique ID for a quiz session"""
    return str(uuid.uuid4())[:8]  # Use first 8 chars of a UUID for brevity

def save_quiz_data(quiz_id, data):
    """Save quiz data to filesystem instead of session"""
    filepath = os.path.join(current_app.config['TEMP_DIR'], f"quiz_{quiz_id}.json")
    
    # Ensure temp directory exists
    try:
        os.makedirs(current_app.config['TEMP_DIR'], exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        return False

def load_quiz_data(quiz_id):
    """Load quiz data from filesystem"""
    filepath = os.path.join(current_app.config['TEMP_DIR'], f"quiz_{quiz_id}.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
            return data
        else:
            return None
    except Exception as e:
        return None

def delete_quiz_data(quiz_id):
    """Delete quiz data file when quiz is completed"""
    filepath = os.path.join(current_app.config['TEMP_DIR'], f"quiz_{quiz_id}.json")
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        else:
            return False
    except Exception as e:
        return False 