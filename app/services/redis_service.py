"""
Redis Service - Operações com Redis
"""
import redis
import json
from typing import Optional, Dict, List
from app.core.config import settings
from app.utils.lua_scripts import DRAW_PIXEL_SCRIPT, RECOVER_PIXELS_SCRIPT, INIT_USER_SCRIPT
import logging

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self):
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )
        
        # Registra Lua scripts
        self.draw_pixel_sha = self.redis_client.script_load(DRAW_PIXEL_SCRIPT)
        self.recover_pixels_sha = self.redis_client.script_load(RECOVER_PIXELS_SCRIPT)
        self.init_user_sha = self.redis_client.script_load(INIT_USER_SCRIPT)

    def ping(self) -> bool:
        """Testa conexão com Redis"""
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    def init_user(self, user_id: str, pixels_max: int, current_time: int) -> tuple[int, int]:
        """
        Inicializa usuário com pixels máximos
        Retorna: (was_new, pixels_count)
        """
        try:
            result = self.redis_client.evalsha(
                self.init_user_sha,
                1,
                user_id,
                pixels_max,
                current_time
            )
            return tuple(result)
        except Exception as e:
            logger.error(f"Error initializing user {user_id}: {e}")
            raise

    def draw_pixel(self, image_id: str, user_id: str, x: int, y: int, color: str, 
                   tool: str, timestamp: int) -> tuple[int, int, Optional[str]]:
        """
        Desenha um pixel atomicamente
        Retorna: (success, pixels_remaining, prev_color or error_msg)
        """
        pixel_key = f"{x},{y}"
        
        try:
            result = self.redis_client.evalsha(
                self.draw_pixel_sha,
                1,
                image_id,
                user_id,
                pixel_key,
                color,
                tool,
                timestamp
            )
            
            if result[0] == 0:
                # Falha
                return (0, 0, result[1])  # (success, remaining, error)
            else:
                # Sucesso
                return (1, int(result[1]), result[2])  # (success, remaining, prev_color)
        except Exception as e:
            logger.error(f"Error drawing pixel: {e}")
            raise

    def recover_pixels(self, user_id: str, pixels_max: int, current_time: int, 
                      recovery_interval: int) -> tuple[int, int]:
        """
        Recupera pixels baseado em tempo decorrido
        Retorna: (total_pixels, pixels_gained)
        """
        try:
            result = self.redis_client.evalsha(
                self.recover_pixels_sha,
                1,
                user_id,
                pixels_max,
                current_time,
                recovery_interval
            )
            return tuple(result)
        except Exception as e:
            logger.error(f"Error recovering pixels: {e}")
            raise

    def get_pixels(self, user_id: str) -> int:
        """Obtém pixels atuais do usuário"""
        try:
            pixels = self.redis_client.get(f"pixels:{user_id}")
            return int(pixels) if pixels else 0
        except Exception as e:
            logger.error(f"Error getting pixels: {e}")
            return 0

    def set_pixels(self, user_id: str, pixels: int) -> bool:
        """Define pixels do usuário"""
        try:
            self.redis_client.set(f"pixels:{user_id}", pixels)
            return True
        except Exception as e:
            logger.error(f"Error setting pixels: {e}")
            return False

    def get_canvas(self, image_id: str) -> Dict[str, str]:
        """Obtém canvas completo para uma imagem"""
        try:
            canvas_data = self.redis_client.hgetall(f"canvas:{image_id}")
            return canvas_data or {}
        except Exception as e:
            logger.error(f"Error getting canvas: {e}")
            return {}

    def publish_draw(self, image_id: str, message: str) -> int:
        """Publica um evento de desenho para todos os clientes"""
        try:
            return self.redis_client.publish(f"pixels:{image_id}", message)
        except Exception as e:
            logger.error(f"Error publishing draw: {e}")
            return 0

    def get_draw_log(self, image_id: str, start: int = 0, end: int = -1) -> List[str]:
        """Obtém log de desenhos para uma imagem"""
        try:
            return self.redis_client.lrange(f"draw_log:{image_id}", start, end) or []
        except Exception as e:
            logger.error(f"Error getting draw log: {e}")
            return []

    def get_last_pixel_reset(self, user_id: str) -> int:
        """Obtém timestamp do último reset de pixels"""
        try:
            reset_time = self.redis_client.get(f"last_pixel_reset:{user_id}")
            return int(reset_time) if reset_time else 0
        except Exception as e:
            logger.error(f"Error getting last pixel reset: {e}")
            return 0

    def set_last_pixel_reset(self, user_id: str, timestamp: int) -> bool:
        """Define timestamp do último reset de pixels"""
        try:
            self.redis_client.set(f"last_pixel_reset:{user_id}", timestamp)
            return True
        except Exception as e:
            logger.error(f"Error setting last pixel reset: {e}")
            return False

    def delete_user_data(self, user_id: str) -> bool:
        """Deleta todos os dados de um usuário do Redis"""
        try:
            pipe = self.redis_client.pipeline()
            pipe.delete(f"pixels:{user_id}")
            pipe.delete(f"last_pixel_reset:{user_id}")
            pipe.delete(f"rate_limit:{user_id}")
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting user data: {e}")
            return False

    def close(self):
        """Fecha a conexão"""
        try:
            self.redis_client.close()
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")


# Instância global
redis_service = RedisService()
