"""
Authentication for Tree-of-Thought Debugging Tool.
Handles user registration, login, JWT tokens, and password hashing.
Uses MongoDB users collection; pass db from SessionManager.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from pymongo.database import Database
from pymongo.collection import Collection
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

# JWT is optional at import so app can run without it for non-auth flows
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    jwt = None


class AuthError(Exception):
    """Raised when auth fails (invalid credentials, missing user, etc.)."""
    pass


class AuthManager:
    """Manages users and JWT auth. Uses existing MongoDB database."""

    def __init__(self, db: Database):
        self.db = db
        self.users: Collection = db.users
        self._ensure_indexes()
        self._jwt_secret = os.getenv("JWT_SECRET")
        if not self._jwt_secret:
            logger.warning("JWT_SECRET not set - auth tokens will be insecure or fail")

    def _ensure_indexes(self) -> None:
        try:
            self.users.create_index("email", unique=True)
            self.users.create_index("created_at")
            logger.debug("Auth users indexes ensured")
        except Exception as e:
            logger.warning("Auth index creation: %s", e)

    def register(self, email: str, password: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new user. Returns user dict (no password). Raises AuthError if email exists."""
        email = _normalize_email(email)
        if not email or not password.strip():
            raise AuthError("Email and password are required")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters")

        existing = self.users.find_one({"email": email})
        if existing:
            raise AuthError("An account with this email already exists")

        user_id = str(uuid.uuid4())
        doc = {
            "_id": user_id,
            "email": email,
            "password_hash": generate_password_hash(password, method="scrypt"),
            "name": (name or "").strip() or None,
            "created_at": datetime.utcnow(),
        }
        self.users.insert_one(doc)
        logger.info("Registered user: %s", email)
        return _user_doc_to_response(doc)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Verify credentials and return user + token. Raises AuthError on failure."""
        email = _normalize_email(email)
        if not email or not password:
            raise AuthError("Email and password are required")

        doc = self.users.find_one({"email": email})
        if not doc:
            raise AuthError("Invalid email or password")
        if not check_password_hash(doc.get("password_hash", ""), password):
            raise AuthError("Invalid email or password")

        user = _user_doc_to_response(doc)
        token = self.create_token(user["id"], user["email"])
        return {"user": user, "token": token}

    def create_token(self, user_id: str, email: str, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT for the given user."""
        if not JWT_AVAILABLE or not jwt:
            raise AuthError("JWT support not available (install PyJWT)")
        if not self._jwt_secret:
            raise AuthError("JWT_SECRET is not configured")

        payload = {
            "sub": user_id,
            "email": email,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + (expires_delta or timedelta(days=7)),
        }
        return jwt.encode(payload, self._jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate JWT; return payload dict or None."""
        if not token or not JWT_AVAILABLE or not jwt or not self._jwt_secret:
            return None
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            return payload
        except Exception:
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return user dict (no password) or None."""
        doc = self.users.find_one({"_id": user_id})
        return _user_doc_to_response(doc) if doc else None

    def search_users(self, q: str, limit: int = 20) -> list:
        """Search users by name or email (case-insensitive). Returns list of user dicts (no password)."""
        q = (q or "").strip()
        if not q or len(q) < 2:
            return []
        import re
        pattern = re.escape(q)
        regex = re.compile(pattern, re.IGNORECASE)
        cursor = self.users.find({
            "$or": [
                {"email": regex},
                {"name": regex},
            ]
        }).limit(limit)
        return [_user_doc_to_response(doc) for doc in cursor]


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _user_doc_to_response(doc: Dict) -> Dict[str, Any]:
    """Build public user dict from DB document."""
    return {
        "id": doc["_id"],
        "email": doc["email"],
        "name": doc.get("name"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }
