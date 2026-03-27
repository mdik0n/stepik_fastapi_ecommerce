from http.client import HTTPException

from fastapi import APIRouter, status, Depends, HTTPException

from app.models import User as UserModel
from app.schemas import UserCreate, User as UserSchema, RefreshTokenRequest
from sqlalchemy.ext.asyncio import AsyncSession
from app.db_depends import get_async_db
from app.auth import hash_password, create_access_token, verify_password, create_refresh_token
from sqlalchemy import select
from app.config import SECRET_KEY, ALGORITHM
import jwt

from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_async_db)):
    """
    Регистрирует нового пользователя с ролью 'buyer' или 'seller' или 'admin'.
    """

    # Проверка уникальности email

    result = await db.scalars(select(UserModel).where(UserModel.email == user.email))

    if result.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this email already exists")

    # Создание объекта пользователя с хешированным паролем

    db_user = UserModel(email=user.email,
                        hashed_password=hash_password(user.password),
                        role=user.role
                        )
    # Добавление в сессию и сохранение в базе

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return db_user


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_async_db)):
    """
    Аутентифицирует пользователя и возвращает access_token и refresh_token.
    """

    result = await db.scalars(select(UserModel).where(UserModel.email == form_data.username, UserModel.is_active))
    user = result.first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"},
                            )

    access_token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.email, "role": user.role, "id": user.id})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh")
async def refresh_token(body: RefreshTokenRequest, db: AsyncSession = Depends(get_async_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    old_refresh_token = body.refresh_token

    try:
        payload = jwt.decode(old_refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        toke_type: str = payload.get("token_type")

        # Проверяем, что токен действительно refresh

        if email is None or toke_type != "refresh":
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        # refresh-токен истёк
        raise credentials_exception
    except jwt.PyJWTError:
        # подпись неверна или токен повреждён
        raise credentials_exception

    user: UserModel | None = (
        await db.execute(select(UserModel).where(UserModel.email == email, UserModel.is_active))).scalar_one_or_none()

    if user is None:
        raise credentials_exception

    new_refresh_token = create_refresh_token(
        data={"sub": user.email, "role": user.role, "id": user.id}
    )

    new_access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "id": user.id}
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }
