"""Authentication router."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.db_models import User, RefreshToken
from app.services.auth import create_access_token, get_current_user, verify_password, SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import uuid

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    country: str = "United Kingdom"
    phone: str | None = None
    address: str | None = None

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    country: str
    phone: str | None
    address: str | None
    is_admin: bool

# --- Refresh Token Helpers ---
REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_refresh_token(user_id: int) -> str:
    return str(uuid.uuid4())

# --- Endpoints ---

@router.post("/auth/register", response_model=LoginResponse)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    from app.services.auth import hash_password
    
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        country=body.country,
        phone=body.phone,
        address=body.address
    )
    db.add(new_user)
    await db.flush()
    
    # Access Token
    access_token = create_access_token(new_user.id)
    
    # Refresh Token
    refresh_token_val = create_refresh_token(new_user.id)
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    db_token = RefreshToken(
        token=refresh_token_val,
        user_id=new_user.id,
        expires_at=expires
    )
    db.add(db_token)
    await db.commit()

    response.set_cookie(
        key="refresh_token",
        value=refresh_token_val,
        httponly=True,
        secure=False, # True in prod
        samesite="lax",
        expires=expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": new_user.id, "email": new_user.email, "name": new_user.name, "country": new_user.country, "phone": new_user.phone, "address": new_user.address, "is_admin": new_user.is_admin},
    }

@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Access Token
    access_token = create_access_token(user.id)
    
    # Refresh Token
    refresh_token_val = create_refresh_token(user.id)
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    db_token = RefreshToken(
        token=refresh_token_val,
        user_id=user.id,
        expires_at=expires
    )
    db.add(db_token)
    await db.commit()

    # Set cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token_val,
        httponly=True,
        secure=False, # Set to True in production
        samesite="lax",
        expires=expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "name": user.name, "country": user.country, "phone": user.phone, "address": user.address, "is_admin": user.is_admin},
    }

@router.post("/auth/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await db.execute(delete(RefreshToken).where(RefreshToken.token == refresh_token))
        await db.commit()
    
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}

@router.post("/auth/refresh")
async def refresh(request: Request, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token,
            RefreshToken.expires_at > datetime.now(timezone.utc)
        )
    )
    db_token = result.scalar_one_or_none()
    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    new_access_token = create_access_token(db_token.user_id)
    return {"access_token": new_access_token, "token_type": "bearer"}

@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "country": user.country, "phone": user.phone, "address": user.address, "is_admin": user.is_admin}
