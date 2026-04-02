from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.screenshot.router.screenshot_router import router as screenshot_router
from app.websocket_manager import handle_websocket_connection
from app.services.mongo_service import mongo_service
from app.services.redis_service import redis_service
from app.utils.auth import extract_user_id_from_token
import logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    app.include_router(screenshot_router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        token: str = Query(...),
        imageId: str = Query(...)
    ):
        """
        WebSocket endpoint para comunicação em tempo real
        Query params:
        - token: JWT token do usuário
        - imageId: ID da imagem que está sendo pintada
        """
        try:
            # Extrai user_id do token
            user_id = extract_user_id_from_token(token)
            
            if not user_id:
                await websocket.close(code=4001, reason="Invalid token")
                return
            
            logger.info(f"WebSocket connection attempt: {user_id} for image {imageId}")
            
            # Handler principal
            await handle_websocket_connection(websocket, user_id, imageId)
        
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            try:
                await websocket.close(code=4000, reason="Internal error")
            except:
                pass

    # Startup event
    @app.on_event("startup")
    async def startup():
        """Inicializa conexões e serviços"""
        try:
            # MongoDB
            await mongo_service.connect()
            logger.info("MongoDB connected")
            
            # Redis
            if redis_service.ping():
                logger.info("Redis connected")
            else:
                logger.error("Redis connection failed")
        except Exception as e:
            logger.error(f"Startup error: {e}")
            raise

    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown():
        """Fecha conexões"""
        try:
            await mongo_service.disconnect()
            redis_service.close()
            logger.info("Services disconnected")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")

    return app
