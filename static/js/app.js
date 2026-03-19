/* ═══════════════════════════════════════════════════════════════
   Iri Collections — Core JavaScript
   JWT Auth, API Client, Cart Management, Lazy Loading
   ═══════════════════════════════════════════════════════════════ */

// ─── Utility ───────────────────────────────────────────────────
function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ─── API Client ────────────────────────────────────────────────
const API = {
    base: '/api',

    getToken() {
        return localStorage.getItem('access_token');
    },

    setTokens(tokens) {
        localStorage.setItem('access_token', tokens.access);
        localStorage.setItem('refresh_token', tokens.refresh);
    },

    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
    },

    getUser() {
        const u = localStorage.getItem('user');
        return u ? JSON.parse(u) : null;
    },

    setUser(user) {
        localStorage.setItem('user', JSON.stringify(user));
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    isAdmin() {
        const user = this.getUser();
        return user && user.role === 'admin';
    },

    async refreshToken() {
        const refresh = localStorage.getItem('refresh_token');
        if (!refresh) return false;
        try {
            const res = await fetch(`${this.base}/auth/refresh/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh })
            });
            if (!res.ok) return false;
            const data = await res.json();
            localStorage.setItem('access_token', data.access);
            if (data.refresh) localStorage.setItem('refresh_token', data.refresh);
            return true;
        } catch { return false; }
    },

    async request(endpoint, options = {}) {
        const url = `${this.base}${endpoint}`;
        const headers = { ...options.headers };

        if (!(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }

        const token = this.getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        let res = await fetch(url, { ...options, headers });

        // Auto-refresh on 401
        if (res.status === 401 && token) {
            const refreshed = await this.refreshToken();
            if (refreshed) {
                headers['Authorization'] = `Bearer ${this.getToken()}`;
                res = await fetch(url, { ...options, headers });
            } else {
                this.clearTokens();
                window.location.href = '/login/';
                return null;
            }
        }
        return res;
    },

    async get(endpoint) {
        const res = await this.request(endpoint);
        if (!res) return null;
        return res.json();
    },

    async post(endpoint, data) {
        const res = await this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (!res) return null;
        return { ok: res.ok, status: res.status, data: await res.json() };
    },

    async patch(endpoint, data) {
        const res = await this.request(endpoint, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
        if (!res) return null;
        return { ok: res.ok, status: res.status, data: await res.json() };
    },

    async delete(endpoint, data = null) {
        const opts = { method: 'DELETE' };
        if (data) opts.body = JSON.stringify(data);
        const res = await this.request(endpoint, opts);
        if (!res) return null;
        try { return { ok: res.ok, data: await res.json() }; }
        catch { return { ok: res.ok, data: null }; }
    },
};

// ─── Toast Notifications ───────────────────────────────────────
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            this.container.id = 'toast-container';
            document.body.appendChild(this.container);
        }
    },

    show(message, type = 'info', duration = 3000) {
        if (!this.container) this.init();
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        this.container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('show'));
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 400);
        }, duration);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error'); },
    info(msg) { this.show(msg, 'info'); }
};

// ─── Lazy Loading ──────────────────────────────────────────────
function initLazyLoading() {
    const images = document.querySelectorAll('img[data-src]');
    if (!images.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                img.addEventListener('load', () => img.classList.add('loaded'));
                observer.unobserve(img);
            }
        });
    }, { rootMargin: '100px' });

    images.forEach(img => observer.observe(img));
}

// ─── Update Nav State ──────────────────────────────────────────
function updateNavbar() {
    const authLinks = document.getElementById('auth-links');
    const userMenu = document.getElementById('user-menu');
    const cartCount = document.getElementById('cart-count');
    const adminLink = document.getElementById('admin-link');

    if (!authLinks) return;

    if (API.isLoggedIn()) {
        const user = API.getUser();
        authLinks.classList.add('hidden');
        if (userMenu) {
            userMenu.classList.remove('hidden');
            const nameEl = userMenu.querySelector('.user-name');
            if (nameEl) nameEl.textContent = user?.full_name || user?.email || 'Account';
        }
        if (adminLink && API.isAdmin()) {
            adminLink.classList.remove('hidden');
        }
        // Load cart count
        updateCartCount();
    } else {
        authLinks.classList.remove('hidden');
        if (userMenu) userMenu.classList.add('hidden');
        if (adminLink) adminLink.classList.add('hidden');
        if (cartCount) cartCount.textContent = '0';
    }
}

async function updateCartCount() {
    if (!API.isLoggedIn()) return;
    try {
        const cart = await API.get('/store/cart/');
        const badge = document.getElementById('cart-count');
        if (badge && cart) badge.textContent = cart.item_count || '0';
    } catch {}
}

function logout() {
    API.clearTokens();
    Toast.success('Logged out successfully');
    setTimeout(() => window.location.href = '/', 500);
}

// ─── Format Currency ───────────────────────────────────────────
function formatPrice(price) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(price);
}

// ─── Product Card HTML ─────────────────────────────────────────
function productCardHTML(product) {
    const discount = product.compare_price
        ? Math.round((1 - product.price / product.compare_price) * 100)
        : 0;
    const imgSrc = product.display_image || product.image_url || product.image || '';

    return `
        <div class="card product-card" onclick="window.location.href='/product/${product.slug}/'" data-product-id="${product.id}">
            <div class="product-card-image">
                <img data-src="${imgSrc}" alt="${product.name}" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'%3E%3Crect fill='%2316161f' width='400' height='400'/%3E%3C/svg%3E">
                ${discount > 0 ? `<span class="product-card-badge">${discount}% Off</span>` : ''}
                <div class="product-card-actions">
                    <button class="product-card-action-btn" onclick="event.stopPropagation(); addToCart(${product.id})" title="Add to Cart">🛒</button>
                </div>
            </div>
            <div class="product-card-info">
                <div class="product-card-category">${escapeHTML(product.category_name || '')}</div>
                <h3 class="product-card-name">${escapeHTML(product.name)}</h3>
                <div class="product-card-price">
                    <span class="current">${formatPrice(product.price)}</span>
                    ${product.compare_price ? `<span class="original">${formatPrice(product.compare_price)}</span>` : ''}
                    ${discount > 0 ? `<span class="discount">${discount}% off</span>` : ''}
                </div>
            </div>
        </div>
    `;
}

// ─── Add to Cart ───────────────────────────────────────────────
async function addToCart(productId, quantity = 1) {
    if (!API.isLoggedIn()) {
        Toast.info('Please login to add items to cart');
        setTimeout(() => window.location.href = '/login/', 1000);
        return;
    }
    const res = await API.post('/store/cart/', { product_id: productId, quantity });
    if (res && res.ok) {
        Toast.success('Added to cart!');
        updateCartCount();
    } else {
        Toast.error(res?.data?.error || 'Failed to add to cart');
    }
}

// ─── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    Toast.init();
    updateNavbar();
    initLazyLoading();

    // Mobile nav toggle
    const toggle = document.getElementById('nav-toggle');
    const links = document.getElementById('nav-links');
    if (toggle && links) {
        toggle.addEventListener('click', () => links.classList.toggle('open'));
    }
});
