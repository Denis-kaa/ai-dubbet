import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.models.database import User, get_db
from backend.services.auth import hash_password, verify_password, create_access_token, get_current_user
from fastapi.responses import JSONResponse
from backend.services.email_service import (
    generate_verification_code,
    send_verification_email,
    send_password_reset_email,
    CODE_TTL_MINUTES,
)
from backend.services.rate_limiter import rate_limit
from backend.services.google_auth import verify_google_token, GoogleTokenError
from backend.services.sms_service import send_otp_sms

router = APIRouter(prefix="/auth", tags=["auth"])

_PHONE_RE = re.compile(r"^\+998\d{9}$")


class GoogleAuthRequest(BaseModel):
    credential: str


class PhoneRequestCodeRequest(BaseModel):
    phone: str


class PhoneVerifyCodeRequest(BaseModel):
    phone: str
    code: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


class ResendCodeRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class PendingVerificationResponse(BaseModel):
    pending_verification: bool = True
    email: str
    message: str


class PhonePendingVerificationResponse(BaseModel):
    pending_verification: bool = True
    phone: str
    message: str


def _issue_code(user: User, db: Session) -> str:
    """Tasdiqlash kodini beradi.

    Agar hozirgina (so'nggi daqiqa ichida) berilgan, hali amal qiladigan kod
    bo'lsa, o'shani qaytaradi — yangisini yaratmaydi. Aks holda, foydalanuvchi
    tugmani ikki marta bossa yoki so'rov tasodifan qaytarilsa, birinchi
    emailga yuborilgan kod bekor bo'lib, "to'g'ri kod ishlamadi" holatiga
    olib keladi.
    """
    now = datetime.utcnow()
    if (
        user.verification_code
        and user.verification_code_expires_at
        and user.verification_code_expires_at - now > timedelta(minutes=CODE_TTL_MINUTES - 1)
    ):
        return user.verification_code

    code = generate_verification_code()
    user.verification_code = code
    user.verification_code_expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    db.commit()
    return code


def _issue_phone_code(user: User, db: Session) -> str:
    """_issue_code bilan bir xil mantiq, telefon maydonlari uchun."""
    now = datetime.utcnow()
    if (
        user.phone_verification_code
        and user.phone_verification_code_expires_at
        and user.phone_verification_code_expires_at - now > timedelta(minutes=CODE_TTL_MINUTES - 1)
    ):
        return user.phone_verification_code

    code = generate_verification_code()
    user.phone_verification_code = code
    user.phone_verification_code_expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    db.commit()
    return code


@router.post("/register", status_code=201, dependencies=[Depends(rate_limit("register", 5, 600))])
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> PendingVerificationResponse:
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak.")
    if db.query(User).filter(User.email == req.email.lower()).first():
        raise HTTPException(status_code=400, detail="Bu email allaqachon ro'yxatdan o'tgan.")

    user = User(
        email=req.email.lower().strip(),
        name=req.name.strip(),
        password_hash=hash_password(req.password),
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    code = _issue_code(user, db)
    if not send_verification_email(user.email, code, user.name):
        raise HTTPException(status_code=500, detail="Tasdiqlash kodini yuborishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")

    return PendingVerificationResponse(email=user.email, message="Tasdiqlash kodi emailingizga yuborildi.")


@router.post("/login", dependencies=[Depends(rate_limit("login", 10, 600))])
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bu email ro'yxatdan o'tmagan.")
    try:
        if not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Parol noto'g'ri.")
    except ValueError:
        # bcrypt hash buzilgan — foydalanuvchiga tushunarli xabar
        raise HTTPException(status_code=401, detail="Parol noto'g'ri.")

    # Agar foydalanuvchi allaqachon tasdiqlangan bo'lsa — JWT to'g'ridan-to'g'ri,
    # qayta email-kod yuborilmaydi. Yangi akkauntlar uchun eski oqim saqlanadi.
    if user.is_verified:
        token = create_access_token(str(user.id), user.email)
        return AuthResponse(
            access_token=token,
            user={"id": str(user.id), "name": user.name, "email": user.email, "role": user.role},
        )

    code = _issue_code(user, db)
    if not send_verification_email(user.email, code, user.name):
        raise HTTPException(status_code=500, detail="Tasdiqlash kodini yuborishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")

    return PendingVerificationResponse(email=user.email, message="Tasdiqlash kodi emailingizga yuborildi.")


@router.post("/verify-code", dependencies=[Depends(rate_limit("verify_code", 10, 600))])
def verify_code(req: VerifyCodeRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not user.verification_code:
        raise HTTPException(status_code=400, detail="Kod topilmadi. Qaytadan urinib ko'ring.")
    if not user.verification_code_expires_at or user.verification_code_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kod muddati tugagan. Yangi kod so'rang.")
    if user.verification_code != req.code.strip():
        raise HTTPException(status_code=400, detail="Kod noto'g'ri.")

    user.is_verified = True
    user.verification_code = None
    user.verification_code_expires_at = None
    db.commit()

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        access_token=token,
        user={"id": str(user.id), "name": user.name, "email": user.email, "role": user.role},
    )


@router.post("/google", dependencies=[Depends(rate_limit("google_auth", 20, 600))])
def google_auth(req: GoogleAuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Google Identity Services token orqali kirish/ro'yxatdan o'tish —
    bir bosqichli (email kodi shart emas, Google email'ni allaqachon
    tasdiqlagan). Email bir xil bo'lgan mavjud parol-akkount bo'lsa, o'shanga
    bog'lanadi (ikkita alohida akkount hosil bo'lmaydi)."""
    try:
        info = verify_google_token(req.credential)
    except GoogleTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    user = db.query(User).filter(User.google_id == info["sub"]).first()

    if not user:
        user = db.query(User).filter(User.email == info["email"]).first()
        if user:
            user.google_id = info["sub"]
            if info["email_verified"]:
                user.is_verified = True
            db.commit()

    if not user:
        user = User(
            email=info["email"],
            name=info["name"],
            google_id=info["sub"],
            password_hash=None,
            is_verified=info["email_verified"],
            auth_provider="google",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        access_token=token,
        user={"id": str(user.id), "name": user.name, "email": user.email, "role": user.role},
    )


@router.post("/phone/request-code", dependencies=[Depends(rate_limit("phone_request_code", 3, 600))])
def phone_request_code(req: PhoneRequestCodeRequest, db: Session = Depends(get_db)) -> PhonePendingVerificationResponse:
    """Telefon orqali kirish/ro'yxatdan o'tish — kod SMS orqali yuboriladi,
    parol yoki ism shart emas (kod o'zi tasdiqlash vazifasini bajaradi)."""
    phone = req.phone.strip()
    if not _PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak.")

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(phone=phone, name=phone, is_verified=False, auth_provider="phone")
        db.add(user)
        db.commit()
        db.refresh(user)

    code = _issue_phone_code(user, db)
    if not send_otp_sms(phone, code):
        raise HTTPException(status_code=500, detail="SMS yuborishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")

    return PhonePendingVerificationResponse(phone=phone, message="Tasdiqlash kodi SMS orqali yuborildi.")


@router.post("/phone/verify-code", dependencies=[Depends(rate_limit("phone_verify_code", 10, 600))])
def phone_verify_code(req: PhoneVerifyCodeRequest, db: Session = Depends(get_db)) -> AuthResponse:
    phone = req.phone.strip()
    user = db.query(User).filter(User.phone == phone).first()
    if not user or not user.phone_verification_code:
        raise HTTPException(status_code=400, detail="Kod topilmadi. Qaytadan urinib ko'ring.")
    if not user.phone_verification_code_expires_at or user.phone_verification_code_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kod muddati tugagan. Yangi kod so'rang.")
    if user.phone_verification_code != req.code.strip():
        raise HTTPException(status_code=400, detail="Kod noto'g'ri.")

    user.is_verified = True
    user.phone_verification_code = None
    user.phone_verification_code_expires_at = None
    db.commit()

    token = create_access_token(str(user.id), user.email or "")
    return AuthResponse(
        access_token=token,
        user={"id": str(user.id), "name": user.name, "email": user.email, "role": user.role},
    )


@router.post("/resend-code", dependencies=[Depends(rate_limit("resend_code", 5, 600))])
def resend_code(req: ResendCodeRequest, db: Session = Depends(get_db)) -> PendingVerificationResponse:
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi.")

    code = _issue_code(user, db)
    if not send_verification_email(user.email, code, user.name):
        raise HTTPException(status_code=500, detail="Tasdiqlash kodini yuborishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")

    return PendingVerificationResponse(email=user.email, message="Kod qayta yuborildi.")


@router.post("/forgot-password", dependencies=[Depends(rate_limit("forgot_password", 5, 600))])
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)) -> PendingVerificationResponse:
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bu email ro'yxatdan o'tmagan.")

    code = _issue_code(user, db)
    if not send_password_reset_email(user.email, code, user.name):
        raise HTTPException(status_code=500, detail="Kodni yuborishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")

    return PendingVerificationResponse(email=user.email, message="Parolni tiklash kodi emailingizga yuborildi.")


@router.post("/reset-password", dependencies=[Depends(rate_limit("reset_password", 10, 600))])
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)) -> AuthResponse:
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak.")

    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not user.verification_code:
        raise HTTPException(status_code=400, detail="Kod topilmadi. Qaytadan urinib ko'ring.")
    if not user.verification_code_expires_at or user.verification_code_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kod muddati tugagan. Yangi kod so'rang.")
    if user.verification_code != req.code.strip():
        raise HTTPException(status_code=400, detail="Kod noto'g'ri.")

    user.password_hash = hash_password(req.new_password)
    user.is_verified = True
    user.verification_code = None
    user.verification_code_expires_at = None
    db.commit()

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        access_token=token,
        user={"id": str(user.id), "name": user.name, "email": user.email, "role": user.role},
    )


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat(),
    }
