import hmac
import hashlib

def generate_csrf_token(uid: str, session_nonce: str, secret: str) -> str:
    msg = f"{uid}:{session_nonce}".encode("utf-8")
    key = secret.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()

def validate_csrf_token(
    token: str, uid: str, session_nonce: str, secret: str
) -> bool:
    expected_token = generate_csrf_token(uid, session_nonce, secret)
    return hmac.compare_digest(token, expected_token)
