from django.contrib import admin
from mongoengine import Document
from .models import User, Role

# Note: Django admin doesn't work with MongoEngine documents directly
# You'll need to create custom admin views or use a different admin interface
# For now, we'll leave this empty since we're using MongoDB
