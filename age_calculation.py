# age_utils.py
import datetime
from ethiopian_date import EthiopianDateConverter
from hijridate import Hijri
from typing import Literal, Tuple, Optional

CalendarType = Literal["greg", "eth", "hijri"]

def calculate_age(birth_date: datetime.date, today: Optional[datetime.date] = None) -> int:
    """Calculate age in years from a birth date."""
    if not today:
        today = datetime.date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years

def validate_birth_date(calendar: CalendarType, year: int, month: int, day: int) -> Tuple[bool, Optional[str]]:
    """Validate a birth date according to the calendar."""
    try:
        if calendar == "greg":
            birth_date = datetime.date(year, month, day)
        elif calendar == "eth":
            g_date = EthiopianDateConverter.to_gregorian(year, month, day)
            birth_date = datetime.date(g_date.year, g_date.month, g_date.day)
        elif calendar == "hijri":
            g_date = Hijri(year, month, day).to_gregorian()
            birth_date = datetime.date(g_date.year, g_date.month, g_date.day)
        else:
            return False, "Unsupported calendar type"
        
        if birth_date > datetime.date.today():
            return False, "Birth date cannot be in the future"
        
        return True, None
    except ValueError as e:
        return False, f"Invalid date: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def parse_birth_date(calendar: CalendarType, year: int, month: int, day: int) -> datetime.date:
    """Convert any supported calendar birthdate to a Gregorian datetime.date."""
    valid, error = validate_birth_date(calendar, year, month, day)
    if not valid:
        raise ValueError(error)
    
    if calendar == "greg":
        return datetime.date(year, month, day)
    elif calendar == "eth":
        g_date = EthiopianDateConverter.to_gregorian(year, month, day)
        return datetime.date(g_date.year, g_date.month, g_date.day)
    elif calendar == "hijri":
        g_date = Hijri(year, month, day).to_gregorian()
        return datetime.date(g_date.year, g_date.month, g_date.day)
