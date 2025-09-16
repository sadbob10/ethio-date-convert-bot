# date_utils.py
import datetime
from ethiopian_date import EthiopianDateConverter
from hijridate import Hijri, Gregorian

ETH_WEEKDAYS = ["እሑድ", "ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "ዓርብ", "ቅዳሜ"]
HIJRI_WEEKDAYS = ["al-Ahad", "al-Ithnayn", "ath-Thulatha", "al-Arbi'a", "al-Khamis", "al-Jumu'ah", "as-Sabt"]

GREG_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

ETH_MONTHS = [
    ("መስከረም", "Meskerem"), ("ጥቅምት", "Tikimt"), ("ህዳር", "Hidar"), ("ታህሳስ", "Tahsas"),
    ("ጥር", "Tir"), ("የካቲት", "Yekatit"), ("መጋቢት", "Megabit"), ("ሚያዝያ", "Miyazya"),
    ("ግንቦት", "Ginbot"), ("ሰኔ", "Sene"), ("ሐምሌ", "Hamle"), ("ነሐሴ", "Nehase"),
    ("ጳጉሜን", "Pagumen")
]

HIJRI_MONTHS = [
    "Muharram", "Safar", "Rabiʿ al-Awwal", "Rabiʿ al-Thani",
    "Jumada al-Awwal", "Jumada al-Thani", "Rajab", "Shaʿban",
    "Ramadan", "Shawwal", "Dhu al-Qaʿdah", "Dhu al-Hijjah"
]

def get_ethiopian_weekday(eth_year: int, eth_month: int, eth_day: int) -> str:
    g_date = EthiopianDateConverter.to_gregorian(eth_year, eth_month, eth_day)
    return ETH_WEEKDAYS[(g_date.weekday() + 1) % 7]

def get_hijri_weekday(hy: int, hm: int, hd: int) -> str:
    g_date = Hijri(hy, hm, hd).to_gregorian()
    weekday_index = (g_date.weekday() + 1) % 7
    return HIJRI_WEEKDAYS[weekday_index]

def format_gregorian_date(date: datetime.date) -> str:
    return f"{date.strftime('%A')}, {date.day} {GREG_MONTHS[date.month - 1]} {date.year}"

def format_ethiopian_date(eth_year: int, eth_month: int, eth_day: int) -> str:
    eth_am, eth_en = ETH_MONTHS[eth_month - 1]
    eth_weekday = get_ethiopian_weekday(eth_year, eth_month, eth_day)
    return f"{eth_weekday}, {eth_day} {eth_am} ({eth_en}) {eth_year}"

def format_hijri_date(hy: int, hm: int, hd: int) -> str:
    hijri_weekday = get_hijri_weekday(hy, hm, hd)
    return f"{hijri_weekday}, {hd} {HIJRI_MONTHS[hm - 1]} {hy} AH"

def validate_date(cal_type: str, y: int, m: int, d: int) -> tuple[bool, str | None]:
    try:
        if cal_type == "greg":
            datetime.date(y, m, d)
        elif cal_type == "eth":
            EthiopianDateConverter.to_gregorian(y, m, d)
        elif cal_type == "hijri":
            Hijri(y, m, d)
        return True, None
    except ValueError as e:
        return False, f"Invalid date: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
