from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton
from PyQt6.QtCore import pyqtSlot
from loguru import logger

class DharaSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Plugins")
        self.setMinimumSize(400, 200)

        self.layout = QVBoxLayout(self)

        self.label = QLabel("Enter plugin name:")
        self.layout.addWidget(self.label)

        self.search_input = QLineEdit()
        self.layout.addWidget(self.search_input)

        self.search_button = QPushButton("Search")
        self.layout.addWidget(self.search_button)

        self.search_button.clicked.connect(self.search)

    @pyqtSlot()
    def search(self):
        plugin_name = self.search_input.text()
        logger.info(f"Searching for plugin: {plugin_name}")
        # Implement the search functionality here
