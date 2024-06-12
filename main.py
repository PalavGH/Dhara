import json
import sys
import asyncio
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop, QApplication as QAsyncApplication
import qt_material
from loguru import logger
from MainWindow import MainWindow  # Assuming MainWindow is in main_window.py
from utils import init_db
from state import state  # Import the State instance

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Main function to initialize and run the application
def main():
    # Configure logging
    logger.add(sys.stdout, level="INFO")

    app = QAsyncApplication(sys.argv)
    qt_material.apply_stylesheet(app, theme='dark_lightgreen.xml')
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialize the database
    init_db()

    # Load state from Redis
    state.load_state()

    main_window = MainWindow()
    main_window.show()

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
