from fastapi import Depends, HTTPException, status
from fastapi.requests import Request
from typing import Optional

from .auth import get_current_user

async def get_user(request: Request) -> Optional[dict]:
    return await get_current_user(request)

async def require_login(request: Request) -> dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user

def require_role(*roles: str):
    async def checker(request: Request):
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user
    return checker