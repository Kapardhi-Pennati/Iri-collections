# Iri Collections — Ethereal Jewelry Curation

A premium, full-stack jewelry e-commerce platform built with **Django**, **Django REST Framework**, and the **Lumina Ether** minimalist luxury design system.

## ✨ Lumina Ether Design System
The platform features a custom-built, high-performance frontend inspired by the "Lumina Ether" aesthetic:
- **Aesthetic**: Minimalist luxury with glassmorphism, refined spacing, and ethereal light-play.
- **Typography**: Powered by `Noto Serif` (Headlines) and `Manrope` (Body/Labels) via Google Fonts.
- **Layout**: Asymmetric editorial grids and "Bento Box" category layouts for a modern curation experience.
- **Iconography**: Clean, lightweight `Material Symbols Outlined` (Weight: 300).

## 🛡️ Enterprise Security Hardening
- **Secure Authentication**: Argon2 hashing, cryptographically secure OTPs, and JWT session management.
- **Brute-Force Protection**: Account lockout after 5 failed attempts and endpoint-level throttling.
- **Transaction Integrity**: HMAC-SHA256 signature verification for all Stripe webhooks.
- **Infrastructure**: Strict HSTS, CSP, X-Frame-Options, CSRF/CORS whitelisting, and secure cookie policies.
- **Audit Trace**: Consolidated event logging for all financial and security-sensitive mutations.

## 🚀 Key Features
- **Wishlist Curation**: Heart icons and toggle logic for users to save their favorite pieces.
- **Editorial Catalog**: Asymmetric grid with vertical offsets and advanced filtering (Category, Search, Sort).
- **Stripe Integration**: Secure checkout flow using Stripe Checkout Sessions and Webhook fulfillment.
- **Shopping Bag**: Premium cart experience with real-time updates and "Secure Shipping" calculations.
- **Currency**: Fully localized for **INR (₹)** with precise rounding and formatting.
- **Printable Invoices**: Native browser-optimized checkout receipts and order tracking.

## 🛠️ Local Development Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Create a `.env` file in the root directory (refer to `.env.example`):
   ```bash
   SECRET_KEY=your_django_secret
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   
   # Stripe Keys (https://dashboard.stripe.com/test/apikeys)
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

3. **Infrastructure**:
   Ensure [Redis](https://redis.io/) is running for session management and rate limiting:
   ```bash
   redis-server
   ```

4. **Initialize Database**:
   ```bash
   python manage.py migrate
   python manage.py seed_data
   ```

5. **Run Development Server**:
   ```bash
   python manage.py runserver
   ```

## ☁️ Production Deployment (Vercel)
The platform is optimized for serverless deployment on Vercel with automatic horizontal scaling.

- **Runtime**: Python 3.13 Serverless Functions
- **Static Assets**: WhiteNoise CDN with aggressive caching
- **Database**: PostgreSQL (Neon.tech recommended)
- **Security Protocols**: Enforced HTTPS/SSL and secure cookie flags when `DEBUG=False`.

---
*© 2026 Iri Collections. All rights reserved.*
