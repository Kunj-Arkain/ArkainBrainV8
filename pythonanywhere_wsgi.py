"""
PythonAnywhere WSGI Configuration Template

INSTRUCTIONS:
1. Copy this file's contents into your PythonAnywhere WSGI config file
   (found at /var/www/YOURUSERNAME_pythonanywhere_com_wsgi.py)
2. Replace YOURUSERNAME with your actual PythonAnywhere username
3. Save and reload the web app from the Web tab
"""

import sys
import os

# === CHANGE THIS to your PythonAnywhere username ===
USERNAME = 'YOURUSERNAME'

project_home = f'/home/{USERNAME}/slot-studio'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

# Set working directory so relative paths work
os.chdir(project_home)

# Import the Flask app
from web_app import app as application
