import re
from datetime import datetime
from loguru import logger

def normalize_name(name):
    return re.sub(r'\W+', '', name).lower()

def prettify_date(date_str):
    try:
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        return date.strftime("%B %d, %Y")
    except ValueError as e:
        logger.error(f"Error formatting date: {e}")
        return "Unknown Date"
