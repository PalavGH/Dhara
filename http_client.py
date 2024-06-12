import httpx
from contextlib import asynccontextmanager
from loguru import logger

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
