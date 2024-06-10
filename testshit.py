import asyncio
import json
import os
import logging
from difflib import SequenceMatcher
from urllib.request import urlretrieve

import aiohttp
import flet as ft
from aiohttp.client_exceptions import ClientError
import ctypes

# Configuration
API_KEY_MODRINTH = "mrp_OAGlIyM8TsArB075q7P9kMxMyFaqJEOqC00PcVWNG2CSZoWe3mhXylH0p4xt"
API_KEY_HANGAR = "f1eb3a00-8f95-43b7-bbde-1b4953aeae40.f09efd5c-a3a4-4f2b-991d-ed36e58d7bb5".strip()  # New Hangar API key
SEARCH_URL_MODRINTH = "https://api.modrinth.com/v2/search"
PROJECT_URL_MODRINTH = "https://api.modrinth.com/v2/project"
VERSION_URL_MODRINTH = "https://api.modrinth.com/v2/version"
AUTH_URL_HANGAR = "https://hangar.papermc.io/api/v1/authenticate"
SEARCH_URL_HANGAR = "https://hangar.papermc.io/api/v1/projects"
CACHE_DIR = "cache"
PLUGIN_FOLDER = "C:\\Custom\\Sandal Wearers\\plugins"
USER_AGENT = "PluginManagerApp/1.0"

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create cache directory if it doesn't exist
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


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

    def add_found_plugin(self, plugin, source):
        self.found_plugins.append((plugin, source))

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


def cache_plugin_data(plugin_name, data, source):
    with open(os.path.join(CACHE_DIR, f"{source}_{plugin_name}.json"), "w") as f:
        json.dump(data, f)


def load_cached_plugin_data(plugin_name, source):
    cache_path = os.path.join(CACHE_DIR, f"{source}_{plugin_name}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    return None


def cache_image(url, plugin_name, source):
    if not url:
        return None
    image_path = os.path.join(CACHE_DIR, f"{source}_{plugin_name}.png")
    if not os.path.exists(image_path):
        urlretrieve(url, image_path)
    return image_path


async def fetch(url, session, headers=None, params=None):
    try:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                error_message = await response.text()
                logging.error(f"Error fetching {url}: {response.status} - {error_message}")
                return None
            return await response.json()
    except ClientError as e:
        logging.error(f"Client error fetching {url}: {e}")
        return None


async def authenticate_hangar():
    async with aiohttp.ClientSession() as session:
        headers = {"User-Agent": USER_AGENT}
        api_key = state.get_api_key("hangar")
        async with session.post(f"{AUTH_URL_HANGAR}?apiKey={api_key}", headers=headers) as response:
            if response.status != 200:
                error_message = await response.text()
                logging.error(f"Error authenticating with Hangar API: {response.status} - {error_message}")
                return None
            data = await response.json()
            if "token" in data:
                return data["token"]
            else:
                logging.error("Failed to authenticate with Hangar API")
                return None


async def search_plugin_modrinth(plugin_name):
    async with aiohttp.ClientSession() as session:
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


async def search_plugin_hangar(plugin_name, token):
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT
        }
        params = {
            "q": plugin_name,
            "limit": 10
        }
        return await fetch(SEARCH_URL_HANGAR, session, headers=headers, params=params)


async def search_plugin(plugin_name):
    modrinth_results = await search_plugin_modrinth(plugin_name)
    logging.info(f"Modrinth results: {modrinth_results}")
    if modrinth_results and modrinth_results.get('total_hits', 0) > 0:
        return modrinth_results['hits'], "modrinth"

    token = await authenticate_hangar()
    if token:
        hangar_results = await search_plugin_hangar(plugin_name, token)
        logging.info(f"Hangar results: {hangar_results}")
        if hangar_results and hangar_results.get('pagination', {}).get('count', 0) > 0:
            return hangar_results['result'], "hangar"
    return [], None


async def fetch_version_details(version_id, session):
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    return await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)


def get_best_match(plugin_name, results, source):
    best_match = None
    highest_score = 0
    normalized_plugin_name = normalize_name(plugin_name)

    for plugin in results:
        if source == "modrinth":
            if 'title' not in plugin:
                logging.error(f"Plugin data does not contain 'title' key: {plugin}")
                continue
            normalized_result_name = normalize_name(plugin['title'])
        elif source == "hangar":
            if 'name' not in plugin:
                logging.error(f"Plugin data does not contain 'name' key: {plugin}")
                continue
            normalized_result_name = normalize_name(plugin['name'])

        score = SequenceMatcher(None, normalized_plugin_name, normalized_result_name).ratio()
        if score > highest_score:
            highest_score = score
            best_match = plugin

    if best_match and highest_score > 0.8:
        return best_match
    else:
        return None


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

    async with aiohttp.ClientSession() as session:
        tasks = []
        sources = []
        for plugin_name, plugin_version in plugins:
            tasks.append(search_plugin(plugin_name))

        results_with_sources = await asyncio.gather(*tasks)

        for (plugin_name, plugin_version), (result, source) in zip(plugins, results_with_sources):
            best_match = get_best_match(plugin_name, result, source)
            if best_match:
                plugin_data = load_cached_plugin_data(plugin_name, source)
                if not plugin_data:
                    plugin_data = best_match
                    cache_plugin_data(plugin_name, plugin_data, source)

                # Avoid fetching version details if they are already cached
                if source == "modrinth":
                    if 'versions' in plugin_data and all(isinstance(v, str) for v in plugin_data['versions']):
                        valid_versions = plugin_data['versions']
                    else:
                        # Fetch the version details for each version if not cached
                        version_details_tasks = [fetch_version_details(version_id, session) for version_id in
                                                 plugin_data['versions']]
                        version_details = await asyncio.gather(*version_details_tasks)
                        valid_versions = [v['version_number'] for v in version_details if v and 'version_number' in v]

                        # Update the cached plugin data with fetched version details
                        plugin_data['versions'] = valid_versions
                        cache_plugin_data(plugin_name, plugin_data, source)
                    latest_version = plugin_data['latest_version'] if 'latest_version' in plugin_data else \
                    valid_versions[-1] if valid_versions else "Unknown Version"
                else:
                    # For Hangar, handle versions differently if needed
                    latest_version = best_match.get('lastUpdated', "Unknown Version")

                state.add_found_plugin((plugin_name, latest_version,
                                        plugin_data['title'] if source == "modrinth" else plugin_data['name'],
                                        plugin_data['project_id'] if source == "modrinth" else plugin_data['namespace'][
                                            'slug'], plugin_data), source)
            else:
                state.add_not_found_plugin((plugin_name, plugin_version))

    return state.found_plugins, state.not_found_plugins


async def fetch_versions(project_id):
    url = f"{PROJECT_URL_MODRINTH}/{project_id}/version"
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    async with aiohttp.ClientSession() as session:
        return await fetch(url, session, headers=headers)


async def download_plugin(version_id, destination):
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {API_KEY_MODRINTH}",
            "User-Agent": USER_AGENT
        }
        data = await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)
        if not data or 'files' not in data or not data['files']:
            logging.error(f"Error fetching version data for {version_id}")
            return

        download_url = data['files'][0]['url']
        async with session.get(download_url) as download_response:
            if download_response.status != 200:
                logging.error(f"Error downloading {download_url}: {download_response.status}")
                return
            with open(destination, 'wb') as f:
                while True:
                    chunk = await download_response.content.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)


async def check_for_updates(found_plugins):
    updates = []
    for (plugin_name, current_version, mod_name, project_id, plugin_data), source in found_plugins:
        if source == "modrinth":
            if 'versions' not in plugin_data or not plugin_data['versions']:
                continue

            current_version_date = None
            latest_version = None
            latest_version_date = None

            for version in plugin_data['versions']:
                if version == current_version:
                    current_version_date = version['date_published']
                if latest_version_date is None or version['date_published'] > latest_version_date:
                    latest_version_date = version['date_published']
                    latest_version = version

            if current_version_date and latest_version_date > current_version_date:
                updates.append((plugin_name, current_version, latest_version))
        else:
            # For Hangar, handle updates differently if needed
            latest_version = plugin_data.get('lastUpdated', "Unknown Version")
            if latest_version != current_version:
                updates.append((plugin_name, current_version, latest_version))

    return updates


async def load_plugins(page):
    state.set_loading(True)
    page.update()

    state.clear_plugins()
    found_plugins, not_found_plugins = await check_plugins(state.get_plugin_folder())

    plugin_list = ft.ListView(expand=True, spacing=10, padding=10)
    for (plugin_name, plugin_version, mod_name, mod_id, plugin_data), source in found_plugins:
        categories = ', '.join(plugin_data.get('categories', [])) if 'categories' in plugin_data else ""
        image_path = cache_image(plugin_data.get('icon_url', plugin_data.get('avatarUrl')), plugin_name, source)
        if image_path:
            plugin_image = ft.Image(src=image_path, width=48, height=48)
        else:
            plugin_image = None
        plugin_info = ft.Column(
            controls=[
                ft.Text(f"Name: {plugin_name}", size=20, weight="bold"),
                ft.Text(f"Version: {plugin_version}"),
                ft.Text(f"Found Mod: {mod_name}"),
                ft.Text(f"Categories: {categories}"),
            ],
            alignment="start",
            spacing=5
        )
        plugin_container = ft.Container(
            content=ft.ListTile(
                title=ft.Text(plugin_name),
                subtitle=ft.Text(f"Version: {plugin_version}"),
                leading=plugin_image,
                trailing=ft.ElevatedButton(text="Update", on_click=lambda e, p=plugin_data: update_plugin(p)),
                on_click=lambda e, p=plugin_data: select_plugin(p, page),
            ),
            border=ft.border.all(1, "white") if state.get_selected_plugin() == plugin_data else None,
            padding=5
        )
        plugin_list.controls.append(plugin_container)

    for plugin_name, plugin_version in not_found_plugins:
        plugin_list.controls.append(
            ft.Container(
                ft.Row(
                    controls=[
                        ft.Text(f"Name: {plugin_name}", color="red"),
                        ft.Text(f"Version: {plugin_version}", color="red"),
                        ft.Text("Not Found", color="red"),
                    ],
                    alignment="start"
                ),
                padding=10
            )
        )

    state.set_loading(False)
    page.controls.append(plugin_list)
    page.update()


def update_plugin(plugin):
    logging.info(f"Updating plugin: {plugin.get('title', plugin.get('name'))}")


def select_plugin(plugin, page):
    state.set_selected_plugin(plugin)
    logging.info(f"Selected plugin: {plugin.get('title', plugin.get('name'))}")
    rebuild_info_box(page)


async def check_updates(page):
    state.set_loading(True)
    page.update()

    updates = await check_for_updates(state.found_plugins)
    plugin_list = ft.ListView(expand=True, spacing=10, padding=10)
    if updates:
        state.set_update_status(updates)
        for name, current_version, latest_version in updates:
            plugin_list.controls.append(
                ft.Text(f"Update available for {name}: {current_version} -> {latest_version}", color="green")
            )
    else:
        plugin_list.controls.append(
            ft.Text("All plugins are up to date.", color="green")
        )

    state.set_loading(False)
    page.controls.append(plugin_list)
    page.update()


def build_info_box():
    plugin = state.get_selected_plugin()
    if plugin:
        return ft.Column(
            controls=[
                ft.Text(f"Name: {plugin.get('title', plugin.get('name'))}", size=24, weight="bold",
                        url=f"https://modrinth.com/plugin/{plugin.get('project_id', plugin.get('namespace', {}).get('slug'))}"),
                ft.Text(f"Author: {plugin.get('author')}"),
                ft.Text(f"Description: {plugin.get('description')}"),
            ],
            alignment="start",
            spacing=5,
            expand=True,
            padding=10
        )
    else:
        return ft.Container()


def rebuild_info_box(page):
    info_box = build_info_box()
    for control in page.controls:
        if isinstance(control, ft.Container) and control.expand:
            control.content = info_box
            page.update()


def main(page: ft.Page):
    # Set process name for task manager
    ctypes.windll.kernel32.SetConsoleTitleW("PaperManager")

    page.title = "Plugin Manager"
    page.theme_mode = "dark"

    # Define UI components
    plugin_list = ft.ListView(expand=True, padding=10)

    update_button = ft.ElevatedButton(text="Check for Updates", on_click=lambda e: asyncio.run(check_updates(page)))
    remove_button = ft.ElevatedButton(text="Remove Plugins", on_click=lambda e: logging.info("Remove Plugins clicked"))
    search_button = ft.ElevatedButton(text="Search Plugins", on_click=lambda e: logging.info("Search Plugins clicked"))

    button_column = ft.Container(
        content=ft.Column(
            controls=[update_button, remove_button, search_button],
            alignment=ft.MainAxisAlignment.START,
            spacing=10,
            width=150
        ),
        padding=10
    )

    top_box = ft.Container(
        content=plugin_list,
        expand=True,
        padding=10,
        border=ft.border.all(1, "white")
    )

    info_box = ft.Container(
        content=build_info_box(),
        expand=True,
        padding=10,
        border=ft.border.all(1, "white")
    )

    main_layout = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    top_box,
                    button_column,
                ],
                expand=True,
                spacing=10,
                alignment=ft.MainAxisAlignment.START,
            ),
            ft.Container(
                content=info_box,
                expand=True,
                padding=10,
                alignment=ft.alignment.bottom_center,
                border=ft.border.all(1, "white")
            )
        ],
        expand=True,
        alignment=ft.MainAxisAlignment.START
    )

    # Add components to the page
    page.add(main_layout)

    # Load plugins
    asyncio.run(load_plugins(page))


if __name__ == "__main__":
    ft.app(target=main)
