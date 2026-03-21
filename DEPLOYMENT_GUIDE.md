# QUICK-START GUIDE: Deploying Secure Application

## Pre-Deployment Checklist (< 30 minutes)

### 1. Generate Secrets

```bash
# Generate Django SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Generate strong passwords
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Store in .env file (NEVER commit to git!)
echo "SECRET_KEY=<paste-above>" >> .env
```

###  2. Set Environment Variables

Create `.env` with (see `.env.example` for full template):

```bash
# Core
SECRET_KEY=<generated-above>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com

# Database
DB_ENGINE=django.db.backends.postgresql
DB_NAME=iri_collections
DB_USER=postgres
DB_PASSWORD=<random-password>
DB_HOST=your-db-host.rds.amazonaws.com
DB_PORT=5432

# Email
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=<gmail-app-password>

# Payment
RAZORPAY_KEY_ID=rzp_live_xxxxx
RAZORPAY_KEY_SECRET=xxxxx

# Cache
REDIS_URL=redis://localhost:6379/1
```

### 3. Install Production Dependencies

```bash
pip install -r requirements.txt
pip install gunicorn psycopg2-binary redis python-json-logger
```

### 4. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create superuser (admin)
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### 5. Test Security Settings

```bash
# Check for security issues
python manage.py check --deploy

# Test rate limiting
python manage.py shell
>>> from core.security import is_rate_limited, audit_log
>>> is_rate_limited("test_key", 3, 3600)
False
>>> audit_log("TEST_LOG", severity="INFO")

# Verify CSRF protection
curl -X POST http://localhost:8000/api/store/cart/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: missing" \
  -d '{}' \
  # Should return 403 (forbidden)
```

### 6. Deploy

#### Option A: Heroku (Easiest for small projects)

```bash
# Install Heroku CLI
# Log in
heroku login

# Create app
heroku create iri-collections

# Set environment variables
heroku config:set SECRET_KEY=<from-step-1> \
                   DEBUG=False \
                   ALLOWED_HOSTS=iri-collections.herokuapp.com

# Deploy
git push heroku main

# Run migrations
heroku run python manage.py migrate
```

#### Option B: AWS/GCP/DigitalOcean (More control)

```bash
# Start with:
# - Linux server (Ubuntu 20.04 or later)
# - PostgreSQL database
# - Redis cache
# - Nginx reverse proxy
# - SSL certificate (Let's Encrypt)

# On server:
git clone <repo> /opt/iri-collections
cd /opt/iri-collections

# Install dependencies
pip install -r requirements.txt
pip install gunicorn

# Run migrations
python manage.py migrate

# Start with Gunicorn
gunicorn ecommerce.wsgi:application \
  --bind 127.0.0.1:8000 \
  --workers 4 \
  --worker-class=sync \
  --timeout=30 \
  --access-logfile - \
  --error-logfile -

# Configure Nginx as reverse proxy (see nginx.conf template)
# Configure SSL with Let's Encrypt (certbot)
# Set up systemd service for auto-restart
```

#### Option C: Docker (Reproducible)

```bash
# Build image
docker build -t iri-collections .

# Run container
docker run -e SECRET_KEY=<key> \
           -e DEBUG=False \
           -e ALLOWED_HOSTS=yourdomain.com \
           -p 8000:8000 \
           iri-collections

# Or use docker-compose.yml for full stack
docker-compose up -d
```

### 7. Verify Production Security

```bash
# Check HTTPS
curl -I https://yourdomain.com
# Look for: Strict-Transport-Security, X-Frame-Options, etc.

# Test authentication flow
curl -X POST https://yourdomain.com/api/auth/request-otp/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "action": "signup"}'

# Check rate limiting
for i in {1..5}; do
  curl -X POST https://yourdomain.com/api/auth/request-otp/ \
    -H "Content-Type: application/json" \
    -d '{"email": "test@example.com", "action": "signup"}'
done
# Response 5: 429 (too many requests)

# Review logs
tail -f logs/audit.log | grep "CRITICAL\|WARNING"
```

## Ongoing Maintenance

### Daily:
- Monitor error logs: `tail -f logs/app.log`
- Check audit logs for suspicious activity: `tail -f logs/audit.log`

### Weekly:
- Review failed login attempts
- Check disk space (logs grow)
- Monitor database size

### Monthly:
- Update dependencies: `pip list --outdated`
- Review audit trail for incidents
- Check Django security advisories

### Quarterly:
- Rotate secrets (if using long-lived keys)
- Security assessment
- Backup verification

### Yearly:
- Full security audit
- Penetration testing
- Architecture review

---

## Troubleshooting

### "Connection refused" when accessing Redis
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Start Redis if not running
redis-server
```

### "SECRET_KEY not set" error
```bash
# Ensure .env is loaded
source .env
echo $SECRET_KEY

# Or run with explicit env vars
SECRET_KEY=xxx DEBUG=False python manage.py runserver
```

### Rate limiting not working
```bash
# Verify Redis connection in app
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'value', 60)
>>> cache.get('test')
# Should return: 'value'
```

### 502 Bad Gateway
```bash
# Check application is running
ps aux | grep gunicorn

# Check logs for errors
tail -f logs/app.log | head -50

# Check Nginx config
nginx -t

# Restart services
systemctl restart gunicorn
systemctl restart nginx
```

---

## Security Checklist

Before going live:

```
Basic Setup:
  ☐ SECRET_KEY set and unique
  ☐ DEBUG = False
  ☐ ALLOWED_HOSTS configured
  ☐ HTTPS enabled (SSL certificate)

Database:
  ☐ PostgreSQL (not SQLite) in production
  ☐ Strong DB password (25+ chars)
  ☐ Daily backups configured
  ☐ SSL connection to DB enabled

Email:
  ☐ Gmail app password (not regular password)
  ☐ SMTP credentials set
  ☐ TLS enabled

Payments:
  ☐ Razorpay live keys (not test keys)
  ☐ Webhook signature verification enabled
  ☐ SSL certificate valid

Cache:
  ☐ Redis running
  ☐ Rate limiting tested
  ☐ Connection pool configured

Static Files:
  ☐ collectstatic run
  ☐ Served by CDN or Nginx
  ☐ Cache headers configured

Monitoring:
  ☐ Error tracking enabled (Sentry)
  ☐ Logging configured
  ☐ Alerting set up
  ☐ APM monitoring active

Backups:
  ☐ Database backups scheduled
  ☐ Backup restoration tested
  ☐ WAF enabled (CloudFlare)
  ☐ DDoS protection enabled
```

---

## Additional Resources

- **Django Deployment**: https://docs.djangoproject.com/en/5.1/howto/deployment/
- **OWASP Security**: https://owasp.org
- **Razorpay Docs**: https://razorpay.com/docs/
- **Let's Encrypt**: https://letsencrypt.org/
- **Nginx Config**: https://nginx.org/en/docs/
- **Docker Guide**: https://docs.docker.com

---

**Need Help?**  
Review IMPLEMENTATION_GUIDE.md for step-by-step setup instructions.  
Check SECURITY_AUDIT_REPORT.md for vulnerability details.
