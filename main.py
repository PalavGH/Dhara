import sys
import asyncio
from qasync import QEventLoop, QApplication as QAsyncApplication
import qt_material

from MainWindow import MainWindow
from logging_config import configure_logging
from plugin_manager import PluginManager
from state_manager import State
from config import Config


# Main function to initialize and run the application
def main():
    # Configure logging
    configure_logging()

    # Initialize the configuration
    config = Config()

    # Setup the application
    app = QAsyncApplication(sys.argv)
    qt_material.apply_stylesheet(app, theme='dark_lightgreen.xml')
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialize the database
    plugin_manager = PluginManager()
    plugin_manager.init_db()

    # Load state
    state = State()
    state.load_state()

    # Initialize and show the main window
    main_window = MainWindow()
    main_window.show()

    # Run the event loop
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
