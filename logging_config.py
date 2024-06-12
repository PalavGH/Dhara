from loguru import logger

def configure_logging():
    logger.add("logs/app.log", rotation="1 MB", retention="10 days")

