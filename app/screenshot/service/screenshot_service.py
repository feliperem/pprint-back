import base64
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from fastapi import HTTPException
from app.core.settings import settings


async def capture_screenshot(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()

            await page.set_viewport_size({
                "width": settings.BROWSER_VIEWPORT_WIDTH,
                "height": settings.BROWSER_VIEWPORT_HEIGHT,
            })

            try:
                await page.goto(url, wait_until="networkidle", timeout=settings.BROWSER_TIMEOUT)
            except PlaywrightTimeoutError:
                raise HTTPException(status_code=408, detail="TIMEOUT")

            screenshot_bytes = await page.screenshot(full_page=False)
            return base64.b64encode(screenshot_bytes).decode("utf-8")

        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg:
                raise HTTPException(status_code=408, detail="TIMEOUT")
            if any(k in error_msg for k in [
                "net::err_name_not_resolved",
                "net::err_connection_refused",
                "net::err_connection_timed_out",
                "net::err_address_unreachable",
                "err_failed",
            ]):
                raise HTTPException(status_code=503, detail="UNREACHABLE")
            raise HTTPException(status_code=400, detail="UNKNOWN")
        finally:
            await browser.close()
