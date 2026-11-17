import re
from typing import Tuple

# Жесткий черный список скама
STOP_WORDS = [
    r"1win", r"казино", r"crypto", r"крипт", r"бинарн", r"ставк",
    r"онлайн-доход", r"пассивный доход", r"без вложений", r"арбитраж",
    r"онлифанс", r"onlyfans", r"вебкам", r"webcam", r"модели 18\+",
    r"раскрутка", r"дроп", r"обнал", r"кардинг", r"залив", r"пирамид"
]

STOP_REGEX = re.compile("|".join(STOP_WORDS), re.IGNORECASE)

class FastPreFilter:
    @staticmethod
    def inspect(text: str, min_len: int = 25, max_len: int = 4000) -> Tuple[bool, str]:
        if not text or not isinstance(text, str):
            return False, "Empty message"
        cleaned = text.strip()
        if len(cleaned) < min_len:
            return False, f"Too short ({len(cleaned)} chars)"
        if len(cleaned) > max_len:
            return False, "Too long"
        if STOP_REGEX.search(cleaned):
            return False, "Matched blacklisted scam/spam keywords"
        return True, "OK"