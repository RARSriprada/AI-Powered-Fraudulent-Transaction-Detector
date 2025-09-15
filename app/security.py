# security.py

import re
from cryptography.fernet import Fernet
from passlib.context import CryptContext
from jose import JWTError, jwt

from datetime import datetime, timedelta
from pydantic import BaseModel

# --- Encryption/Decryption ---
ENCRYPTION_KEY = b'qO9ZINaZA0SgA_f6pPqJb2e7FmN8cVd1uUa4gHk9l_I='  # must stay constant
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_data(data: str) -> str:
    if not data:
        return ""
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt safely. Fallback to last 4 of encrypted string if key mismatch."""
    if not encrypted_data:
        return ""
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except Exception:
        return f"****{encrypted_data[-4:]}" if len(encrypted_data) >= 4 else "****"

def mask_card_number(card_number: str) -> str:
    """Mask card numbers, showing only last 4 digits."""
    if not card_number:
        return ""
    digits = re.sub(r'\D', '', card_number)
    if not digits:
        return "Invalid Card Number"
    if len(digits) <= 4:
        return digits
    masked_prefix = '*' * (len(digits) - 4)
    masked = masked_prefix + digits[-4:]
    groups = [masked[i:i+4] for i in range(0, len(masked), 4)]
    return ' '.join(groups)

# --- Passwords + JWT ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password):
    return pwd_context.hash(password)

SECRET_KEY = "a_very_secret_key_for_our_project"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 2000

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

class TokenData(BaseModel):
    username: str | None = None
