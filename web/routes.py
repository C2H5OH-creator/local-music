from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
router = APIRouter()


@router.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/yandex", status_code=303)


@router.get("/yandex", response_class=HTMLResponse, include_in_schema=False)
async def yandex_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "yandex.html",
        {
            "active_source": "yandex",
            "status": None,
            "static_version": "20260611-2",
        },
    )
