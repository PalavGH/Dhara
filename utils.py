import asyncio
import os
import sqlite3
import json
import traceback
from datetime import datetime
from difflib import SequenceMatcher
from contextlib import asynccontextmanager
from loguru import logger
import httpx
from httpx import HTTPStatusError
from state import state  # Import state from state.py

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Load API keys from environment variables
API_KEY_MODRINTH = os.environ.get(config['api_keys']['modrinth'])
API_KEY_HANGAR = os.environ.get(config['api_keys']['hangar'])

# Load other configurations
SEARCH_URL_MODRINTH = config['urls']['search_modrinth']
AUTH_URL_HANGAR = config['urls']['auth_hangar']
SEARCH_URL_HANGAR = config['urls']['search_hangar']
CACHE_DIR = config['paths']['cache_dir']
PLUGIN_FOLDER = config['paths']['plugin_folder']
DB_PATH = config['paths']['db_path']
USER_AGENT = config['user_agent']
DB_SCHEMA = config['db_schema']['plugins']

logger.add("plugin_manager.log", rotation="10 MB")

def normalize_name(name):
    return ''.join(e for e in name if e.isalpha()).lower()

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
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS plugins (
                      {", ".join([f"{key} {value}" for key, value in DB_SCHEMA.items()])}
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
        json_response = response.json()
        if isinstance(json_response, dict):
            return json_response
        else:
            logger.error(f"Unexpected response format: {json_response}")
            return None
    except HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code} - {e.response.text}")
        logger.error(traceback.format_exc())
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        logger.error(traceback.format_exc())
        return None

async def authenticate_hangar():
    try:
        async with http_session() as session:
            headers = {"User-Agent": USER_AGENT}
            response = await session.post(f"{AUTH_URL_HANGAR}?apiKey={API_KEY_HANGAR}", headers=headers)
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
    # Normalize the plugin name
    normalized_plugin_name = normalize_name(plugin_name)

    # Check cache (SQLite) first
    cached_data = await get_plugin_from_db(normalized_plugin_name)
    if cached_data:
        logger.info(f"Found cached data for {plugin_name}")
        return [cached_data], "cache"

    # If not in cache, search in Hangar first
    token = await authenticate_hangar()
    if token:
        hangar_results = await search_plugin_hangar(plugin_name, token)
        if hangar_results:
            hangar_plugins = [convert_hangar_to_unified(plugin) for plugin in hangar_results.get('result', [])]
            logger.debug(f"Hangar results: {hangar_plugins}")
            best_match = get_best_match(normalized_plugin_name, hangar_plugins)
            if best_match:
                await insert_or_update_plugin(best_match)
                return [best_match], "hangar"

    # If not found in Hangar or no best match, search in Modrinth
    modrinth_results = await search_plugin_modrinth(plugin_name)
    if modrinth_results:
        modrinth_plugins = [convert_modrinth_to_unified(plugin) for plugin in modrinth_results.get('hits', [])]
        logger.debug(f"Modrinth results: {modrinth_plugins}")
        best_match = get_best_match(normalized_plugin_name, modrinth_plugins)
        if best_match:
            await insert_or_update_plugin(best_match)
            return [best_match], "modrinth"

    return [], None

async def fetch_version_details(version_id, session):
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    return await fetch(f"{config['urls']['version_modrinth']}/{version_id}", session, headers=headers)

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
        logger.debug(f"Comparing {plugin_name} with {plugin.get('name')}")
        if isinstance(plugin, dict):
            normalized_result_name = normalize_name(plugin['title'] if plugin.get('title') else plugin['name'])
            score = SequenceMatcher(None, normalized_plugin_name, normalized_result_name).ratio()
            logger.debug(f"Score for {plugin.get('name')}: {score}")
            if score > highest_score:
                highest_score = score
                best_match = plugin
        else:
            logger.error(f"Unexpected plugin type: {type(plugin)}. Expected dict, got {type(plugin)}")

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
                logger.debug(f"Results type: {type(results)}, value: {results}")
                logger.debug(f"Source type: {type(source)}, value: {source}")
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

                    state.add_found_plugin((plugin_name, plugin_data['date_modified'], plugin_data['title'],
                                            plugin_data['url'], plugin_data, image_filepath))
                else:
                    state.add_not_found_plugin((plugin_name, plugin_version))
    except Exception as e:
        logger.error(f"Error checking plugins: {e}")
        logger.error(traceback.format_exc())

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

def prettify_date(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except ValueError:
        return date_str

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
