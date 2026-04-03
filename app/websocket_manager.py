"""
WebSocket Manager - Gerencia conexões WebSocket
"""
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
import logging
from typing import Dict, Set, Optional
from datetime import datetime
from app.core.config import settings
from app.models.message import (
    InitMessage, DrawMessage, DrawResponseMessage,
    BroadcastDrawMessage, ErrorMessage, MessageType, PixelsUpdateMessage
)
from app.services.redis_service import redis_service
from app.services.mongo_service import mongo_service

logger = logging.getLogger(__name__)


async def get_user_pixel_config(user_id: str) -> dict:
    """Carrega configuracao atual de pixels do usuario a partir do Mongo."""
    return await mongo_service.get_or_create_user_pixel_config(user_id)


def build_pixel_state(pixels_disponiveis: int, pixels_max: int, seconds_until_next_pixel: int) -> dict:
    return {
        "pixelsDisponiveis": pixels_disponiveis,
        "pixelsMax": pixels_max,
        "secondsUntilNextPixel": max(0, seconds_until_next_pixel),
    }


class ConnectionManager:
    def __init__(self):
        # user_id -> set of WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # image_id -> set of user_ids
        self.image_viewers: Dict[str, Set[str]] = {}
        # pubsub listener
        self.pubsub_listener: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, user_id: str, image_id: str):
        """Conecta um novo cliente"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        
        self.active_connections[user_id].add(websocket)
        
        if image_id not in self.image_viewers:
            self.image_viewers[image_id] = set()
        
        self.image_viewers[image_id].add(user_id)
        
        logger.info(f"Client connected: {user_id} on image {image_id}")

    async def disconnect(self, user_id: str, websocket: WebSocket, image_id: str):
        """Desconecta um cliente"""
        try:
            removed_connection = False
            removed_viewer = False

            if user_id in self.active_connections:
                removed_connection = websocket in self.active_connections[user_id]
                self.active_connections[user_id].discard(websocket)
                
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            
            if image_id in self.image_viewers:
                removed_viewer = user_id in self.image_viewers[image_id]
                self.image_viewers[image_id].discard(user_id)
                
                if not self.image_viewers[image_id]:
                    del self.image_viewers[image_id]

            if removed_connection or removed_viewer:
                logger.info(f"Client disconnected: {user_id} from image {image_id}")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Envia mensagem para um cliente específico"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast(self, image_id: str, message: dict, exclude_user: Optional[str] = None):
        """Faz broadcast de mensagem para todos os clientes de uma imagem"""
        if image_id not in self.image_viewers:
            return
        
        for user_id in self.image_viewers[image_id]:
            if exclude_user and user_id == exclude_user:
                continue
            
            if user_id in self.active_connections:
                for websocket in self.active_connections[user_id]:
                    try:
                        await websocket.send_json(message)
                    except Exception as e:
                        logger.error(f"Error broadcasting to {user_id}: {e}")

    def get_online_count(self, image_id: str) -> int:
        """Obtém número de usuários online para uma imagem"""
        return len(self.image_viewers.get(image_id, set()))

    def get_active_users(self, image_id: str) -> list:
        """Obtém lista de usuários ativos para uma imagem"""
        return list(self.image_viewers.get(image_id, set()))


# Instância global
connection_manager = ConnectionManager()


async def recover_user_pixels(user_id: str, websocket: WebSocket, source: str = "periodic") -> dict:
    """Recupera pixels e devolve estado atualizado do saldo do usuario."""
    try:
        pixel_config = await get_user_pixel_config(user_id)
        pixels_max = pixel_config["pixelsMax"]
        current_time = int(datetime.utcnow().timestamp())
        new_pixels, pixels_gained, seconds_until_next_pixel = redis_service.recover_pixels(
            user_id=user_id,
            pixels_max=pixels_max,
            current_time=current_time,
            recovery_interval=settings.PIXEL_RECOVERY_INTERVAL,
        )

        pixel_state = build_pixel_state(new_pixels, pixels_max, seconds_until_next_pixel)

        if pixels_gained > 0:
            await mongo_service.log_countdown_recovery(user_id, pixels_gained, source)

            update_msg = {
                "type": MessageType.PIXELS_UPDATE,
                **pixel_state,
                "pixelsGained": pixels_gained,
                "lastUpdated": datetime.utcnow().isoformat(),
            }
            await connection_manager.send_personal(websocket, update_msg)

        return pixel_state

    except Exception as e:
        logger.error(f"Error recovering pixels for {user_id}: {e}")
        pixel_config = await get_user_pixel_config(user_id)
        return build_pixel_state(
            redis_service.get_pixels(user_id),
            pixel_config["pixelsMax"],
            0,
        )


async def periodic_recovery_task(user_id: str, websocket: WebSocket, recovery_event: asyncio.Event):
    """Task que agenda a recuperação com base no próximo pixel e acorda após novos envios."""
    try:
        while True:
            pixel_state = await recover_user_pixels(user_id, websocket, source="periodic")

            if pixel_state["pixelsDisponiveis"] >= pixel_state["pixelsMax"]:
                sleep_for = 5
            else:
                sleep_for = max(1, pixel_state["secondsUntilNextPixel"])

            try:
                await asyncio.wait_for(recovery_event.wait(), timeout=sleep_for)
                recovery_event.clear()
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        logger.debug(f"Periodic recovery task canceled for {user_id}")
    except Exception as e:
        logger.error(f"Periodic recovery task error for {user_id}: {e}")


async def handle_websocket_connection(websocket: WebSocket, user_id: str, image_id: str):
    """
    Handler principal para conexão WebSocket
    """
    await connection_manager.connect(websocket, user_id, image_id)
    recovery_task = None
    recovery_event = asyncio.Event()

    try:
        pixel_config = await get_user_pixel_config(user_id)
        pixels_max = pixel_config["pixelsMax"]

        # Inicializa o usuário se necessário
        current_time = int(datetime.utcnow().timestamp())
        redis_service.init_user(user_id, pixels_max, current_time)

        # Tenta recuperação imediata (caso esteja offline por tempo suficiente)
        pixel_state = await recover_user_pixels(user_id, websocket, source="connection")

        # Inicia task periódica de recuperação
        recovery_task = asyncio.create_task(periodic_recovery_task(user_id, websocket, recovery_event))

        # Obtém estado atual
        canvas = redis_service.get_canvas(image_id)
        online_count = connection_manager.get_online_count(image_id)
        active_users = connection_manager.get_active_users(image_id)
        
        # Envia inicialização
        init_msg = {
            "type": MessageType.INIT,
            **pixel_state,
            "canvas": canvas,
            "onlineCount": online_count,
            "activeUsers": active_users
        }
        await connection_manager.send_personal(websocket, init_msg)
        
        logger.info(f"Init sent to {user_id}: {pixel_state['pixelsDisponiveis']}/{pixel_state['pixelsMax']}")
        
        # Loop de mensagens
        while True:
            data = await websocket.receive_json()

            msg_type = data.get("type")

            if msg_type == MessageType.DRAW or msg_type == "draw":
                await handle_draw_message(
                    websocket=websocket,
                    user_id=user_id,
                    image_id=image_id,
                    message=data,
                    recovery_event=recovery_event,
                )
            elif msg_type == MessageType.DRAW_BATCH or msg_type == "draw_batch":
                await handle_draw_batch(
                    websocket=websocket,
                    user_id=user_id,
                    image_id=image_id,
                    message=data,
                    recovery_event=recovery_event,
                )
            else:
                logger.debug(f"Unknown message type from {user_id}: {msg_type}")

    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected by client: {user_id} on image {image_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            error_msg = {
                "type": MessageType.ERROR,
                "message": str(e),
                "code": "ws_error"
            }
            await connection_manager.send_personal(websocket, error_msg)
        except:
            pass
    finally:
        if recovery_task:
            recovery_task.cancel()
            try:
                await recovery_task
            except asyncio.CancelledError:
                pass
        await connection_manager.disconnect(user_id, websocket, image_id)


async def handle_draw_message(
    websocket: WebSocket,
    user_id: str,
    image_id: str,
    message: dict,
    recovery_event: Optional[asyncio.Event] = None,
):
    """
    Handler para mensagem de desenho
    """
    try:
        pixel_config = await get_user_pixel_config(user_id)
        pixels_max = pixel_config["pixelsMax"]
        x = message.get("x")
        y = message.get("y")
        color = message.get("color")
        tool = message.get("tool")
        timestamp = message.get("timestamp", int(datetime.utcnow().timestamp() * 1000))
        
        # Validações
        if not all([x is not None, y is not None, color, tool]):
            error_msg = {
                "type": MessageType.ERROR,
                "message": "Missing required fields",
                "code": "invalid_message"
            }
            await connection_manager.send_personal(websocket, error_msg)
            return
        
        # Tenta desenhar no Redis (Lua script)
        success, pixels_remaining, result = redis_service.draw_pixel(
            image_id=image_id,
            user_id=user_id,
            x=x,
            y=y,
            color=color,
            tool=tool,
            timestamp=int(timestamp)
        )
        
        if success == 0:
            # Falha (out of pixels ou rate limit)
            error_msg = {
                "type": MessageType.ERROR,
                "message": str(result),
                "code": result
            }
            await connection_manager.send_personal(websocket, error_msg)
            return
        
        # Sucesso! Faz broadcast
        broadcast_msg = {
            "type": MessageType.DRAW,
            "userId": user_id,
            "imageId": image_id,
            "x": x,
            "y": y,
            "color": color,
            "tool": tool,
            "timestamp": timestamp
        }
        
        await connection_manager.broadcast(image_id, broadcast_msg)
        
        # Envia confirmação de pixels restantes
        response_msg = {
            "type": "draw_response",
            "success": True,
            "pixelsRemaining": pixels_remaining,
            "pixelsMax": pixels_max,
            "secondsUntilNextPixel": settings.PIXEL_RECOVERY_INTERVAL,
        }
        await connection_manager.send_personal(websocket, response_msg)

        if recovery_event:
            recovery_event.set()
        
        logger.debug(f"{user_id} drew pixel at ({x},{y}), {pixels_remaining} remaining")
    
    except Exception as e:
        logger.error(f"Error handling draw message: {e}")
        try:
            error_msg = {
                "type": MessageType.ERROR,
                "message": "Internal server error",
                "code": "server_error"
            }
            await connection_manager.send_personal(websocket, error_msg)
        except:
            pass


async def handle_draw_batch(
    websocket: WebSocket,
    user_id: str,
    image_id: str,
    message: dict,
    recovery_event: Optional[asyncio.Event] = None,
):
    """Handler para mensagem de desenho em lote"""
    draws = message.get("draws")
    pixel_config = await get_user_pixel_config(user_id)
    pixels_max = pixel_config["pixelsMax"]

    if not isinstance(draws, list):
        await connection_manager.send_personal(websocket, {
            "type": MessageType.DRAW_BATCH_RESPONSE,
            "success": False,
            "processed": 0,
            "failed": 0,
            "pixelsRemaining": redis_service.get_pixels(user_id),
            "pixelsMax": pixels_max,
            "secondsUntilNextPixel": 0,
            "error": "invalid_draw_batch"
        })
        return

    normalized_draws = []

    for draw in draws:
        if not all([draw.get("x") is not None, draw.get("y") is not None, draw.get("color"), draw.get("tool")]):
            await connection_manager.send_personal(websocket, {
                "type": MessageType.DRAW_BATCH_RESPONSE,
                "success": False,
                "processed": 0,
                "failed": len(draws),
                "pixelsRemaining": redis_service.get_pixels(user_id),
                "pixelsMax": pixels_max,
                "secondsUntilNextPixel": 0,
                "error": "invalid_draw_batch"
            })
            return

        normalized_draws.append({
            "x": int(draw.get("x")),
            "y": int(draw.get("y")),
            "color": str(draw.get("color")),
            "tool": str(draw.get("tool")),
            "timestamp": int(draw.get("timestamp", int(datetime.utcnow().timestamp() * 1000))),
        })

    pixels_remaining = redis_service.get_pixels(user_id)

    if pixels_remaining <= 0 or len(normalized_draws) > pixels_remaining:
        await connection_manager.send_personal(websocket, {
            "type": MessageType.DRAW_BATCH_RESPONSE,
            "success": False,
            "processed": 0,
            "failed": len(normalized_draws),
            "pixelsRemaining": pixels_remaining,
            "pixelsMax": pixels_max,
            "secondsUntilNextPixel": 0,
            "error": "out_of_pixels"
        })
        return

    submitted_at = int(datetime.utcnow().timestamp())
    success, pixels_remaining, error_code = redis_service.draw_batch(
        image_id=image_id,
        user_id=user_id,
        draws=normalized_draws,
        submitted_at=submitted_at,
    )

    if success == 0:
        await connection_manager.send_personal(websocket, {
            "type": MessageType.DRAW_BATCH_RESPONSE,
            "success": False,
            "processed": 0,
            "failed": len(normalized_draws),
            "pixelsRemaining": pixels_remaining,
            "pixelsMax": pixels_max,
            "secondsUntilNextPixel": 0,
            "error": error_code or "invalid_draw_batch",
        })
        return

    for draw in normalized_draws:
        broadcast_msg = {
            "type": MessageType.DRAW,
            "userId": user_id,
            "imageId": image_id,
            "x": draw["x"],
            "y": draw["y"],
            "color": draw["color"],
            "tool": draw["tool"],
            "timestamp": draw["timestamp"],
        }
        await connection_manager.broadcast(image_id, broadcast_msg)

    response_msg = {
        "type": MessageType.DRAW_BATCH_RESPONSE,
        "success": True,
        "processed": len(normalized_draws),
        "failed": 0,
        "pixelsRemaining": pixels_remaining,
        "pixelsMax": pixels_max,
        "secondsUntilNextPixel": settings.PIXEL_RECOVERY_INTERVAL if pixels_remaining < pixels_max else 0,
        "error": None,
    }
    await connection_manager.send_personal(websocket, response_msg)

    if recovery_event:
        recovery_event.set()

