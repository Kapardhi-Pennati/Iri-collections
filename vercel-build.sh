#!/bin/bash

# Vercel Build Script for Django Application
# This script runs during the Vercel build process

set -e  # Exit on error

echo "🔨 Building Django Application for Vercel..."

# Install dependencies (pip is run automatically, but we can add extras here)
echo "📦 Dependencies installing..."

# Create necessary directories
mkdir -p staticfiles
mkdir -p media

# Run Django management commands
echo "🗄️ Running database migrations..."
python manage.py migrate --no-input

echo "📦 Collecting static files..."
python manage.py collectstatic --no-input --clear

echo "✅ Build complete!"
