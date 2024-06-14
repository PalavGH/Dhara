from loguru import logger

def configure_logging():
    logger.add("logs/app.log", rotation="10 MB", retention="10 days", level="DEBUG")
    logger.info("Logging configured")
