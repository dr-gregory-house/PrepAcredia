import markdown2
from datetime import datetime

def init_filters(app):
    """Initialize template filters and context processors"""
    
    @app.template_filter('markdown')
    def markdown_filter(text):
        return markdown2.markdown(text or "")
    
    # Make zip available in templates
    @app.template_global('zip')
    def zip_filter(*args):
        return __builtins__.zip(*args)
    
    # Provide datetime to all templates
    @app.context_processor
    def inject_now():
        return {'now': datetime.now} 