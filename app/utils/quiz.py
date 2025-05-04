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
        print(f"Quiz data saved to {filepath}")
        return True
    except Exception as e:
        print(f"Error saving quiz data: {str(e)}")
        return False

def load_quiz_data(quiz_id):
    """Load quiz data from filesystem"""
    filepath = os.path.join(current_app.config['TEMP_DIR'], f"quiz_{quiz_id}.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
            print(f"Loaded quiz data from {filepath}")
            return data
        else:
            print(f"Quiz data file not found: {filepath}")
    except Exception as e:
        print(f"Error loading quiz data: {str(e)}")
    return None

def delete_quiz_data(quiz_id):
    """Delete quiz data file when quiz is completed"""
    filepath = os.path.join(current_app.config['TEMP_DIR'], f"quiz_{quiz_id}.json")
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Deleted quiz data file: {filepath}")
            return True
        else:
            print(f"No quiz data file to delete: {filepath}")
    except Exception as e:
        print(f"Error deleting quiz data: {str(e)}")
    return False 