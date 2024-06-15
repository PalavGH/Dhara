import traceback
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from server.api.dhara_api_handler import DharaAPIHandler
from loguru import logger
from contextlib import asynccontextmanager

app = FastAPI()
api_handler = DharaAPIHandler()


class PluginRequest(BaseModel):
    plugin_name: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Dhara Server")
    try:
        await api_handler.initialize()
        await api_handler.authenticate_hangar()
        await api_handler.authenticate_modrinth()
        yield
    except Exception as e:
        logger.exception(f"Error during server lifespan: {e}")
    finally:
        await api_handler.close()
        logger.info("Shutting down Dhara Server")


app.router.lifespan_context = lifespan


@app.get("/health")
async def health_check():
    logger.info("Health check endpoint called")
    return {"status": "ok"}


@app.post("/fetch_plugin")
async def fetch_plugin(request: PluginRequest):
    logger.info(f"Fetching plugin: {request.plugin_name}")
    try:
        plugin_data = await api_handler.fetch_plugin_data(request.plugin_name)
        if "error" in plugin_data:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return plugin_data
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"Internal server error while fetching plugin: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
