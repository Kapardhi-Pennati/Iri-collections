# Iri Collections - E-Commerce Platform

A premium, full-featured jewelry e-commerce platform built with Django, Django REST Framework, and a custom high-performance vanilla JavaScript frontend.

## Features
- **Premium Design**: Dark theme luxury aesthetic utilizing `Bodoni Moda` and `Montserrat` typography.
- **Robust E-Commerce**: Product catalog, cart management, atomic order transactions, inventory control.
- **Secure Authentication**: Argon2 password hashing and JWT token-based auth.
- **Razorpay Integration**: Full UPI and Card payment gateway integration.
- **Printable Invoices**: Native browser-optimized print stylesheets for generation of order bills.
- **Security First**: DOM-based XSS protection, Django rate limiting, HTTP security headers, and Schema CheckConstraints.

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
   ALLOWED_HOSTS=127.0.0.1,localhost
   RAZORPAY_KEY_ID=your_test_key
   RAZORPAY_KEY_SECRET=your_test_secret
   ```

3. **Run Migrations & Seed Data**:
   ```bash
   python manage.py migrate
   python manage.py seed_data
   ```

4. **Run Server**:
   ```bash
   python manage.py runserver
   ```

## Production Deployment (Render, Heroku, Railway)

The repository is completely configured for modern PaaS deployment.

1. Connect your Github Repository to your hosting provider.
2. The platform will automatically detect the `Procfile` and `requirements.txt`.
3. In your hosting provider's **Environment Variables** settings, inject the following:
   - `SECRET_KEY` = (A long, random cryptographic string)
   - `DEBUG` = `False`
   - `ALLOWED_HOSTS` = `yourwebsite.com`
   - `PROD_DOMAINS` = `yourwebsite.com` (Used for strict CORS and CSRF protection)
   - `RAZORPAY_KEY_ID` = (Your Live Razorpay Key)
   - `RAZORPAY_KEY_SECRET` = (Your Live Razorpay Secret)
   - `DATABASE_URL` = (Provided by your host's managed PostgreSQL addon)

*(Note: When `DEBUG=False` is detected, the app automatically switches to WhiteNoise static file handling and enforces strict HTTPS/SSL security headers.)*
