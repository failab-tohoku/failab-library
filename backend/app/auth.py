import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USERS = {}

admin_username = os.getenv("ADMIN_USERNAME")
admin_password = os.getenv("ADMIN_PASSWORD")
admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH")
if admin_username and (admin_password or admin_password_hash):
    USERS[admin_username] = {
        "username": admin_username,
        "password": admin_password,
        "password_hash": admin_password_hash,
        "role": "admin",
    }

user_username = os.getenv("USER_USERNAME")
user_password = os.getenv("USER_PASSWORD")
user_password_hash = os.getenv("USER_PASSWORD_HASH")
if user_username and (user_password or user_password_hash):
    USERS[user_username] = {
        "username": user_username,
        "password": user_password,
        "password_hash": user_password_hash,
        "role": "user",
    }

if not USERS:
    USERS = {
        "admin": {
            "username": "admin",
            "password": "password",
            "password_hash": None,
            "role": "admin",
        },
        "user": {
            "username": "user",
            "password": "password",
            "password_hash": None,
            "role": "user",
        },
    }


def authenticate_user(username: str, password: str):
    user = USERS.get(username)
    if not user:
        return None

    password_hash = user.get("password_hash")
    if password_hash:
        if not pwd_context.verify(password, password_hash):
            return None
        return user

    if user.get("password") != password:
        return None

    return user


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_current_user(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        user = USERS.get(username)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return user
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def get_current_user(token: str = Depends(oauth2_scheme)):
    return decode_current_user(token)


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user
