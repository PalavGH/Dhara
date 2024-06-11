import asyncio
import os
import sqlite3
import sys
from difflib import SequenceMatcher
from contextlib import asynccontextmanager
from loguru import logger
import httpx
from httpx import HTTPStatusError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QLabel, QWidget, QListWidget, \
    QListWidgetItem, QHBoxLayout, QScrollArea, QLineEdit, QMessageBox
from PySide6.QtGui import QPixmap
import qt_material
from datetime import datetime
from qasync import QEventLoop, asyncSlot, QApplication as QAsyncApplication

# Configuration
API_KEY_MODRINTH = os.environ.get('MODAPI')
API_KEY_HANGAR = os.environ.get('HANGERAPI')
SEARCH_URL_MODRINTH = "https://api.modrinth.com/v2/search"
PROJECT_URL_MODRINTH = "https://api.modrinth.com/v2/project"
VERSION_URL_MODRINTH = "https://api.modrinth.com/v2/version"
AUTH_URL_HANGAR = "https://hangar.papermc.io/api/v1/authenticate"
SEARCH_URL_HANGAR = "https://hangar.papermc.io/api/v1/projects"
CACHE_DIR = "cache"
PLUGIN_FOLDER = "C:\\Custom\\Sandal Wearers\\plugins"
USER_AGENT = "PluginManagerApp/1.0"
DB_PATH = os.path.join(CACHE_DIR, "plugins.db")

# Initialize Loguru logger
logger.add("plugin_manager.log", rotation="10 MB")

class State:
    def __init__(self):
        self.found_plugins = []
        self.not_found_plugins = []
        self.loading = False
        self.error_message = ""
        self.update_status = []
        self.api_keys = {
            "modrinth": API_KEY_MODRINTH,
            "hangar": API_KEY_HANGAR
        }
        self.plugin_folder = PLUGIN_FOLDER
        self.selected_plugin = None

    def set_loading(self, is_loading):
        self.loading = is_loading

    def set_error(self, message):
        self.error_message = message

    def clear_error(self):
        self.error_message = ""

    def add_found_plugin(self, plugin):
        self.found_plugins.append(plugin)

    def add_not_found_plugin(self, plugin):
        self.not_found_plugins.append(plugin)

    def clear_plugins(self):
        self.found_plugins = []
        self.not_found_plugins = []

    def set_update_status(self, updates):
        self.update_status = updates

    def clear_update_status(self):
        self.update_status = []

    def set_api_key(self, platform, key):
        self.api_keys[platform] = key.strip()

    def get_api_key(self, platform):
        return self.api_keys.get(platform)

    def set_plugin_folder(self, folder_path):
        self.plugin_folder = folder_path

    def get_plugin_folder(self):
        return self.plugin_folder

    def set_selected_plugin(self, plugin):
        self.selected_plugin = plugin

    def get_selected_plugin(self):
        return self.selected_plugin


state = State()


def normalize_name(name):
    return ''.join(e for e in name if e.isalnum()).lower()


@asynccontextmanager
async def http_session():
    async with httpx.AsyncClient() as session:
        try:
            yield session
        finally:
            await session.aclose()


def init_db():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS plugins (
                      id INTEGER PRIMARY KEY,
                      name TEXT,
                      title TEXT,
                      description TEXT,
                      author TEXT,
                      date_created TEXT,
                      date_modified TEXT,
                      icon_url TEXT,
                      category TEXT,
                      downloads INTEGER,
                      follows INTEGER,
                      url TEXT,
                      source TEXT
                      )''')
    conn.commit()
    conn.close()


async def insert_or_update_plugin(plugin_data):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT OR REPLACE INTO plugins (name, title, description, author, date_created, date_modified, icon_url, category, downloads, follows, url, source)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (plugin_data['name'], plugin_data['title'], plugin_data['description'], plugin_data['author'],
                        plugin_data['date_created'], plugin_data['date_modified'], plugin_data['icon_url'],
                        plugin_data['category'], plugin_data['downloads'], plugin_data['follows'], plugin_data['url'],
                        plugin_data['source']))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error inserting or updating plugin data: {e}")


async def get_plugin_from_db(plugin_name):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plugins WHERE name=?", (plugin_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "name": row[1],
                "title": row[2],
                "description": row[3],
                "author": row[4],
                "date_created": row[5],
                "date_modified": row[6],
                "icon_url": row[7],
                "category": row[8],
                "downloads": row[9],
                "follows": row[10],
                "url": row[11],
                "source": row[12]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching plugin from database: {e}")
        return None


async def fetch(url, session, headers=None, params=None):
    try:
        logger.debug(f"Fetching URL: {url} with headers: {headers} and params: {params}")
        response = await session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return None


async def authenticate_hangar():
    try:
        async with http_session() as session:
            headers = {"User-Agent": USER_AGENT}
            api_key = state.get_api_key("hangar")
            response = await session.post(f"{AUTH_URL_HANGAR}?apiKey={api_key}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("token")
    except HTTPStatusError as e:
        logger.error(f"Error authenticating with Hangar API: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Hangar authentication: {e}")
        return None


async def search_plugin_modrinth(plugin_name):
    try:
        async with http_session() as session:
            headers = {
                "Authorization": f"Bearer {API_KEY_MODRINTH}",
                "User-Agent": USER_AGENT
            }
            params = {
                "query": plugin_name,
                "limit": 10,
                "facets": "[[\"categories:utility\"]]",
                "sort": "popularity"
            }
            return await fetch(SEARCH_URL_MODRINTH, session, headers=headers, params=params)
    except Exception as e:
        logger.error(f"Error searching Modrinth plugin: {e}")
        return None


async def search_plugin_hangar(plugin_name, token):
    try:
        normalized_plugin_name = ''.join(e for e in plugin_name if e.isalpha())

        logger.info(f"Searching for plugin '{normalized_plugin_name}' in Hangar")

        async with http_session() as session:
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT
            }
            params = {
                "q": normalized_plugin_name,
                "limit": 10
            }
            return await fetch(SEARCH_URL_HANGAR, session, headers=headers, params=params)
    except Exception as e:
        logger.error(f"Error searching Hangar plugin: {e}")
        return None


def convert_modrinth_to_unified(modrinth_data):
    return {
        "name": normalize_name(modrinth_data.get("title", "")),
        "title": modrinth_data.get("title", ""),
        "description": modrinth_data.get("description", ""),
        "author": modrinth_data.get("author", "Unknown Author"),
        "date_created": modrinth_data.get("date_created", ""),
        "date_modified": modrinth_data.get("date_modified", ""),
        "icon_url": modrinth_data.get("icon_url", ""),
        "category": modrinth_data.get("categories", [""])[0],
        "downloads": modrinth_data.get("downloads", 0),
        "follows": modrinth_data.get("follows", 0),
        "url": f"https://modrinth.com/mod/{modrinth_data.get('slug', '')}",
        "source": "modrinth"
    }


def convert_hangar_to_unified(hangar_data):
    return {
        "name": normalize_name(hangar_data.get("name", "")),
        "title": hangar_data.get("name", ""),
        "description": hangar_data.get("description", ""),
        "author": hangar_data.get("namespace", {}).get("owner", "Unknown Author"),
        "date_created": hangar_data.get("createdAt", ""),
        "date_modified": hangar_data.get("lastUpdated", ""),
        "icon_url": hangar_data.get("avatarUrl", ""),
        "category": hangar_data.get("category", ""),
        "downloads": hangar_data.get("stats", {}).get("downloads", 0),
        "follows": hangar_data.get("stats", {}).get("stars", 0),
        "url": f"https://hangar.papermc.io/{hangar_data.get('namespace', {}).get('owner', '')}/{hangar_data.get('namespace', {}).get('slug', '')}",
        "source": "hangar"
    }


async def search_plugin(plugin_name):
    # Check cache (SQLite) first for both sources
    cached_data = await get_plugin_from_db(normalize_name(plugin_name))

    if cached_data:
        logger.info(f"Found cached data for {plugin_name}")
        return [cached_data], "cache"

    # If not in cache, search in Hangar first
    token = await authenticate_hangar()
    if token:
        hangar_results = await search_plugin_hangar(plugin_name, token)
        if hangar_results and hangar_results.get('pagination', {}).get('count', 0) > 0:
            unified_data = [convert_hangar_to_unified(plugin) for plugin in hangar_results['result']]
            for data in unified_data:
                await insert_or_update_plugin(data)
            return unified_data, "hangar"

    # If not found in Hangar, search in Modrinth
    modrinth_results = await search_plugin_modrinth(plugin_name)
    if modrinth_results and modrinth_results.get('total_hits', 0) > 0:
        unified_data = [convert_modrinth_to_unified(plugin) for plugin in modrinth_results['hits']]
        for data in unified_data:
            await insert_or_update_plugin(data)
        return unified_data, "modrinth"

    return [], None


async def fetch_version_details(version_id, session):
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    return await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)


async def download_image(url, filepath):
    try:
        async with http_session() as session:
            async with session.stream("GET", url) as response:
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
    except Exception as e:
        logger.error(f"Error downloading image: {e}")


def get_best_match(plugin_name, results):
    best_match = None
    highest_score = 0
    normalized_plugin_name = normalize_name(plugin_name)

    for plugin in results:
        normalized_result_name = normalize_name(plugin['title'] if plugin.get('title') else plugin['name'])
        score = SequenceMatcher(None, normalized_plugin_name, normalized_result_name).ratio()
        if score > highest_score:
            highest_score = score
            best_match = plugin

    return best_match if highest_score > 0.8 else None


def scan_folder(folder_path):
    plugins = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".jar"):
            plugin_name = os.path.splitext(filename)[0]
            plugins.append((plugin_name, "Unknown Version"))
    return plugins


async def check_plugins(folder_path):
    plugins = scan_folder(folder_path)
    state.clear_plugins()

    try:
        async with http_session() as session:
            tasks = [search_plugin(plugin_name) for plugin_name, _ in plugins]
            results_with_sources = await asyncio.gather(*tasks)

            for (plugin_name, plugin_version), (results, source) in zip(plugins, results_with_sources):
                best_match = get_best_match(plugin_name, results)
                if best_match:
                    plugin_data = await get_plugin_from_db(normalize_name(plugin_name))
                    if not plugin_data:
                        plugin_data = best_match
                        await insert_or_update_plugin(plugin_data)

                    image_filepath = None
                    if plugin_data['icon_url']:
                        file_ext = os.path.splitext(plugin_data['icon_url'])[-1].split('?')[0]
                        image_filepath = os.path.join(CACHE_DIR, f"{normalize_name(plugin_name)}{file_ext}")
                        if not os.path.exists(image_filepath):
                            await download_image(plugin_data['icon_url'], image_filepath)

                    state.add_found_plugin((plugin_name, plugin_data['date_modified'], plugin_data['title'], plugin_data['url'], plugin_data, image_filepath))
                else:
                    state.add_not_found_plugin((plugin_name, plugin_version))
    except Exception as e:
        logger.error(f"Error checking plugins: {e}")

    return state.found_plugins, state.not_found_plugins


async def check_for_updates(found_plugins):
    updates = []
    try:
        for plugin in found_plugins:
            plugin_name, current_version, mod_name, project_id, plugin_data, _ = plugin
            latest_version = plugin_data.get('latest_version', "Unknown Date")
            if latest_version != current_version:
                updates.append((plugin_name, current_version, latest_version, latest_version))

        return updates
    except Exception as e:
        logger.error(f"Error checking updates: {e}")
        return updates


async def load_plugins():
    state.set_loading(True)
    try:
        found_plugins, not_found_plugins = await check_plugins(state.get_plugin_folder())
        state.set_loading(False)
        return found_plugins, not_found_plugins
    except Exception as e:
        logger.error(f"Error loading plugins: {e}")
        state.set_loading(False)
        return [], []


async def download_plugin(url, destination):
    try:
        async with http_session() as session:
            async with session.stream("GET", url) as download_response:
                download_response.raise_for_status()
                with open(destination, 'wb') as f:
                    async for chunk in download_response.aiter_bytes():
                        f.write(chunk)
    except Exception as e:
        logger.error(f"Error downloading plugin: {e}")


def update_plugin(plugin):
    logger.info(f"Updating plugin: {plugin.get('title', plugin.get('name'))}")
    try:
        asyncio.create_task(download_plugin(plugin['url'], f"{state.get_plugin_folder()}/{plugin['title']}.jar"))
    except Exception as e:
        logger.error(f"Error updating plugin: {e}")


def create_plugin_list_item(plugin):
    widget = QWidget()
    layout = QHBoxLayout()

    label_name = QLabel(f"<a href='{plugin[3]}' style='color: white'>{plugin[2]}</a>")
    label_name.setOpenExternalLinks(True)
    label_last_updated = QLabel(f"Date Modified: {prettify_date(plugin[1])}")

    image_label = QLabel()
    image_filepath = plugin[5]
    if image_filepath and os.path.exists(image_filepath):
        pixmap = QPixmap(image_filepath)
        image_label.setPixmap(pixmap)
        image_label.setFixedSize(64, 64)
        image_label.setScaledContents(True)
    else:
        image_label.setText("No Image")

    layout.addWidget(image_label)
    layout.addWidget(label_name)
    layout.addWidget(label_last_updated)
    widget.setLayout(layout)

    return widget


def create_not_found_plugin_list_item(plugin_name, plugin_version):
    widget = QWidget()
    layout = QHBoxLayout()

    label_name = QLabel(f"Name: {plugin_name}")
    label_version = QLabel(f"Version: {plugin_version}")
    label_not_found = QLabel("Not Found")

    layout.addWidget(label_name)
    layout.addWidget(label_version)
    layout.addWidget(label_not_found)
    widget.setLayout(layout)

    return widget


def prettify_date(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except ValueError:
        return date_str


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paper Server Manager")
        self.setMinimumSize(800, 600)

        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)

        self.plugin_list = QListWidget()
        self.plugin_list.itemClicked.connect(self.display_plugin_info)

        self.check_updates_button = QPushButton("Check for Updates")
        self.check_updates_button.clicked.connect(self.check_updates)

        self.remove_plugin_button = QPushButton("Remove Plugin")
        self.remove_plugin_button.clicked.connect(self.remove_plugin)

        self.search_plugins_button = QPushButton("Search Plugins")
        self.search_plugins_button.clicked.connect(self.search_plugins)

        self.info_box = QScrollArea()
        self.info_box.setWidgetResizable(True)

        self.button_layout = QVBoxLayout()
        self.button_layout.addWidget(self.check_updates_button)
        self.button_layout.addWidget(self.remove_plugin_button)
        self.button_layout.addWidget(self.search_plugins_button)

        self.main_layout = QHBoxLayout()
        self.main_layout.addWidget(self.plugin_list)
        self.main_layout.addLayout(self.button_layout)

        self.layout.addLayout(self.main_layout)
        self.layout.addWidget(self.info_box)

        self.setCentralWidget(self.central_widget)

        # Run the plugin loading in the background to ensure GUI loads immediately
        asyncio.run_coroutine_threadsafe(self.load_plugins(), asyncio.get_event_loop())

    async def load_plugins(self):
        try:
            found_plugins, not_found_plugins = await load_plugins()
            self.plugin_list.clear()
            for plugin in found_plugins:
                item = QListWidgetItem(self.plugin_list)
                widget = create_plugin_list_item(plugin)
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.UserRole, plugin)
                self.plugin_list.setItemWidget(item, widget)

            for plugin_name, plugin_version in not_found_plugins:
                item = QListWidgetItem(self.plugin_list)
                widget = create_not_found_plugin_list_item(plugin_name, plugin_version)
                item.setSizeHint(widget.sizeHint())
                self.plugin_list.setItemWidget(item, widget)
        except Exception as e:
            logger.error(f"Error loading plugins: {e}")

    @asyncSlot()
    async def check_updates(self):
        try:
            updates = await check_for_updates(state.found_plugins)
            for plugin_name, current_version, latest_version, latest_version_date in updates:
                item = QListWidgetItem(
                    f"Update available for {plugin_name}: {current_version} -> {latest_version} ({prettify_date(latest_version_date)})")
                self.plugin_list.addItem(item)
        except Exception as e:
            logger.error(f"Error checking updates: {e}")

    def display_plugin_info(self, item):
        plugin = item.data(Qt.UserRole)
        if plugin:
            plugin_name, date_modified, mod_name, project_id, plugin_data, image_filepath = plugin
            author = plugin_data.get('author', 'Unknown Author')
            description = plugin_data.get('description', 'No description available.')

            info_layout = QHBoxLayout()

            image_label = QLabel()
            if image_filepath and os.path.exists(image_filepath):
                pixmap = QPixmap(image_filepath)
                image_label.setPixmap(pixmap)
                image_label.setFixedSize(128, 128)
                image_label.setScaledContents(True)
            else:
                image_label.setText("No Image")

            text_layout = QVBoxLayout()
            text_title = QLabel(
                f"<h1><a href='{project_id}' style='color: white'>{plugin_name}</a></h1>")
            text_description = QLabel(
                f"<p><strong>Mod Name:</strong> {mod_name}</p><p><strong>Date Modified:</strong> {prettify_date(date_modified)}</p><p><strong>Author:</strong> {author}</p><p><strong>Description:</strong> {description}</p>")

            text_layout.addWidget(text_title)
            text_layout.addWidget(text_description)

            info_layout.addWidget(image_label)
            info_layout.addLayout(text_layout)

            info_widget = QWidget()
            info_widget.setLayout(info_layout)

            self.info_box.setWidget(info_widget)

    def remove_plugin(self):
        selected_items = self.plugin_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            plugin = item.data(Qt.UserRole)
            plugin_name = plugin[0]

            try:
                os.remove(os.path.join(state.get_plugin_folder(), f"{plugin_name}.jar"))
                logger.info(f"Plugin '{plugin_name}' removed successfully")
                self.plugin_list.takeItem(self.plugin_list.row(item))
            except Exception as e:
                logger.error(f"Error removing plugin: {e}")
                self.show_error_message("Error", f"An error occurred while removing plugin '{plugin_name}'")

    def search_plugins(self):
        search_dialog = SearchDialog(self)
        search_dialog.exec_()


class SearchDialog(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Plugins")
        self.setMinimumSize(400, 200)

        central_widget = QWidget()
        layout = QVBoxLayout()

        self.search_field = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search)

        layout.addWidget(self.search_field)
        layout.addWidget(self.search_button)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    @asyncSlot()
    async def search(self):
        plugin_name = self.search_field.text()
        if plugin_name:
            results, _ = await search_plugin(plugin_name)
            if results:
                self.show_plugin_results(results)
            else:
                self.show_error_message("Error", f"No results found for '{plugin_name}'")

    def show_plugin_results(self, results):
        results_dialog = PluginResultsDialog(results, self)
        results_dialog.exec_()

    def show_error_message(self, title, message):
        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Warning)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(message)
        error_dialog.exec_()


class PluginResultsDialog(QMainWindow):
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Results")
        self.setMinimumSize(600, 400)

        central_widget = QWidget()
        layout = QVBoxLayout()

        self.plugin_list = QListWidget()
        self.plugin_list.itemDoubleClicked.connect(self.select_plugin)

        layout.addWidget(self.plugin_list)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.populate_results(results)

    def populate_results(self, results):
        for plugin in results:
            item = QListWidgetItem(plugin.get('title', plugin.get('name')))
            item.setData(Qt.UserRole, plugin)
            self.plugin_list.addItem(item)

    def select_plugin(self, item):
        plugin = item.data(Qt.UserRole)
        if plugin:
            state.set_selected_plugin(plugin)
            self.close()


if __name__ == "__main__":
    app = QAsyncApplication(sys.argv)
    qt_material.apply_stylesheet(app, theme='dark_lightgreen.xml')
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    main_window = MainWindow()
    main_window.show()

    with loop:
        loop.run_forever()
