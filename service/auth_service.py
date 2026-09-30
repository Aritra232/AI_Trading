import hashlib
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional


class AuthService:
    def __init__(self, database_service=None):
        self.database_service = database_service
        self._memory_users: Dict[str, Dict[str, Any]] = {}
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}

        # Ensure default user exists on service startup
        self.seed_default_user()

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def seed_default_user(self):
        default_email = os.getenv("DEFAULT_USER_EMAIL", "bashirani@gmail.com").strip().lower()
        default_pass = os.getenv("DEFAULT_USER_PASSWORD", "12345678").strip()
        default_name = os.getenv("DEFAULT_USER_NAME", "Bashir Ani").strip()

        salt = secrets.token_hex(16)
        password_hash = self._hash_password(default_pass, salt)

        user_doc = {
            "user_id": "usr_bashirani",
            "email": default_email,
            "name": default_name,
            "role": "trader",
            "salt": salt,
            "password_hash": password_hash,
            "updated_at": self._utc_now_iso(),
        }

        # Store in memory cache
        self._memory_users[default_email] = user_doc

        # Store in MongoDB if available
        if self.database_service and self.database_service.is_enabled():
            try:
                collection = self.database_service.db.users
                existing = collection.find_one({"email": default_email})
                if not existing:
                    user_doc["created_at"] = self._utc_now_iso()
                    collection.insert_one(user_doc)
                else:
                    # Update password hash if needed so 12345678 is always guaranteed to work
                    collection.update_one(
                        {"email": default_email},
                        {
                            "$set": {
                                "salt": salt,
                                "password_hash": password_hash,
                                "name": default_name,
                                "role": "trader",
                                "updated_at": self._utc_now_iso(),
                            }
                        }
                    )
            except Exception as exc:
                print(f"[AuthService] Error seeding default user into MongoDB: {exc}")

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        norm_email = (email or "").strip().lower()
        clean_pass = (password or "").strip()

        if not norm_email or not clean_pass:
            return None

        user_doc = None

        # Try MongoDB first
        if self.database_service and self.database_service.is_enabled():
            try:
                user_doc = self.database_service.db.users.find_one({"email": norm_email})
            except Exception as exc:
                print(f"[AuthService] MongoDB query error: {exc}")

        # Fallback to memory
        if not user_doc:
            user_doc = self._memory_users.get(norm_email)

        if not user_doc:
            return None

        salt = user_doc.get("salt", "")
        expected_hash = user_doc.get("password_hash", "")
        calculated_hash = self._hash_password(clean_pass, salt)

        if not secrets.compare_digest(expected_hash, calculated_hash):
            return None

        # Credentials are valid -> Generate Auth Token
        token = f"tok_{secrets.token_hex(24)}"
        session_data = {
            "token": token,
            "user_id": user_doc.get("user_id", "usr_bashirani"),
            "email": user_doc.get("email"),
            "name": user_doc.get("name", "Bashir Ani"),
            "role": user_doc.get("role", "trader"),
            "created_at": self._utc_now_iso(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
        }

        # Store session in memory
        self._memory_sessions[token] = session_data

        # Store session in MongoDB
        if self.database_service and self.database_service.is_enabled():
            try:
                self.database_service.db.user_sessions.update_one(
                    {"token": token},
                    {"$set": session_data},
                    upsert=True
                )
            except Exception as exc:
                print(f"[AuthService] Error saving session to MongoDB: {exc}")

        return {
            "token": token,
            "user": {
                "id": session_data["user_id"],
                "email": session_data["email"],
                "name": session_data["name"],
                "role": session_data["role"],
            }
        }

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        clean_tok = (token or "").strip()
        if not clean_tok:
            return None

        # Check memory
        session = self._memory_sessions.get(clean_tok)
        if session:
            return session

        # Check DB
        if self.database_service and self.database_service.is_enabled():
            try:
                db_session = self.database_service.db.user_sessions.find_one({"token": clean_tok}, {"_id": 0})
                if db_session:
                    self._memory_sessions[clean_tok] = db_session
                    return db_session
            except Exception as exc:
                print(f"[AuthService] Error verifying token in DB: {exc}")

        return None
