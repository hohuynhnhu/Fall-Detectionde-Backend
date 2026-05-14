from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin.exceptions import FirebaseError
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import UserDB
from ..services.auth_service import (
    add_camera,
    get_user_cameras,
    remove_camera,
    upsert_user,
)
from ..services.dependencies import get_current_user
from ..services.firebase_service import (
    create_email_user,
    sign_in_with_email,
    update_user_password,
    verify_id_token,
)

router = APIRouter()


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


class UserResponse(BaseModel):
    id:           int
    firebase_uid: str
    email:        Optional[str]
    phone_number: Optional[str]
    display_name: Optional[str]
    is_active:    bool

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    id_token:     str
    refresh_token: str
    expires_in:   str
    user:         UserResponse


class CameraAssignRequest(BaseModel):
    camera_id: str
    label:     Optional[str] = None


class CameraResponse(BaseModel):
    id:        int
    camera_id: str
    label:     Optional[str]

    class Config:
        from_attributes = True


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
             summary="Đăng nhập bằng số điện thoại (OTP — client gửi id_token sau khi xác minh OTP)")
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


@router.get("/cameras", response_model=list[CameraResponse],
            summary="Danh sách cameras của user")
async def list_cameras(
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_cameras(db, current_user.id)


@router.post("/cameras", response_model=CameraResponse, status_code=201,
             summary="Thêm camera vào user")
async def assign_camera(
    body: CameraAssignRequest,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await add_camera(db, current_user.id, body.camera_id, body.label)


@router.delete("/cameras/{camera_id}", status_code=204,
               summary="Xóa camera khỏi user")
async def unassign_camera(
    camera_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    removed = await remove_camera(db, current_user.id, camera_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera không tồn tại trong danh sách của bạn")
