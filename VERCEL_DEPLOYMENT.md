# 🚀 Vercel Deployment Guide - Iri Collections

Complete guide to deploy your Django e-commerce application to Vercel.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step-by-Step Setup](#step-by-step-setup)
3. [Environment Variables](#environment-variables)
4. [Database Setup](#database-setup)
5. [Deployment](#deployment)
6. [Post-Deployment](#post-deployment)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Vercel account (free tier available)
- Git repository (GitHub, GitLab, or Bitbucket)
- PostgreSQL database (e.g., Neon, Railway, AWS RDS)
- Razorpay merchant account

---

## Step-by-Step Setup

### 1. Create Vercel Account

1. Go to [vercel.com](https://vercel.com)
2. Sign up with GitHub, GitLab, or Bitbucket
3. Create a new project

### 2. Connect Your Repository

1. Click "Add New..." → "Project"
2. Select your Git repository
3. Vercel will auto-detect Django framework
4. Click "Deploy"

### 3. Configure Environment Variables

After connecting, configure environment variables:

1. Go to **Settings** → **Environment Variables**
2. Add all variables from `.env.example`
3. **Make sure these are set:**
   - `SECRET_KEY` (generate new one)
   - `DEBUG=false`
   - `ALLOWED_HOSTS` (your Vercel domain)
   - `DATABASE_URL` (PostgreSQL connection)
   - `RAZORPAY_KEY_ID` & `RAZORPAY_KEY_SECRET`

### 4. Build Command

Vercel will automatically detect and run:
```bash
python manage.py collectstatic --no-input && python manage.py migrate
```

---

## Environment Variables

### Required Variables

```env
# Django Core
SECRET_KEY=your-secret-key-here
DEBUG=false
ALLOWED_HOSTS=yourdomain.vercel.app,www.yourdomain.vercel.app,yourdomain.com

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:5432/db_name

# Razorpay
RAZORPAY_KEY_ID=rzp_live_xxxxx
RAZORPAY_KEY_SECRET=xxxxx

# Security
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
```

### Optional Variables

```env
# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=app-password

# AWS S3 (for media storage)
AWS_ACCESS_KEY_ID=xxxxx
AWS_SECRET_ACCESS_KEY=xxxxx
AWS_STORAGE_BUCKET_NAME=bucket-name
```

---

## Database Setup

### Option 1: PostgreSQL (Recommended)

#### Using Neon (Free, serverless)

1. Go to [neon.tech](https://neon.tech)
2. Create new project
3. Copy connection string: `postgres://user:password@host/db`
4. Add to Vercel environment: `DATABASE_URL`

#### Using Railway

1. Go to [railway.app](https://railway.app)
2. Create new PostgreSQL service
3. Copy connection URL
4. Add to Vercel environment: `DATABASE_URL`

#### Using AWS RDS

1. Follow AWS RDS setup for PostgreSQL
2. Copy database endpoint
3. Format: `postgresql://username:password@endpoint:5432/dbname`
4. Add to Vercel environment: `DATABASE_URL`

### Option 2: SQLite (Not recommended for production)

SQLite won't work on Vercel's ephemeral file system. Use PostgreSQL instead.

---

## Deployment

### Automatic Deployment (Recommended)

Push to your main branch:
```bash
git push origin main
```

Vercel will automatically:
1. Build the application
2. Run migrations
3. Collect static files
4. Deploy

### Manual Deployment

```bash
vercel --prod
```

### Rollback

```bash
vercel rollback
```

---

## Post-Deployment

### 1. Add Your Domain

1. Go to Vercel project settings
2. **Domains** → Add custom domain
3. Update DNS records at your domain registrar
4. Wait for DNS to propagate (5-30 minutes)

### 2. Verify Deployment

```bash
curl https://yourdomain.com/api/health/  # Verify if you have a health endpoint
```

### 3. Create Superuser

Run this one-time command:
```bash
vercel env pull .env.production
python manage.py createsuperuser --settings ecommerce.settings
```

Or use Vercel CLI to run commands:
```bash
vercel run "python manage.py createsuperuser"
```

### 4. Test Payment Gateway

1. Go to admin: `https://yourdomain.com/admin`
2. Login with superuser credentials
3. Test Razorpay integration with test keys first

### 5. Monitor Logs

```bash
vercel logs  # View deployment logs
```

---

## Architecture

```
Vercel Serverless (PythonRuntime 3.13)
    ↓
Django App (ecommerce/)
    ↓
PostgreSQL (Neon/Railway/RDS)
Razorpay API ← Payment Processing
AWS S3 ← Media Storage (optional)
```

---

## Performance Optimization

### 1. Enable Caching

```python
# In ecommerce/settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

### 2. Static Files

Static files are served from Vercel's CDN automatically via WhiteNoise middleware.

### 3. Database Connection Pooling

For high traffic, use connection pooling in `DATABASE_URL`:
```
postgresql://user:password@host:5432/db?sslmode=require&connect_timeout=10
```

---

## Security Checklist

- ✅ `SECRET_KEY` is strong (32+ chars, random)
- ✅ `DEBUG=false` in production
- ✅ `ALLOWED_HOSTS` includes all domains
- ✅ PostgreSQL credentials safe (use managed database)
- ✅ HTTPS enabled (automatic on Vercel)
- ✅ CORS configured correctly
- ✅ CSRF protection enabled
- ✅ Security headers set
- ✅ Razorpay keys safe (use environment variables)

---

## Troubleshooting

### 500 Error on Deploy

```bash
# Check build logs
vercel logs --tail

# Common causes:
# - Missing environment variables
# - Database migration errors
# - Missing SECRET_KEY

# Solution:
vercel env pull .env.production  # Pull env vars locally
python manage.py migrate  # Test migrations locally
```

### Database Connection Error

```
FATAL: too many connections
```

Solution: Enable connection pooling in DATABASE_URL:
```
postgresql://user:password@host:5432/db?connect_timeout=10
```

### Static Files Not Loading

```
# Ensure WhiteNoiseMiddleware is in settings.py
# and static files are collected during build
```

### CORS Errors

```python
# Update CORS settings to include Vercel domain
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
    "https://www.yourdomain.com",
    "https://yourdomain.vercel.app"
]
```

### Razorpay Not Working

1. Verify API keys are correct
2. Check if mode is TEST or LIVE
3. Ensure webhook URL is set to: `https://yourdomain.com/api/payment/webhook/`

---

## Monitoring & Maintenance

### View Logs

```bash
vercel logs  # Last 100 logs
vercel logs --tail  # Stream logs in real-time
```

### Database Backups

- **Neon**: Automatic backups every 24 hours
- **Railway**: Enable backups in dashboard
- **AWS RDS**: Configure automated snapshots

### Performance Monitoring

- Use Vercel Analytics: Settings → Analytics
- Monitor database query times
- Check API response times

---

## Scaling

### Increase Serverless Function Memory

1. Go to Project Settings → Functions
2. Increase memory for API functions
3. Redeploy

### Database Scaling

For high traffic:
1. Upgrade to RDS Multi-AZ
2. Add read replicas
3. Implement caching layer (Redis)

---

## Useful Commands

```bash
# Deploy
vercel --prod

# View deployments
vercel ls

# Rollback to previous
vercel rollback

# Pull environment variables
vercel env pull .env.production

# Run management command
vercel run "python manage.py createsuperuser"

# Stream logs
vercel logs --tail

# View function stats
vercel inspect
```

---

## Final Checklist

- ✅ Repository pushed to GitHub/GitLab
- ✅ Vercel project created
- ✅ Environment variables configured
- ✅ PostgreSQL database set up
- ✅ Custom domain added (optional)
- ✅ Superuser created
- ✅ Razorpay webhooks configured
- ✅ HTTPS verified
- ✅ Admin panel accessible
- ✅ Payment flow tested

---

## Support

For Vercel issues: [vercel.com/support](https://vercel.com/support)
For Django issues: [django.readthedocs.io](https://django.readthedocs.io)
For Razorpay issues: [razorpay.com/docs](https://razorpay.com/docs)

---

**Deployment Date**: March 21, 2026  
**Django Version**: 5.1  
**Python Version**: 3.13  
**Vercel Runtime**: Python 3.13
