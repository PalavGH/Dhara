import re
from datetime import datetime
from difflib import SequenceMatcher

from loguru import logger


def normalize_name(name):
    try:
        return re.sub(r'[\W\d_]+', '', name).lower()
    except Exception as e:
        logger.exception(f"Error normalizing name: {e}")
        return name.lower()


def prettify_date(date_str):
    try:
        logger.debug(date_str + " is the date string, please work.")
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        return date.strftime("%B %d, %Y")
    except ValueError as e:
        logger.exception(f"Error formatting date: {e}")
        return "Unknown Date"

