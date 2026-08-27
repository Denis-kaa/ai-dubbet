import mimetypes
import os
import boto3
import logging
from botocore.exceptions import ClientError
from botocore.config import Config
from backend.config import get_settings

logger = logging.getLogger(__name__)

def _get_s3_client():
    settings = get_settings()
    bucket = settings.AWS_BUCKET_NAME
    if not bucket or not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        return None, None

    kwargs = {
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
    }
    if settings.AWS_REGION:
        kwargs["region_name"] = settings.AWS_REGION

    try:
        s3_client = boto3.client(
            "s3",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"}
            ),
            **kwargs
        )
        return s3_client, bucket
    except Exception as e:
        logger.error(f"Failed to create S3 client: {e}")
        return None, None

def upload_file_to_s3(file_path: str, object_name: str) -> bool:
    """Upload a file to an S3 bucket."""
    s3_client, bucket = _get_s3_client()
    if not s3_client:
        return False

    if not os.path.exists(file_path):
        logger.error(f"Local file does not exist: {file_path}")
        return False

    try:
        # boto3 upload_file() Content-Type'ni o'zi taxmin qilmaydi (aws-cli'dan
        # farqli) -- ko'rsatilmasa S3 "binary/octet-stream" bilan saqlaydi,
        # bu esa brauzerning <video>/<audio> teglari inline ijro etishdan bosh
        # tortishiga olib keladi (qora ekran, xatosiz) -- 2026-08-19,
        # kutubxona video pleyeri orqali aniqlangan haqiqiy xato.
        content_type, _ = mimetypes.guess_type(object_name)
        extra_args = {"ContentType": content_type} if content_type else None
        s3_client.upload_file(file_path, bucket, object_name, ExtraArgs=extra_args)
        logger.info(f"Successfully uploaded {file_path} to S3 as {object_name}")
        return True
    except Exception as e:
        logger.error(f"S3 upload failed for {file_path}: {e}")
        return False

def download_file_from_s3(object_name: str, local_path: str) -> bool:
    """S3'dagi faylni lokal diskka yuklab oladi (masalan TTS keshdan qayta
    foydalanish uchun — backend/services/tts_cache.py)."""
    s3_client, bucket = _get_s3_client()
    if not s3_client:
        return False

    try:
        s3_client.download_file(bucket, object_name, local_path)
        return True
    except ClientError as e:
        logger.warning(f"S3 dan yuklab olishda xatolik ({object_name}): {e}")
        return False
    except Exception as e:
        logger.error(f"S3 download kutilmagan xatolik ({object_name}): {e}")
        return False


def s3_object_exists(object_name: str) -> bool:
    """Obyekt S3'da haqiqatan mavjudligini tekshiradi. Presigned URL
    generatsiyasi buni tekshirmaydi -- u faqat lokal kriptografik imzolash,
    tarmoq so'rovi emas -- shuning uchun bucket lifecycle qoidasi (3 kundan
    keyin avtomatik o'chirish, backend/config.py: AWS_BUCKET_NAME) bo'yicha
    allaqachon o'chirilgan faylga ham "muvaffaqiyatli" ko'ringan URL
    qaytarib yuborardi, keyin brauzer uni yuklashga uringanda jim tarzda
    404 bilan yiqilardi (2026-08-21 aniqlangan bag)."""
    s3_client, bucket = _get_s3_client()
    if not s3_client:
        return False
    try:
        s3_client.head_object(Bucket=bucket, Key=object_name)
        return True
    except ClientError:
        return False
    except Exception as e:
        logger.error(f"S3 mavjudlikni tekshirishda kutilmagan xatolik ({object_name}): {e}")
        return False


def generate_presigned_download_url(
    object_name: str,
    expiration: int = 3600,
    download: bool = True,
) -> str | None:
    """Generate a presigned URL with an explicit browser disposition."""
    s3_client, bucket = _get_s3_client()
    if not s3_client:
        return None

    try:
        params = {"Bucket": bucket, "Key": object_name}
        # Ilgari yuklangan fayllarning ko'pi S3'da noto'g'ri "binary/octet-stream"
        # Content-Type bilan saqlangan (yuklash ExtraArgs bermagan edi) --
        # brauzer <video>/<audio> shu turni ko'rib inline ijrodan bosh tortadi
        # (qora ekran). ResponseContentType obyektning o'zini o'zgartirmasdan,
        # shu bitta so'rov uchun to'g'ri turni majburlaydi -- mavjud fayllarni
        # qayta yuklashsiz tuzatadi (2026-08-19).
        content_type, _ = mimetypes.guess_type(object_name)
        if content_type:
            params["ResponseContentType"] = content_type
        params["ResponseContentDisposition"] = "attachment" if download else "inline"
        response = s3_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiration,
        )
        return response
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        return None
