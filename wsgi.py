import os
import sys

# Add the current directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask application
from run import app

# This is the WSGI entry point
application = app 