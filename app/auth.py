from datetime import datetime, timedelta
from typing import Optional, Dict
import hashlib
import hmac
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse

serializer = URLSafeTimedSerializer("parking_secret_key")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        algorithm, salt, stored_hash = hashed_password.split('$')
        if algorithm != 'sha256':
            return False
        computed_hash = hashlib.pbkdf2_hmac('sha256', plain_password.encode(), salt.encode(), 100000, dklen=64).hex()
        return hmac.compare_digest(computed_hash, stored_hash)
    except:
        return False

def get_password_hash(password: str) -> str:
    import secrets
    salt = secrets.token_urlsafe(16)
    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000, dklen=64)
    return f"sha256${salt}${hash_obj.hex()}"

def create_session_data(user_id: int, username: str, role: str) -> str:
    data = {"user_id": user_id, "username": username, "role": role, "timestamp": datetime.now().isoformat()}
    return serializer.dumps(data)

def decode_session_data(session_data: str) -> Optional[Dict]:
    try:
        data = serializer.loads(session_data, max_age=1800)
        return data
    except:
        return None

async def get_current_user(request: Request) -> Optional[Dict]:
    session_data = request.cookies.get("parking_session")
    if not session_data:
        return None
    return decode_session_data(session_data)

async def require_login(request: Request) -> Dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user

async def require_role(request: Request, *roles: str) -> Dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    if user["role"] not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return user

def set_session_cookie(response: RedirectResponse, user_id: int, username: str, role: str) -> RedirectResponse:
    session_data = create_session_data(user_id, username, role)
    response.set_cookie(key="parking_session", value=session_data, httponly=True, max_age=1800)
    return response

def clear_session_cookie(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie(key="parking_session")
    return response
