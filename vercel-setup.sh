#!/bin/bash

# Vercel Deployment Quick Start Script
# This script helps set up your Django app for Vercel deployment

set -e

echo "🚀 Iri Collections - Vercel Deployment Setup"
echo "=============================================="
echo ""

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "📦 Installing Vercel CLI..."
    npm install -g vercel
fi

echo "✅ Vercel CLI ready"
echo ""

# Generate new SECRET_KEY
echo "🔐 Generating new SECRET_KEY..."
SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
echo "SECRET_KEY=$SECRET_KEY"
echo ""

echo "📋 Required environment variables:"
echo "   1. DATABASE_URL (PostgreSQL connection)"
echo "   2. RAZORPAY_KEY_ID"
echo "   3. RAZORPAY_KEY_SECRET"
echo "   4. EMAIL_HOST_USER (Gmail)"
echo "   5. EMAIL_HOST_PASSWORD (Gmail app password)"
echo ""

# Verify git is clean
if [[ -n $(git status -s) ]]; then
    echo "⚠️  Your repository has uncommitted changes."
    echo "Please commit or stash changes before deploying:"
    echo "  git add ."
    echo "  git commit -m 'Prepare for Vercel deployment'"
fi
echo ""

echo "🔗 Login to Vercel..."
vercel auth

echo ""
echo "📤 Creating/updating Vercel project..."
vercel link

echo ""
echo "🎯 Next steps:"
echo ""
echo "1️⃣  Set environment variables in Vercel:"
echo "    vercel env add SECRET_KEY"
echo "    vercel env add DATABASE_URL"
echo "    vercel env add RAZORPAY_KEY_ID"
echo "    vercel env add RAZORPAY_KEY_SECRET"
echo ""
echo "   Or in Vercel dashboard:"
echo "   Settings → Environment Variables"
echo ""
echo "2️⃣  Deploy:"
echo "    git push origin main"
echo "    # or manual deploy:"
echo "    vercel --prod"
echo ""
echo "3️⃣  Create superuser:"
echo "    vercel run 'python manage.py createsuperuser'"
echo ""
echo "4️⃣  Monitor:"
echo "    vercel logs --tail"
echo ""

echo "✨ Deployment setup complete!"
