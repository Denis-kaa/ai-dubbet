class PermanentError(Exception):
    """Qayta urinish ma'nosiz bo'lgan xatolik — har safar bir xil natija
    chiqadi (masalan, video shaxsiy/o'chirilgan, yoki nutq topilmadi).
    Celery task retry mexanizmi buni ushlab, darhol FAILED qiladi.

    `code` — DubbingJob.error_code'ga yoziladigan qisqa toifa (masalan
    "VIDEO_UNAVAILABLE"). Berilmasa umumiy "PERMANENT" ishlatiladi.
    """

    def __init__(self, message: str, code: str = "PERMANENT"):
        super().__init__(message)
        self.code = code
