import sys
from PyQt6.QtWidgets import QApplication
from client.ui.dhara_main_window import DharaMainWindow
from config.dhara_settings import load_config
from utils.dhara_logger import configure_logging
from loguru import logger
from qt_material import apply_stylesheet


def main():
    try:
        configure_logging()
        config = load_config('config/client_config.json')
        app = QApplication(sys.argv)
        apply_stylesheet(app, theme='dark_lightgreen.xml')
        main_window = DharaMainWindow(config)
        main_window.show()
        sys.exit(app.exec())
    except Exception:
        logger.exception("An error occurred")
        sys.exit(1)

if __name__ == "__main__":
    main()
