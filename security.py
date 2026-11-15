import time
import re
import html
import threading
from collections import defaultdict, deque
from functools import wraps
from flask import session, request, redirect, url_for, abort, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------- Rate Limiter ----------------- #

class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = defaultdict(deque)

    def is_allowed(self, key, max_requests=5, window_seconds=60):
        now = time.time()
        with self.lock:
            q = self.requests[key]
            # Expire old timestamps
            while q and q[0] <= now - window_seconds:
                q.popleft()

            if len(q) < max_requests:
                q.append(now)
                return True, max_requests - len(q)
            return False, 0

    def reset(self):
        """Resets rate limiting state (useful for test suites)."""
        with self.lock:
            self.requests.clear()

    def get_client_ip(self):
        if request.headers.get("X-Forwarded-For"):
            return request.headers.get("X-Forwarded-For").split(",")[0].strip()
        return request.remote_addr or "127.0.0.1"

rate_limiter = SlidingWindowRateLimiter()

def rate_limit(max_requests=5, window_seconds=60):
    """Decorator to rate-limit sensitive endpoints."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = rate_limiter.get_client_ip()
            key = f"{request.endpoint}:{ip}"
            allowed, remaining = rate_limiter.is_allowed(key, max_requests, window_seconds)
            if not allowed:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({
                        "success": False,
                        "message": f"Rate limit exceeded. Please wait {window_seconds} seconds before trying again."
                    }), 429
                return make_response(
                    f"<h3>429 Too Many Requests</h3><p>Rate limit exceeded. Please wait {window_seconds} seconds.</p>",
                    429
                )
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ----------------- Password Hashing ----------------- #

def hash_password(password: str) -> str:
    """Hashes password using scrypt or pbkdf2:sha256."""
    return generate_password_hash(password, method='scrypt')

def verify_password(password_hash: str, password: str) -> bool:
    """Securely verifies password against hash."""
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)

# ----------------- Input Sanitization & Validation ----------------- #

def sanitize_text(text: str, max_length: int = 150) -> str:
    """Escapes HTML entities and truncates excessive characters."""
    if not text:
        return ""
    cleaned = str(text).strip()[:max_length]
    return html.escape(cleaned)

def validate_student_id(student_id: str) -> bool:
    """Validates student ID allows only alphanumeric, hyphens, and underscores."""
    if not student_id or len(student_id) > 40:
        return False
    return bool(re.match(r'^[A-Za-z0-9_\-\.]+$', student_id))

def validate_email(email: str) -> bool:
    """Validates email format if provided."""
    if not email:
        return True # Optional
    return bool(re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email))

# ----------------- Role-Based Access Control (RBAC) ----------------- #

def login_required(f):
    """Requires user to be logged in (any role)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Authentication required."}), 401
            return redirect(url_for("login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Strictly requires logged-in user to have admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Admin authentication required."}), 401
            return redirect(url_for("login_page", next=request.path))
        if session.get("role") != "admin":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Access denied: Administrator privileges required."}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    """Ensures logged-in user is a student or admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("student_login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- Security Headers Middleware ----------------- #

def apply_security_headers(response):
    """Applies OWASP recommended security headers to all responses."""
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Cross-site scripting filter
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Permissions policy (camera allowed for self, no mic/geolocation)
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    
    # Content Security Policy (allows necessary CDNs for Bootstrap, FontAwesome, Chart.js)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob: https://ui-avatars.com https://placehold.co; "
        "connect-src 'self'; "
        "media-src 'self' data:; "
        "frame-ancestors 'self';"
    )
    response.headers["Content-Security-Policy"] = csp

    return response
