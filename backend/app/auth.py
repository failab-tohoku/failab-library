import os
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", auto_error=False)

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set")

if SECRET_KEY == "CHANGE_ME":
    raise RuntimeError("SECRET_KEY must not use the insecure default value")

if os.getenv("USER_PASSWORD"):
    raise RuntimeError(
        "USER_PASSWORD is not supported. Set USER_PASSWORD_HASH instead."
    )

user_username = os.getenv("USER_USERNAME")
user_password_hash = os.getenv("USER_PASSWORD_HASH")
if not user_username or not user_password_hash:
    raise RuntimeError("Set USER_USERNAME and USER_PASSWORD_HASH in environment variables.")

USERS = {
    user_username: {
        "username": user_username,
        "password_hash": user_password_hash,
        "role": "user",
    }
}

if user_password_hash.startswith("$2a$"):
    raise RuntimeError(
        "USER_PASSWORD_HASH uses deprecated bcrypt prefix $2a$. Regenerate with $2b$."
    )


def authenticate_user(username: str, password: str):
    user = USERS.get(username)
    if not user:
        return None

    try:
        ok = bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        )
    except ValueError:
        return None

    if not ok:
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


def get_current_user(request: Request, token: str | None = Depends(oauth2_scheme)):
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return decode_current_user(token)
