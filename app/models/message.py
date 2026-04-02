from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum


class MessageType(str, Enum):
    INIT = "init"
    DRAW = "draw"
    DRAW_BATCH = "draw_batch"
    DRAW_BATCH_RESPONSE = "draw_batch_response"
    ERROR = "error"
    PIXELS_UPDATE = "pixels_update"
    CANVAS_SYNC = "canvas_sync"
    DISCONNECT = "disconnect"


class DrawMessage(BaseModel):
    """Mensagem de desenho enviada pelo cliente"""
    imageId: str
    x: int
    y: int
    color: str
    tool: str  # "brush" ou "eraser"
    timestamp: int  # timestamp do cliente


class InitMessage(BaseModel):
    """Mensagem de inicialização enviada pelo servidor"""
    type: str = MessageType.INIT
    pixelsDisponiveis: int
    pixelsMax: int
    canvas: dict  # { "x,y": color, ... }
    onlineCount: int
    activeUsers: list


class DrawResponseMessage(BaseModel):
    """Resposta a um draw"""
    type: str = MessageType.DRAW
    success: bool
    pixelsRemaining: int
    x: Optional[int] = None
    y: Optional[int] = None
    error: Optional[str] = None


class BroadcastDrawMessage(BaseModel):
    """Mensagem broacastada para todos"""
    type: str = MessageType.DRAW
    userId: str
    imageId: str
    x: int
    y: int
    color: str
    tool: str
    timestamp: int


class DrawBatchMessage(BaseModel):
    """Mensagem de desenho em lote"""
    type: str = MessageType.DRAW_BATCH
    draws: list[DrawMessage]


class DrawBatchResponseMessage(BaseModel):
    """Resposta de lote de desenho"""
    type: str = MessageType.DRAW_BATCH_RESPONSE
    success: bool
    processed: int
    failed: int
    pixelsRemaining: int
    error: str | None = None


class PixelsUpdateMessage(BaseModel):
    """Atualiza pixel disponível após recuperação"""
    type: str = MessageType.PIXELS_UPDATE
    pixelsDisponiveis: int
    pixelsGained: int
    lastUpdated: Optional[str] = None


class ErrorMessage(BaseModel):
    """Mensagem de erro"""
    type: str = MessageType.ERROR
    message: str
    code: str
