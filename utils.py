import os
from contextlib import asynccontextmanager
from datetime import datetime
from difflib import SequenceMatcher
from loguru import logger

import httpx


def prettify_date(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except ValueError:
        return date_str


def normalize_name(name):
    return ''.join(e for e in name if e.isalpha()).lower()


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
    return [(os.path.splitext(filename)[0], "Unknown Version") for filename in os.listdir(folder_path) if
            filename.endswith(".jar")]


@asynccontextmanager
async def http_session():
    async with httpx.AsyncClient() as session:
        try:
            yield session
        finally:
            await session.aclose()


async def fetch(url, session, headers=None, params=None):
    try:
        response = await session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        return {"error": str(e), "status_code": e.response.status_code}
    except Exception as e:
        return {"error": str(e)}


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
