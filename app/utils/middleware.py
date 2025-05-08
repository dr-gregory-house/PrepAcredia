from functools import wraps
from flask import session, request, g
from datetime import datetime, timedelta
from app.utils.user_tracking import update_user_activity, log_user_activity

def track_user_activity():
    """Middleware to track user activity and update session status"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Only track activity for logged-in users
            if 'user_id' in session and 'session_token' in session:
                try:
                    # Update last activity timestamp
                    update_user_activity(session['user_id'], session['session_token'])
                    
                    # Log certain activities
                    if request.endpoint:
                        activity_type = None
                        activity_details = None
                        
                        # Map endpoints to activity types
                        if request.endpoint == 'quiz.start_quiz':
                            activity_type = 'quiz_start'
                            activity_details = f"Started quiz with {request.args.get('num_questions', 'unknown')} questions"
                        elif request.endpoint == 'quiz.submit_quiz':
                            activity_type = 'quiz_complete'
                            activity_details = f"Completed quiz with score: {request.form.get('score', 'unknown')}"
                        elif request.endpoint == 'profile.update_profile':
                            activity_type = 'profile_update'
                            activity_details = "Updated profile information"
                        
                        if activity_type:
                            log_user_activity(session['user_id'], activity_type, activity_details)
                except Exception as e:
                    # Log error but don't break the request
                    print(f"Error tracking user activity: {str(e)}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator 