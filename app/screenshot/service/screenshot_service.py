import base64
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from app.core.settings import settings


def _capture_screenshot_sync(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        try:
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            # Adicionar headers realistas
            page.set_extra_http_headers({
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Referer": "https://www.google.com/",
            })

            page.set_viewport_size({
                "width": settings.BROWSER_VIEWPORT_WIDTH,
                "height": settings.BROWSER_VIEWPORT_HEIGHT,
            })

            try:
                page.goto(url, wait_until="networkidle", timeout=settings.BROWSER_TIMEOUT)
            except PlaywrightTimeoutError:
                raise HTTPException(status_code=408, detail="TIMEOUT")

            # Pequeno delay antes de capturar
            time.sleep(1)

            screenshot_bytes = page.screenshot(full_page=False)
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
            browser.close()


async def capture_screenshot(url: str) -> str:
    return await run_in_threadpool(_capture_screenshot_sync, url)
