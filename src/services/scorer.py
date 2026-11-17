import re
from src.schemas import JobExtractedData, QualityScoreResult
from src.config import settings

# Поиск украинских номеров телефонов
PHONE_REGEX = re.compile(r"(?:\+?380|0)\s*(?:\(?\d{2}\)?|\d{2})\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}|\b0\d{9}\b")
# Поиск Telegram username (@username или t.me/username)
USERNAME_REGEX = re.compile(r"@[a-zA-Z0-9_]{4,}|t\.me/[a-zA-Z0-9_]{4,}")

class QualityScorer:
    @staticmethod
    def evaluate(job: JobExtractedData) -> QualityScoreResult:
        score = 0
        reasons = []

        if not job.is_job_offer:
            return QualityScoreResult(score=0, grade="D", passed=False, reasons=["Not a job offer"])
        if job.is_scam_or_ad:
            return QualityScoreResult(score=0, grade="D", passed=False, reasons=["Flagged as scam/ad"])

        # 1. ПРОВЕРКА КОНТАКТА: Должен быть Телефон ИЛИ Юзернейм в поле contact.
        # Проверяем ТОЛЬКО contact (а не весь текст), чтобы год/зарплата
        # в описании не давали false-positive телефона.
        contact_str = f"{job.contact or ''}".strip()

        has_phone = bool(PHONE_REGEX.search(contact_str))
        has_username = bool(USERNAME_REGEX.search(contact_str) or ("@" in contact_str and len(contact_str) >= 4))

        if not (has_phone or has_username):
            return QualityScoreResult(
                score=0,
                grade="D",
                passed=False,
                reasons=["No direct contact found (Phone number or @username required)"]
            )

        # Контакты присутствуют (+35)
        score += 35

        # 2. Наличие должности (+25)
        if job.title and len(job.title.strip()) >= 3:
            score += 25
        else:
            reasons.append("Missing title")

        # 3. Наличие зарплаты (+20)
        if job.salary or (job.salary_min and job.salary_min > 0):
            score += 20

        # 4. График / Обязанности (+20)
        if job.schedule or job.responsibilities:
            score += 20

        grade = "A" if score >= 80 else ("B" if score >= 60 else "C")
        passed = score >= settings.MIN_PUBLISH_SCORE

        return QualityScoreResult(score=score, grade=grade, passed=passed, reasons=reasons)