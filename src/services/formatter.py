from typing import Optional
from src.schemas import JobExtractedData

CATEGORY_EMOJI = {
    "клінінг": "🧹", "прибирання": "🧹", "уборка": "🧹",
    "ресторан": "🍽️", "общепит": "🍽️", "кухар": "👨‍🍳", "повар": "👨‍🍳",
    "офіціант": "🤵", "официант": "🤵", "бариста": "☕", "продажі": "🛍️",
    "продавець": "🛍️", "касир": "🛒", "склад": "📦", "вантажник": "💪",
    "різноробочий": "🔨", "водій": "🚗", "водитель": "🚗", "кур'єр": "🛵",
    "будівництво": "🔨", "ремонт": "🔧", "охорона": "🛡️", "адміністратор": "💼",
    "офіс": "💼", "дистанційно": "💻", "підробіток": "⏱️",
}

class JobPostFormatter:
    @staticmethod
    def format_telegram_message(job: JobExtractedData, source_url: Optional[str] = None) -> str:
        emoji = "💼"
        if job.category:
            cat_lower = job.category.lower()
            for key, val in CATEGORY_EMOJI.items():
                if key in cat_lower:
                    emoji = val
                    break

        title = (job.title or "Працівник").upper()
        lines = [f"{emoji} <b>{title}</b>\n"]

        # Локація
        loc_parts = [p for p in [job.city, job.district] if p]
        if loc_parts:
            lines.append(f"📍 <b>Локація:</b> {', '.join(loc_parts)}")

        # Зарплата
        if job.salary:
            lines.append(f"💰 <b>Зарплата:</b> {job.salary}")

        # Графік
        if job.schedule:
            lines.append(f"🕐 <b>Графік:</b> {job.schedule}")

        # Зайнятість
        if job.employment_type:
            lines.append(f"📌 <b>Зайнятість:</b> {job.employment_type}")

        # Обов'язки
        if job.responsibilities:
            lines.append("\n📋 <b>Обов'язки:</b>")
            for r in job.responsibilities[:5]:
                lines.append(f"• {r}")

        # Вимоги
        if job.requirements:
            lines.append("\n📌 <b>Вимоги:</b>")
            for req in job.requirements[:5]:
                lines.append(f"• {req}")

        # Контакт (телефон або telegram-юзернейм)
        if job.contact:
            lines.append(f"\n📞 <b>Контакти:</b> {job.contact}")

        # Фірмовий підвал каналу (без посилань на сторонні джерела)
        lines.append("\n———————————————")
        lines.append("👉 <b>Підписуйтесь на <a href=\"https://t.me/tyrobota_kyiv_ua\">@tyrobota_kyiv_ua</a></b>")

        return "\n".join(lines)