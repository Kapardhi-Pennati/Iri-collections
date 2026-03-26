# Iri Collections - E-Commerce Platform

A premium, full-featured jewelry e-commerce platform built with Django, Django REST Framework, and a custom high-performance vanilla JavaScript frontend.

## Enterprise Security Hardening
The platform has been hardened with a production-grade defensive security layer:
- **Secure Authentication**: Argon2 password hashing, cryptographically secure OTPs (`secrets`), and JWT session management.
- **Brute-Force Protection**: Account lockout (1 hour after 5 failed attempts) and endpoint-level throttling.
- **Integrity**: HMAC-SHA256 signature verification for all payment webhooks.
- **Infrastructure**: Strategic HTTP security headers (HSTS, CSP, X-Frame-Options), strict CSRF/CORS whitelisting, and secure cookie policies.
- **Audit Trail**: Detailed security-sensitive event logging in `logs/audit.log`.

## Features
- **Premium Design**: light Gold theme luxury aesthetic utilizing `Sans Funnel` typography.
- **Robust E-Commerce**: Product catalog, cart management, atomic order transactions with row-level locking.
- **Razorpay Integration**: Full UPI and Card payment gateway integration with safe webhook handling.
- **Printable Invoices**: Native browser-optimized print stylesheets for billing.

## Local Development Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Setup your environment variables**:
   Create a `.env` file in the root directory (see `.env.example`):
   ```
   SECRET_KEY=your_secret_key
   DEBUG=True
   ALLOWED_HOSTS= localhost
   RAZORPAY_KEY_ID=your_test_key
   RAZORPAY_KEY_SECRET=your_test_secret
   ```

3. **Infrastrucutre**:
   Ensure [Redis](https://redis.io/) is installed and running for session/rate limiting:
   ```bash
   redis-server
   ```

4. **Run Migrations & Seed Data**:
   ```bash
   python manage.py migrate
   python manage.py seed_data
   ```

5. **Run Server**:
   ```bash
   python manage.py runserver
   ```

## Production Deployment (Vercel)

The repository is configured for serverless deployment on Vercel with automatic scaling and zero-downtime deploys.

### Quick Start

1. **Setup Vercel CLI**:
   ```bash
   npm install -g vercel
   ```

2. **Configure Database**:
   **Neon**: [neon.tech](https://neon.tech) - Free PostgreSQL serverless

3. **Run Deployment Setup**:
   ```bash
   bash vercel-setup.sh
   ```

4. **Set Environment Variables**:

5. **Deploy**:
   ```bash
   git push origin main  
   # or
   vercel --prod
   ```

### Architecture

- **Runtime**: Python 3.13 Serverless Functions
- **Server**: Vercel wsgi
- **Static Files**: WhiteNoise CDN
- **Database**: PostgreSQL (managed)
- **Media**: Local storage or AWS S3 (optional)
*(Note: When `DEBUG=False`, the app automatically enforces strict HTTPS/SSL security headers and switches to WhiteNoise for static file serving.)*
