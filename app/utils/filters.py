import markdown2
from datetime import datetime
import html

def init_filters(app):
    """Initialize template filters and context processors"""

    @app.template_filter('markdown')
    def markdown_filter(text):
        """Safe markdown filter that escapes HTML before processing"""
        if not text:
            return ""
        # Escape HTML first to prevent XSS
        safe_text = html.escape(text)
        # Then process markdown
        return markdown2.markdown(safe_text)

    # Make zip available in templates
    @app.template_global('zip')
    def zip_filter(*args):
        return zip(*args)

    # Provide datetime to all templates
    @app.context_processor
    def inject_now():
        return {'now': datetime.now}

    # Register format_datetime filter
    app.jinja_env.filters['format_datetime'] = format_datetime

    # Register additional security filters
    @app.template_filter('escape_html')
    def escape_html_filter(text):
        """Escape HTML characters to prevent XSS"""
        return html.escape(str(text or ""))

def format_datetime(timestamp):
    """Format a timestamp as HH:MM DD-MM-YYYY"""
    if not timestamp:
        return ''
    
    # Convert string timestamp to datetime if needed
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                # Try another common format
                timestamp = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                return timestamp
    
    # Format the datetime
    return timestamp.strftime('%H:%M %d-%m-%Y')

def timeago(timestamp):
    """Convert a timestamp to a human-readable relative time string"""
    if not timestamp:
        return ''
    
    # Convert string timestamp to datetime if needed
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return timestamp
    
    now = datetime.now()
    diff = now - timestamp
    
    seconds = diff.total_seconds()
    minutes = seconds // 60
    hours = minutes // 60
    days = diff.days
    
    if seconds < 60:
        return 'just now'
    elif minutes < 60:
        return f'{int(minutes)} minute{"s" if minutes != 1 else ""} ago'
    elif hours < 24:
        return f'{int(hours)} hour{"s" if hours != 1 else ""} ago'
    elif days < 7:
        return f'{days} day{"s" if days != 1 else ""} ago'
    elif days < 30:
        weeks = days // 7
        return f'{weeks} week{"s" if weeks != 1 else ""} ago'
    elif days < 365:
        months = days // 30
        return f'{months} month{"s" if months != 1 else ""} ago'
    else:
        years = days // 365
        return f'{years} year{"s" if years != 1 else ""} ago'
