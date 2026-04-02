"""
Background tasks - Persistência de dados
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List
from app.services.redis_service import redis_service
from app.services.mongo_service import mongo_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class PersistenceManager:
    def __init__(self):
        self.is_running = False
        self.task = None

    async def start(self):
        """Inicia background job de persistência"""
        if self.is_running:
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._persistence_loop())
        logger.info("Persistence manager started")

    async def stop(self):
        """Para background job de persistência"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Persistence manager stopped")

    async def _persistence_loop(self):
        """Loop principal de persistência"""
        while self.is_running:
            try:
                await asyncio.sleep(settings.PERSISTENCE_INTERVAL)
                await self.persist_draw_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Persistence error: {e}")

    async def persist_draw_logs(self):
        """
        Persiste logs de desenhos do Redis para MongoDB
        Esta função pega o draw_log de cada imagem e salva no MongoDB
        """
        try:
            # Nota: Redis não tem iteração direta sobre padrões de chaves
            # Em produção, você manteria uma lista de "active_image_ids"
            # Para agora, vamos apenas loggar que estamos prontos para persistência
            logger.debug("Persistence cycle: checking draw logs...")
            
            # Exemplo: se tivéssemos imagens ativas
            # for image_id in active_images:
            #     await self._persist_image_draws(image_id)
        
        except Exception as e:
            logger.error(f"Error in persistence loop: {e}")

    async def _persist_image_draws(self, image_id: str):
        """Persiste desenhos de uma imagem específica"""
        try:
            # Obtém draw_log do Redis
            draw_log = redis_service.get_draw_log(image_id)
            
            if not draw_log:
                return
            
            # Converte para formato MongoDB
            pixels_to_insert = []
            
            for entry in draw_log:
                # Format: "userId:x,y:color:tool:timestamp"
                try:
                    parts = entry.split(":")
                    if len(parts) >= 5:
                        user_id, pixel_key, color, tool, timestamp = parts[0], parts[1], parts[2], parts[3], parts[4]
                        x, y = map(int, pixel_key.split(","))
                        
                        pixels_to_insert.append({
                            "imageId": image_id,
                            "userId": user_id,
                            "x": x,
                            "y": y,
                            "color": color,
                            "tool": tool,
                            "timestamp": datetime.utcfromtimestamp(int(timestamp) / 1000),
                            "createdAt": datetime.utcnow()
                        })
                except Exception as e:
                    logger.warning(f"Could not parse draw log entry: {entry}, error: {e}")
            
            # Insere no MongoDB
            if pixels_to_insert:
                success = await mongo_service.insert_many_pixels(pixels_to_insert)
                if success:
                    # Limpa o log do Redis após persistência bem-sucedida
                    redis_service.redis_client.delete(f"draw_log:{image_id}")
                    logger.info(f"Persisted {len(pixels_to_insert)} pixels for image {image_id}")
        
        except Exception as e:
            logger.error(f"Error persisting image {image_id}: {e}")

    async def cleanup_old_data(self):
        """
        Limpa dados antigos
        Pode ser executado periodicamente
        """
        try:
            # Exemplo: limpar snapshots antigos do MongoDB
            pass
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")


# Instância global
persistence_manager = PersistenceManager()
