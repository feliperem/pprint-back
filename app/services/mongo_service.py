"""
MongoDB Service - Operações com MongoDB
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from typing import Optional, List, Dict, Any
from app.core.config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MongoService:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def connect(self):
        """Conecta ao MongoDB"""
        try:
            self.client = AsyncIOMotorClient(settings.MONGO_URL)
            self.db = self.client[settings.MONGO_DB_NAME]
            # Testa conexão
            await self.client.admin.command('ping')
            logger.info("Connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def disconnect(self):
        """Desconecta do MongoDB"""
        try:
            if self.client:
                self.client.close()
                logger.info("Disconnected from MongoDB")
        except Exception as e:
            logger.error(f"Error disconnecting from MongoDB: {e}")

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Obtém dados do usuário"""
        try:
            users = self.db["users"]
            user = await users.find_one({"_id": user_id})
            return user
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def upsert_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """Insere ou atualiza usuário"""
        try:
            users = self.db["users"]
            user_data["_id"] = user_id
            user_data["updatedAt"] = datetime.utcnow()
            
            await users.update_one(
                {"_id": user_id},
                {"$set": user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting user: {e}")
            return False

    async def get_or_create_user_pixel_config(self, user_id: str) -> Dict[str, Any]:
        """Obtém configuração de pixels do usuário, criando defaults quando necessário."""
        default_pixels_max = settings.PIXELS_MAX

        try:
            users = self.db["users"]
            now = datetime.utcnow()

            await users.update_one(
                {"_id": user_id},
                {
                    "$setOnInsert": {
                        "createdAt": now,
                        "pixelsMax": default_pixels_max,
                    },
                    "$set": {
                        "updatedAt": now,
                    },
                },
                upsert=True,
            )

            user = await users.find_one({"_id": user_id}, {"pixelsMax": 1})
            pixels_max = int((user or {}).get("pixelsMax", default_pixels_max))

            return {
                "userId": user_id,
                "pixelsMax": pixels_max,
            }
        except Exception as e:
            logger.error(f"Error getting pixel config for {user_id}: {e}")
            return {
                "userId": user_id,
                "pixelsMax": default_pixels_max,
            }

    async def insert_pixel(self, pixel_data: Dict[str, Any]) -> Optional[str]:
        """Insere um pixel no histórico"""
        try:
            pixels = self.db["pixels"]
            result = await pixels.insert_one(pixel_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error inserting pixel: {e}")
            return None

    async def insert_many_pixels(self, pixels_data: List[Dict[str, Any]]) -> bool:
        """Insere múltiplos pixels em batch"""
        try:
            if not pixels_data:
                return True
            
            pixels = self.db["pixels"]
            await pixels.insert_many(pixels_data, ordered=False)
            return True
        except Exception as e:
            logger.error(f"Error inserting pixels: {e}")
            return False

    async def get_image_pixels(self, image_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtém todos os pixels de uma imagem (opcionalmente filtrados por usuário)"""
        try:
            pixels = self.db["pixels"]
            query = {"imageId": image_id}
            
            if user_id:
                query["userId"] = user_id
            
            results = await pixels.find(query).to_list(length=None)
            return results or []
        except Exception as e:
            logger.error(f"Error getting image pixels: {e}")
            return []

    async def log_countdown_recovery(self, user_id: str, pixels_recovered: int, 
                                     source: str) -> bool:
        """Registra uma recuperação de pixels"""
        try:
            log = self.db["countdown_log"]
            await log.update_one(
                {"_id": user_id},
                {
                    "$push": {
                        "recovery_history": {
                            "timestamp": datetime.utcnow(),
                            "pixelsRecovered": pixels_recovered,
                            "source": source
                        }
                    },
                    "$set": {
                        "lastChecked": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error logging countdown recovery: {e}")
            return False

    async def get_canvas_snapshot(self, image_id: str) -> Optional[Dict[str, Any]]:
        """Obtém um snapshot do canvas"""
        try:
            snapshots = self.db["canvas_snapshots"]
            snapshot = await snapshots.find_one(
                {"imageId": image_id},
                sort=[("createdAt", -1)]
            )
            return snapshot
        except Exception as e:
            logger.error(f"Error getting canvas snapshot: {e}")
            return None

    async def save_canvas_snapshot(self, image_id: str, canvas_data: Dict[str, str]) -> bool:
        """Salva um snapshot do canvas"""
        try:
            snapshots = self.db["canvas_snapshots"]
            await snapshots.insert_one({
                "imageId": image_id,
                "canvas": canvas_data,
                "createdAt": datetime.utcnow()
            })
            return True
        except Exception as e:
            logger.error(f"Error saving canvas snapshot: {e}")
            return False

    async def get_stats(self, image_id: str) -> Dict[str, Any]:
        """Obtém estatísticas de uma imagem"""
        try:
            pixels = self.db["pixels"]
            
            total_pixels = await pixels.count_documents({"imageId": image_id})
            unique_users = len(await pixels.distinct("userId", {"imageId": image_id}))
            
            return {
                "imageId": image_id,
                "totalPixels": total_pixels,
                "uniqueUsers": unique_users
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}


# Instância global
mongo_service = MongoService()
