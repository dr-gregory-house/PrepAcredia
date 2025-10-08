from datetime import datetime, timedelta
from app.utils.db import get_user_db_connection, get_content_db_connection
import math
import os
import json
from flask import current_app

# Define review schedule options
FASTER_REVIEW = {  # For more frequent reviews (intensive study)
    1: [0.0035, 0.0104, 0.0417, 0.125, 0.5],     # Easy (5min, 15min, 1hr, 3hr, 12hr)
    2: [0.0069, 0.0208, 0.0833, 0.25, 1],      # Medium-Easy (10min, 30min, 2hr, 6hr, 1day)
    3: [0.0104, 0.0417, 0.125, 0.5, 2],   # Medium (15min, 1hr, 3hr, 12hr, 2days)
    4: [0.0208, 0.0833, 0.25, 1, 3], # Medium-Hard (30min, 2hr, 6hr, 1day, 3days)
    5: [0.0417, 0.125, 0.5, 2, 5] # Hard (1hr, 3hr, 12hr, 2days, 5days)
}

SLOWER_REVIEW = {  # For less frequent reviews (long-term retention)
    1: [2, 7, 14, 30, 60],     # Easy
    2: [2, 5, 10, 21, 45],     # Medium-Easy
    3: [1, 3, 7, 14, 30],      # Medium
    4: [1, 2, 5, 10, 21],      # Medium-Hard
    5: [0.5, 1, 3, 7, 14]      # Hard
}

DEFAULT_REVIEW = {
    1: [1, 3, 7, 14, 30],      # Easy
    2: [1, 2, 5, 10, 20],      # Medium-Easy
    3: [1, 2, 4, 7, 14],       # Medium
    4: [0.5, 1, 3, 5, 10],     # Medium-Hard
    5: [0.02, 0.2, 0.5, 1, 2]     # Hard
}

# Spaced repetition intervals (in days) based on difficulty level
# Format: [1st review, 2nd review, 3rd review, 4th review, 5th review]
# These values represent the number of days to wait before showing the card again
# Each array corresponds to a difficulty level from 1 (easiest) to 5 (hardest)
INTERVALS = DEFAULT_REVIEW

# File to store global config
CONFIG_FILE_PATH = None

def _get_config_file_path():
    """Get the path to the config file"""
    global CONFIG_FILE_PATH
    if CONFIG_FILE_PATH is None:
        # Initialize the path when first needed
        try:
            # Use root_path instead of INSTANCE_PATH to determine where to store the config file
            instance_path = os.path.join(current_app.root_path, '..', 'instance')
            CONFIG_FILE_PATH = os.path.join(instance_path, 'spaced_repetition_config.json')
        except RuntimeError:
            # If outside app context, use a relative path
            CONFIG_FILE_PATH = 'instance/spaced_repetition_config.json'
    return CONFIG_FILE_PATH

def _get_presets_file_path():
    """Get the path to the presets file"""
    try:
        # Use root_path instead of INSTANCE_PATH to determine where to store presets
        instance_path = os.path.join(current_app.root_path, '..', 'instance')
        return os.path.join(instance_path, 'spaced_repetition_presets.json')
    except RuntimeError:
        # If outside app context, use a relative path
        return 'instance/spaced_repetition_presets.json'

def _load_config():
    """Load the spaced repetition configuration from file"""
    config_path = _get_config_file_path()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # After loading, if custom_intervals exists, convert its keys to integers
                if config.get('custom_intervals'):
                    try:
                        config['custom_intervals'] = {int(k): v for k, v in config['custom_intervals'].items()}
                    except (ValueError, TypeError):
                        # If conversion fails, treat it as invalid and revert to default
                        config['custom_intervals'] = None
                        config['schedule_type'] = 'default'
                return config
        except (json.JSONDecodeError, IOError):
            # Return default if file is corrupted or can't be read
            return {'schedule_type': 'default', 'custom_intervals': None}
    else:
        # Default configuration
        return {'schedule_type': 'default', 'custom_intervals': None}

def _save_config(config):
    """Save the spaced repetition configuration to file"""
    config_path = _get_config_file_path()
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f)
        return True
    except IOError:
        return False

def add_to_spaced_repetition(user_id, question_id, difficulty=3):
    """
    Add a question to the spaced repetition system after user answers it incorrectly.
    Difficulty is on a scale of 1-5 where 5 is hardest
    """
    # Make sure we're using the current global config
    load_global_schedule()
    
    conn = get_user_db_connection()
    
    # Calculate next review time (1 day by default for new entries)
    now = datetime.now()
    next_review = now + timedelta(days=INTERVALS[difficulty][0])
    
    try:
        # Check if this question is already in the system for this user
        existing = conn.execute(
            'SELECT id, repetition_count FROM spaced_repetition WHERE user_id = ? AND question_id = ?', 
            (user_id, question_id)
        ).fetchone()
        
        if existing:
            # Update existing entry
            repetition_count = min(existing['repetition_count'] + 1, 5)  # Cap at 5
            next_interval = INTERVALS[difficulty][min(repetition_count - 1, 4)]
            next_review = now + timedelta(days=next_interval)
            
            conn.execute(
                '''UPDATE spaced_repetition 
                   SET last_seen = ?, next_review = ?, repetition_count = ?, difficulty_level = ?
                   WHERE id = ?''',
                (now, next_review, repetition_count, difficulty, existing['id'])
            )
        else:
            # Insert new entry
            conn.execute(
                '''INSERT INTO spaced_repetition 
                   (user_id, question_id, last_seen, next_review, difficulty_level)
                   VALUES (?, ?, ?, ?, ?)''',
                (user_id, question_id, now, next_review, difficulty)
            )
        
        conn.commit()
    finally:
        conn.close()

def get_spaced_repetition_questions(user_id, count=5):
    """
    Get questions due for review based on spaced repetition schedule
    """
    user_conn = get_user_db_connection()
    try:
        # Find questions due for review
        now = datetime.now()
        
        # Get questions that are due for review
        spaced_questions = user_conn.execute(
            '''SELECT sr.question_id, sr.difficulty_level, sr.repetition_count,
               sr.next_review
               FROM spaced_repetition sr
               WHERE sr.user_id = ? AND sr.next_review <= ?
               ORDER BY sr.next_review
               LIMIT ?''',
            (user_id, now, count)
        ).fetchall()
        
        # Get options for each question
        result = []
        content_conn = get_content_db_connection()
        for q in spaced_questions:
            qrow = content_conn.execute('SELECT question_text_ru, question_text_en, hint, explanation FROM questions WHERE id = ?', (q['question_id'],)).fetchone()
            options = content_conn.execute('SELECT letter, text_ru, text_en, is_correct FROM options WHERE question_id = ? ORDER BY letter', (q['question_id'],)).fetchall()
            result.append({
                'id': q['question_id'],
                'text': f"{(qrow['question_text_ru'] if qrow else '')}\n{(qrow['question_text_en'] if qrow else '')}",
                'hint': (qrow['hint'] if qrow else ''),
                'explanation': (qrow['explanation'] if qrow else ''),
                'options': [
                    {
                        'id': o['letter'],
                        'text': f"{o['text_ru'] or ''}\n{o['text_en'] or ''}",
                        'is_correct': bool(o['is_correct'])
                    } for o in options
                ],
                'difficulty_level': q['difficulty_level'],
                'repetition_count': q['repetition_count'],
                'is_review': True  # Flag to indicate this is a review question
            })
        
        return result
    finally:
        user_conn.close()
        try:
            content_conn.close()
        except Exception:
            pass

def mark_question_reviewed(user_id, question_id, is_correct):
    """
    Update a question after it has been reviewed
    """
    conn = get_user_db_connection()
    try:
        # Find current data
        question_data = conn.execute(
            'SELECT repetition_count, difficulty_level FROM spaced_repetition WHERE user_id = ? AND question_id = ?',
            (user_id, question_id)
        ).fetchone()
        
        if not question_data:
            return  # Not found
        
        # Adjust difficulty based on answer
        difficulty = question_data['difficulty_level']
        if is_correct:
            # If correct, make it slightly easier (min difficulty 1)
            new_difficulty = max(difficulty - 1, 1)
            # Increase repetition count
            repetition_count = min(question_data['repetition_count'] + 1, 5)
        else:
            # If incorrect, make it harder (max difficulty 5)
            new_difficulty = min(difficulty + 1, 5)
            # Reset repetition count if still struggling
            repetition_count = 1
        
        # Calculate next review interval
        now = datetime.now()
        next_interval = INTERVALS[new_difficulty][min(repetition_count - 1, 4)]
        next_review = now + timedelta(days=next_interval)
        
        # Update record
        conn.execute(
            '''UPDATE spaced_repetition 
               SET last_seen = ?, next_review = ?, 
                   repetition_count = ?, difficulty_level = ?
               WHERE user_id = ? AND question_id = ?''',
            (now, next_review, repetition_count, new_difficulty, user_id, question_id)
        )
        
        conn.commit()
    finally:
        conn.close()

def remove_from_spaced_repetition(user_id, question_id):
    """
    Remove a question from spaced repetition (when user has mastered it)
    """
    conn = get_user_db_connection()
    try:
        conn.execute(
            'DELETE FROM spaced_repetition WHERE user_id = ? AND question_id = ?',
            (user_id, question_id)
        )
        conn.commit()
    finally:
        conn.close()

def set_review_schedule(schedule_type="default", custom_intervals=None):
    """
    Set the review schedule based on the provided schedule type
    This allows changing the review intervals globally
    
    schedule_type: 'default', 'faster', 'slower', or 'custom'
    custom_intervals: Custom intervals dictionary when schedule_type is 'custom'
    """
    global INTERVALS
    
    # Set schedule based on type
    if schedule_type == "faster":
        INTERVALS = FASTER_REVIEW
    elif schedule_type == "slower":
        INTERVALS = SLOWER_REVIEW
    elif schedule_type == "custom" and custom_intervals:
        # Validate custom intervals
        if _validate_custom_intervals(custom_intervals):
            INTERVALS = custom_intervals
        else:
            # Fall back to default if custom intervals are invalid
            INTERVALS = DEFAULT_REVIEW
            schedule_type = "default"
    else:
        INTERVALS = DEFAULT_REVIEW
        schedule_type = "default"
    
    # Save the configuration
    config = {
        'schedule_type': schedule_type,
        'custom_intervals': custom_intervals if schedule_type == 'custom' else None
    }
    _save_config(config)
    
    return INTERVALS

def _validate_custom_intervals(intervals):
    """Validate custom interval settings"""
    try:
        # Check if all difficulty levels are present
        for difficulty in range(1, 6):
            if difficulty not in intervals:
                return False
            
            # Check if each difficulty has 5 intervals
            if len(intervals[difficulty]) != 5:
                return False
            
            # Check if all intervals are valid numbers
            for interval in intervals[difficulty]:
                if not isinstance(interval, (int, float)) or interval < 0:
                    return False
        
        return True
    except (TypeError, KeyError):
        return False

def load_global_schedule():
    """
    Load the globally configured schedule from the config file
    This ensures all users get the same schedule as configured by admin
    """
    global INTERVALS
    
    config = _load_config()
    schedule_type = config.get('schedule_type', 'default')
    custom_intervals = config.get('custom_intervals')
    
    if schedule_type == "faster":
        INTERVALS = FASTER_REVIEW
    elif schedule_type == "slower":
        INTERVALS = SLOWER_REVIEW
    elif schedule_type == "custom" and custom_intervals and _validate_custom_intervals(custom_intervals):
        INTERVALS = custom_intervals
    else:
        INTERVALS = DEFAULT_REVIEW
    
    return INTERVALS

def get_current_schedule():
    """
    Get the current review schedule information
    Returns a dictionary with schedule information
    """
    # Ensure we're using the latest global config
    load_global_schedule()
    
    # Get the current schedule type
    config = _load_config()
    schedule_type = config.get('schedule_type', 'default')
    
    # Calculate total review duration for each difficulty level
    schedule_info = {
        "intervals": INTERVALS,
        "total_days": {},
        "description": {},
        "schedule_type": schedule_type
    }
    
    for difficulty, intervals in INTERVALS.items():
        total_days = sum(intervals)
        schedule_info["total_days"][difficulty] = total_days
        
        if total_days < 7:
            schedule_info["description"][difficulty] = f"Difficulty {difficulty}: Very frequent reviews (total {total_days:.1f} days)"
        elif total_days < 20:
            schedule_info["description"][difficulty] = f"Difficulty {difficulty}: Standard spacing (total {total_days:.1f} days)"
        else:
            schedule_info["description"][difficulty] = f"Difficulty {difficulty}: Extended spacing (total {total_days:.1f} days)"
    
    return schedule_info

def get_schedule_presets():
    """
    Get all saved schedule presets
    Returns a dictionary of preset name -> intervals
    """
    presets_path = _get_presets_file_path()
    
    if os.path.exists(presets_path):
        try:
            with open(presets_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    else:
        return {}

def save_schedule_preset(name, intervals):
    """
    Save a custom schedule preset
    
    name: Name of the preset
    intervals: Custom intervals dictionary
    """
    if not _validate_custom_intervals(intervals):
        return False
    
    presets_path = _get_presets_file_path()
    presets = get_schedule_presets()
    
    # Add/update the preset
    presets[name] = intervals
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(presets_path), exist_ok=True)
    
    try:
        with open(presets_path, 'w') as f:
            json.dump(presets, f)
        return True
    except IOError:
        return False

def delete_schedule_preset(name):
    """
    Delete a saved schedule preset
    
    name: Name of the preset to delete
    """
    presets_path = _get_presets_file_path()
    presets = get_schedule_presets()
    
    if name in presets:
        del presets[name]
        
        try:
            with open(presets_path, 'w') as f:
                json.dump(presets, f)
            return True
        except IOError:
            return False
    
    return False

# Initialize global schedule on module import
load_global_schedule() 