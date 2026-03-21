"""
Vercel Serverless WSGI Handler for Django

This handler serves the Django application on Vercel's serverless infrastructure.
"""

import os
import sys
import django
from django.conf import settings
from django.core.wsgi import get_wsgi_application

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce.settings")

# Setup Django
django.setup()

# Get WSGI application
app = get_wsgi_application()
