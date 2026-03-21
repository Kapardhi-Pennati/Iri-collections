# IMPLEMENTATION GUIDE: Security Fixes

## Overview of Changes

All production-ready, secure code has been created in new files alongside your existing code. This guide shows you exactly how to integrate the security improvements.

## Files Created (New Security Infrastructure)

```
core/
  __init__.py
  security.py              → Cryptographic OTP, rate limiting, audit logging
  validators.py            → Input validation & sanitization
  throttling.py            → Custom DRF throttle classes
  settings_production.py   → Secure Django settings (REPLACE ecommerce/settings.py)

accounts/
  views_secure.py          → Secure auth views (REPLACE accounts/views.py)

payments/
  views_secure.py          → Secure payment views (REPLACE payments/views.py)

store/
  views_secure.py          → Secure store views (REPLACE store/views.py)
```

---

## STEP 1: Update Django Settings

**📋 ACTION**: Replace `ecommerce/settings.py` with `core/settings_production.py`

### What's Changed:

✅ **SECRET_KEY**: Now requires environment variable (fails fast if not set)  
✅ **DEBUG**: Enforced False in production (raises error if True)  
✅ **CSRF**: CSRF_COOKIE_HTTPONLY = True (prevents XSS token stealing)  
✅ **Session**: HttpOnly, Secure, SameSite=Strict cookies  
✅ **JWT**: Short-lived tokens (30 min), refresh rotation enabled  
✅ **HSTS**: Strict-Transport-Security headers enabled  
✅ **Security Headers**: CSP, X-Frame-Options, Content-Type-Options  
✅ **Rate Limiting**: Global + custom throttle classes  
✅ **Logging**: Structured JSON audit logging  
✅ **Caching**: Redis for rate limiting, sessions  
✅ **CORS**: Restricted to configured origins  

### Installation Steps:

1. Backup current `ecommerce/settings.py`:
   ```bash
   cp ecommerce/settings.py ecommerce/settings.py.backup
   ```

2. Copy secure settings:
   ```bash
   cp core/settings_production.py ecommerce/settings.py
   ```

3. Create logs directory:
   ```bash
   mkdir -p logs
   ```

4. Update `.env` with required variables:
   ```bash
   SECRET_KEY=<generate: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
   DEBUG=False
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   CSRF_TRUSTED_ORIGINS=https://yourdomain.com
   CORS_ALLOWED_ORIGINS=https://yourdomain.com
   
   # Email (required)
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-app-password
   
   # Razorpay (required)
   RAZORPAY_KEY_ID=rzp_live_xxxxx
   RAZORPAY_KEY_SECRET=xxxxx
   
   # Redis (for rate limiting/caching)
   REDIS_URL=redis://localhost:6379/1
   ```

---

## STEP 2: Update Authentication Views

**📋 ACTION**: Replace `accounts/views.py` with secure version

### What's Changed:

✅ **OTP Generation**: Uses `secrets` module (cryptographic random)  
✅ **Rate Limiting**: 3 OTPs/hour, 5 login attempts/hour  
✅ **Account Lockout**: Temporary lockout after 5 failed login attempts  
✅ **Input Validation**: Email normalization, phone validation  
✅ **Security**: Prevents email enumeration, audit logging every auth event  
✅ **Passwords**: Argon2 hashing already configured in settings  

### Implementation:

1. **Option A: Direct Replacement (Recommended)**
   ```bash
   cp accounts/views_secure.py accounts/views.py
   ```

2. **Option B: Manual Merge**
   - Copy `RequestOTPView`, `VerifyOTPView`, `RegisterView`, `LoginView`, `ResetPasswordView` from `views_secure.py`
   - Remove OLD views with same names
   - Ensure imports are updated

3. **Update `accounts/urls.py`** (no changes needed - endpoints are same)

4. **Install dependencies** if needed:
   ```bash
   pip install djangorestframework-simplejwt python-dotenv
   ```

---

## STEP 3: Update Payment Views

**📋 ACTION**: Replace `payments/views.py` with secure version

### What's Changed:

✅ **Signature Verification**: Uses constant-time HMAC comparison  
✅ **Order Validation**: Ensures user ownership before payment  
✅ **Idempotency**: Prevents double-processing of payments  
✅ **Error Handling**: Doesn't leak sensitive information  
✅ **Audit Logging**: All payment events logged  

### Implementation:

```bash
cp payments/views_secure.py payments/views.py
```

---

## STEP 4: Update Store Views

**📋 ACTION**: Replace `store/views.py` (partially) with secure functions

### What's Changed:

✅ **Order Creation**: Database row locking prevents race conditions  
✅ **Stock Validation**: Prevents overbooking even under high concurrency  
✅ **Pincode Verification**: SSRF protection, timeout, rate limiting  
✅ **Input Sanitization**: HTML escape, address validation  
✅ **Error Messages**: Don't leak information  

### Implementation:

1. Copy secure functions from `store/views_secure.py`:
   - `OrderCreateView`
   - `_calculate_shipping_fee()`
   - `PincodeVerifyView`
   - `WishlistView`

2. **Replace** these classes in your existing `store/views.py`

3. Update `store/urls.py` if needed (no URL changes)

---

## STEP 5: Add Core Package to INSTALLED_APPS

**📋 ACTION**: Update `ecommerce/settings.py`

Already done in `core/settings_production.py`, but if manually updating:

```python
INSTALLED_APPS = [
    # ... existing apps ...
    "core",  # Add this
    "accounts",
    "store",
    "payments",
]
```

---

## STEP 6: Set Up Redis for Caching (Production)

Rate limiting and session management require Redis:

### Local Development (Optional):
```bash
# Using Docker
docker run -d -p 6379:6379 redis:7

# Or install locally
brew install redis  # macOS
sudo apt-get install redis-server  # Ubuntu
```

### Production:
- Use managed Redis (AWS ElastiCache, Azure Cache, etc.)
- Set `REDIS_URL` in environment

### Fallback (Development):
```python
# In settings, if Redis unavailable:
USE_LOCAL_CACHE=true  # Uses in-memory cache (not for production)
```

---

## STEP 7: Create Logs Directory

```bash
mkdir -p logs
chmod 755 logs
```

Structured JSON logs will be written to:
- `logs/app.log` — Application events
- `logs/audit.log` — Security & admin actions

---

## STEP 8: Database Migrations (No Changes Required)

Existing models don't need schema changes. However, verify:

```bash
python manage.py migrate
```

---

## STEP 9: Testing

### Test Authentication Flow:
```bash
# 1. Request OTP
curl -X POST http://localhost:8000/api/auth/request-otp/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "action": "signup"}'

# 2. Verify OTP (check email for code)
curl -X POST http://localhost:8000/api/auth/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "otp_code": "123456"}'

# 3. Register
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "SecurePass123!",
    "password2": "SecurePass123!"
  }'

# 4. Login
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "SecurePass123!"}'
```

### Test Rate Limiting:
```bash
# Request 4 OTPs within 1 hour - should fail on 4th
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/auth/request-otp/ \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"test${i}@example.com\", \"action\": \"signup\"}"
  sleep 1
done
```

### Test Payment Security:
- Verify Razorpay webhook signature validation
- Test order creation with insufficient stock
- Verify user can only access own orders

---

## SECURITY CHECKLIST

- [ ] SECRET_KEY set in environment (unique for each environment)
- [ ] DEBUG = False in production
- [ ] HTTPS enforced (SECURE_SSL_REDIRECT = True)
- [ ] HSTS headers enabled
- [ ] Redis/Cache configured for rate limiting
- [ ] Email credentials set in .env
- [ ] Razorpay credentials set in .env
- [ ] Logs directory created and writable
- [ ] Database SSL/TLS configured (production)
- [ ] CSP headers reviewed and customized if needed
- [ ] CORS origins restricted to your domain
- [ ] Rate limits tested
- [ ] Webhook signature verification working
- [ ] Audit logs reviewed (check logs/audit.log)
- [ ] Password reset flow tested end-to-end

---

## Ongoing Maintenance

### Monitor Security:
```bash
# Watch audit logs in real-time
tail -f logs/audit.log

# Search for security events
grep "CRITICAL\|WARNING" logs/audit.log
```

### Regular Updates:
- Keep Django updated: `pip list --outdated`
- Monitor security advisories: https://www.djangoproject.com/weblog/
- Review rate limit metrics quarterly

### Admin Dashboard:
- Track failed login attempts
- Monitor payment failures
- Review high-value orders for fraud

---

## Troubleshooting

### Problem: "CRITICAL: SECRET_KEY not set"
**Solution**: Set `SECRET_KEY` environment variable in `.env`

### Problem: "Too many requests" errors
**Solution**: Rate limits are working. Increase windows in `core/throttling.py` if needed for development

### Problem: OTP emails not sending
**Solution**: Check EMAIL_* variables in `.env`. Use `EMAIL_BACKEND` console backend for testing

### Problem: Redis connection errors
**Solution**: Start Redis or set `USE_LOCAL_CACHE=true` for development

### Problem: CSRF token validation failing
**Solution**: Ensure `CSRF_TRUSTED_ORIGINS` includes your frontend domain

---

## Security Best Practices Going Forward

1. **Secrets Management**:
   - Never commit `.env` file
   - Rotate keys quarterly
   - Use separate keys per environment

2. **Database**:
   - Enable SSL connections (production)
   - Regular backups
   - Monitor slow queries

3. **API Security**:
   - Review rate limits periodically
   - Monitor for abuse patterns
   - Keep IP whitelist updated (if used)

4. **Logging & Monitoring**:
   - Centralize logs (Sentry, Splunk, DataDog)
   - Set alerts for critical events
   - Weekly audit log review

5. **Dependency Updates**:
   - `pip list --outdated`
   - Review changelogs before updating
   - Test in staging first

---

## Need Help?

- **Django Security Docs**: https://docs.djangoproject.com/en/5.1/topics/security/
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **Rate Limiting Strategy**: https://tools.ietf.org/html/draft-polli-ratelimit-headers

