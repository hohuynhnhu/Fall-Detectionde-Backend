from __future__ import annotations

import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin.exceptions import FirebaseError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import OTPCodeDB, UserDB
from ..schemas import LoginResponse, UserResponse
from ..services.auth_service import upsert_user
from ..services.dependencies import get_current_user
from ..services.email_service import generate_otp, send_otp_email
from ..services.firebase_service import (
    create_email_user,
    revoke_refresh_tokens,
    sign_in_with_email,
    update_firebase_user,
    update_user_password,
    verify_id_token,
)

router = APIRouter()

_OTP_TTL = 600  # 10 phút


# ── Request / Response schemas ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:        EmailStr
    password:     str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenLoginRequest(BaseModel):
    id_token: str


class ChangePasswordRequest(BaseModel):
    new_password: str


class SendOTPRequest(BaseModel):
    email:   EmailStr
    purpose: Literal["email_verification", "password_reset"]


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code:  str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email:        EmailStr
    code:         str
    new_password: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    avatar_url:   Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _invalidate_old_otps(db: AsyncSession, email: str, purpose: str) -> None:
    await db.execute(
        update(OTPCodeDB)
        .where(
            OTPCodeDB.email   == email,
            OTPCodeDB.purpose == purpose,
            OTPCodeDB.used    == False,  # noqa: E712
        )
        .values(used=True)
    )


async def _find_valid_otp(db: AsyncSession, email: str, code: str, purpose: str) -> OTPCodeDB | None:
    result = await db.execute(
        select(OTPCodeDB).where(
            OTPCodeDB.email      == email,
            OTPCodeDB.code       == code,
            OTPCodeDB.purpose    == purpose,
            OTPCodeDB.used       == False,  # noqa: E712
            OTPCodeDB.expires_at >  time.time(),
        )
    )
    return result.scalar_one_or_none()


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201,
             summary="Đăng ký tài khoản email/password")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        firebase_user = await create_email_user(body.email, body.password, body.display_name)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    decoded = {
        "uid":          firebase_user["uid"],
        "email":        firebase_user["email"],
        "name":         firebase_user.get("display_name"),
        "phone_number": None,
    }
    user = await upsert_user(db, decoded)
    return user


@router.post("/login", response_model=LoginResponse,
             summary="Đăng nhập email/password")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        firebase_resp = await sign_in_with_email(body.email, body.password)
    except ValueError as e:
        msg = str(e)
        if "EMAIL_NOT_FOUND" in msg or "INVALID_PASSWORD" in msg or "INVALID_LOGIN_CREDENTIALS" in msg:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    decoded = await verify_id_token(firebase_resp["idToken"])
    user = await upsert_user(db, decoded)

    return LoginResponse(
        id_token=firebase_resp["idToken"],
        refresh_token=firebase_resp["refreshToken"],
        expires_in=firebase_resp["expiresIn"],
        user=UserResponse.model_validate(user),
    )


@router.post("/phone/login", response_model=LoginResponse,
             summary="Đăng nhập bằng số điện thoại (client gửi id_token sau khi xác minh OTP)")
async def phone_login(body: TokenLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        decoded = await verify_id_token(body.id_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ hoặc đã hết hạn")

    if not decoded.get("phone_number"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token này không phải của tài khoản phone")

    user = await upsert_user(db, decoded)

    return LoginResponse(
        id_token=body.id_token,
        refresh_token="",
        expires_in="3600",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", status_code=200,
             summary="Đăng xuất — thu hồi tất cả refresh tokens")
async def logout(current_user: UserDB = Depends(get_current_user)):
    try:
        await revoke_refresh_tokens(current_user.firebase_uid)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True, "message": "Đã đăng xuất thành công"}


# ── OTP endpoints ──────────────────────────────────────────────────────────────

@router.post("/send-otp", status_code=200,
             summary="Gửi OTP qua email (xác thực email hoặc đặt lại mật khẩu)")
async def send_otp(body: SendOTPRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserDB).where(UserDB.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email không tồn tại trong hệ thống")

    if body.purpose == "email_verification" and user.email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email đã được xác thực trước đó")

    await _invalidate_old_otps(db, body.email, body.purpose)

    code = generate_otp()
    db.add(OTPCodeDB(
        email=body.email,
        code=code,
        purpose=body.purpose,
        expires_at=time.time() + _OTP_TTL,
    ))
    await db.commit()

    try:
        await send_otp_email(body.email, code, body.purpose)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Không thể gửi email: {e}")

    return {"ok": True, "message": "OTP đã được gửi đến email của bạn"}


@router.post("/verify-email", status_code=200,
             summary="Xác thực email bằng OTP")
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    otp = await _find_valid_otp(db, body.email, body.code, "email_verification")
    if not otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP không hợp lệ hoặc đã hết hạn")

    otp.used = True

    result = await db.execute(select(UserDB).where(UserDB.email == body.email))
    user = result.scalar_one_or_none()
    if user:
        user.email_verified = True

    await db.commit()
    return {"ok": True, "message": "Email đã được xác thực thành công"}


@router.post("/forgot-password", status_code=200,
             summary="Gửi OTP đặt lại mật khẩu qua email")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserDB).where(UserDB.email == body.email))
    user = result.scalar_one_or_none()

    # Luôn trả về OK để tránh lộ thông tin email tồn tại
    if user:
        await _invalidate_old_otps(db, body.email, "password_reset")
        code = generate_otp()
        db.add(OTPCodeDB(
            email=body.email,
            code=code,
            purpose="password_reset",
            expires_at=time.time() + _OTP_TTL,
        ))
        await db.commit()
        try:
            await send_otp_email(body.email, code, "password_reset")
        except Exception:
            pass  # log internally, không lộ lỗi ra ngoài

    return {"ok": True, "message": "Nếu email tồn tại, OTP đã được gửi"}


@router.post("/reset-password", status_code=200,
             summary="Đặt lại mật khẩu bằng OTP")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu phải có ít nhất 6 ký tự")

    otp = await _find_valid_otp(db, body.email, body.code, "password_reset")
    if not otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP không hợp lệ hoặc đã hết hạn")

    result = await db.execute(select(UserDB).where(UserDB.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản không tồn tại")

    try:
        await update_user_password(user.firebase_uid, body.new_password)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    otp.used = True
    await db.commit()
    return {"ok": True, "message": "Mật khẩu đã được đặt lại thành công"}


# ── Profile endpoints ──────────────────────────────────────────────────────────

@router.patch("/profile", response_model=UserResponse,
              summary="Cập nhật hồ sơ cá nhân (display_name, avatar_url)")
async def update_profile(
    body: UpdateProfileRequest,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.display_name is None and body.avatar_url is None:
        return current_user

    firebase_kwargs: dict = {}
    if body.display_name is not None:
        current_user.display_name = body.display_name
        firebase_kwargs["display_name"] = body.display_name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
        firebase_kwargs["photo_url"] = body.avatar_url

    try:
        await update_firebase_user(current_user.firebase_uid, **firebase_kwargs)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=200,
             summary="Đổi mật khẩu (yêu cầu xác thực)")
async def change_password(
    body: ChangePasswordRequest,
    current_user: UserDB = Depends(get_current_user),
):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mật khẩu phải có ít nhất 6 ký tự")

    try:
        await update_user_password(current_user.firebase_uid, body.new_password)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"ok": True, "message": "Đổi mật khẩu thành công"}


@router.get("/me", response_model=UserResponse,
            summary="Lấy thông tin user hiện tại")
async def get_me(current_user: UserDB = Depends(get_current_user)):
    return current_user
