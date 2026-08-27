from sqlalchemy import Column, String, Float, DateTime, Enum, ForeignKey, Integer, BigInteger, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from datetime import datetime
from backend.models.database import Base

class PaymentStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"

class PaymentProvider(str, enum.Enum):
    CLICK = "click"
    PAYME = "payme"
    PAYNET = "paynet"
    UZUM = "uzum"
    MANUAL = "manual"

class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("dubbing_jobs.id"), nullable=True) # Linked to a video dubbing job
    plan = Column(String(20), nullable=True)  # "standard" | "pro" — set instead of job_id for a subscription renewal payment
    is_library_access = Column(Boolean, default=False, nullable=False)  # 2026-08-19: Ommaviy videolar kutubxonasiga bir martalik kirish to'lovi -- job_id/plan ikkalasi ham bo'sh
    amount = Column(Float, nullable=False)
    provider = Column(Enum(PaymentProvider), default=PaymentProvider.CLICK)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    
    click_transaction_id = Column(String, index=True)
    click_prepare_id = Column(BigInteger)
    click_status = Column(Integer)
    click_create_time = Column(Integer)
    click_complete_time = Column(Integer)

    # Payme (Paycom) Merchant API (backend/api/payme_routes.py) -- Payme
    # o'zining "id"si orqali tranzaksiyani kuzatadi (CreateTransaction'da
    # beriladi, keyingi Perform/Cancel/Check so'rovlarida shu orqali
    # qidiriladi). payme_state Payme'ning holat mashinasi: 1=yaratilgan,
    # 2=tasdiqlangan, -1=tasdiqlanmasdan bekor qilingan, -2=tasdiqlangandan
    # keyin bekor qilingan.
    payme_transaction_id = Column(String, index=True, nullable=True)
    payme_state = Column(Integer, nullable=True)
    payme_create_time = Column(BigInteger, nullable=True)
    payme_perform_time = Column(BigInteger, nullable=True)
    payme_cancel_time = Column(BigInteger, nullable=True)
    payme_cancel_reason = Column(Integer, nullable=True)
    # 2026-08-19: pullik job 5 marta urinib ham muvaffaqiyatsiz tugasa
    # (backend/workers/tasks.py) shu bayroq true qilinadi -- Click orqali
    # avtomatik pul qaytarish integratsiyasi yo'q, shuning uchun admin panelda
    # ko'rsatilib, qo'lda qaytariladi.
    needs_refund = Column(Boolean, default=False, nullable=False)

    # Paynet (UZPAYNET) Universal Web-Service -- JSON-RPC 2.0, Basic Auth
    # (backend/api/paynet_routes.py). transactionId Paynet tomonidan
    # PerformTransaction so'rovida beriladi -- Payme'dan farqli, alohida
    # Create bosqichi yo'q, PerformTransaction bir zumda yaratadi va
    # tasdiqlaydi. providerTrnId (raqamli, Paynet'ga qaytariladigan) esa
    # payment.id'dan CRC32 orqali hisoblanadi (paynet_service.provider_trn_id),
    # alohida ustun sifatida saqlanmaydi.
    paynet_transaction_id = Column(BigInteger, index=True, nullable=True)
    paynet_perform_time = Column(DateTime, nullable=True)
    paynet_cancel_time = Column(DateTime, nullable=True)

    # Uzum Bank Merchant webhook (backend/api/uzum_routes.py) -- RASMIY
    # spetsifikatsiya (developer.uzumbank.uz/merchant, 2026-08-20).
    # uzum_account_id -- Uzum'ning "account" maydoni oddiy RAQAM ko'rinishida
    # keladi (Payment.id UUID emas), shuning uchun Click'dagi crc32 naqshi
    # bilan hisoblanadi va SAQLANADI (indekslangan qidiruv uchun).
    # uzum_transaction_id -- Uzum'ning "transId" (UUID-shaklidagi string).
    uzum_account_id = Column(BigInteger, index=True, nullable=True)
    uzum_transaction_id = Column(String, index=True, nullable=True)
    uzum_create_time = Column(DateTime, nullable=True)
    uzum_confirm_time = Column(DateTime, nullable=True)
    uzum_cancel_time = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    job = relationship("DubbingJob")
