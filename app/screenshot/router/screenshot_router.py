from fastapi import APIRouter
from app.screenshot.service.screenshot_service import capture_screenshot

router = APIRouter(prefix="/screenshot", tags=["Screenshot"])


@router.get("")
async def get_screenshot(url: str):
    image_base64 = await capture_screenshot(url)
    return {"image": f"data:image/png;base64,{image_base64}"}
