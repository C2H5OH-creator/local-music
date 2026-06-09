from pathlib import Path
import asyncio
import urllib.parse
import urllib.request

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from api.threading import run_blocking_yandex_call
from api.yandex_service import get_yandex_music_provider, set_yandex_music_token


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
router = APIRouter()


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def error_message(error: Exception) -> str:
    if isinstance(error, TimeoutError | asyncio.TimeoutError):
        return "Yandex Music request timed out"
    return str(error)


def download_cover(cover_uri: str, size: str) -> tuple[bytes, str]:
    if not size.replace("x", "").isdigit():
        raise ValueError("Unsupported cover size")

    cover_url = cover_uri
    if not cover_url.startswith(("http://", "https://")):
        cover_url = f"https://{cover_url}"

    parsed = urllib.parse.urlparse(cover_url)
    if parsed.hostname != "avatars.yandex.net":
        raise ValueError("Unsupported cover host")

    cover_url = cover_url.replace("%%", size)
    request = urllib.request.Request(
        cover_url,
        headers={
            "User-Agent": "local-music/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        content_type = response.headers.get("content-type", "image/jpeg")
        return response.read(), content_type


@router.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/yandex", status_code=303)


@router.get("/yandex", response_class=HTMLResponse, include_in_schema=False)
async def yandex_page(request: Request) -> HTMLResponse:
    auth_status = request.query_params.get("auth")
    return templates.TemplateResponse(
        request,
        "yandex.html",
        {
            "active_source": "yandex",
            "status": {
                "kind": "success",
                "message": "Токен сохранен. Можно загружать информацию об альбомах.",
            }
            if auth_status == "success"
            else None,
        },
    )


@router.get("/web/yandex/cover", include_in_schema=False, name="yandex_cover")
async def yandex_cover(uri: str, size: str = "400x400") -> Response:
    try:
        content, content_type = await run_blocking_yandex_call(download_cover, uri, size)
        return Response(content=content, media_type=content_type)
    except Exception:
        return Response(status_code=404)


@router.post("/web/yandex/auth", response_class=HTMLResponse, include_in_schema=False)
async def authorize_yandex(request: Request, token: str = Form(...)) -> HTMLResponse:
    try:
        await run_blocking_yandex_call(set_yandex_music_token, token)
        if not is_htmx(request):
            return RedirectResponse(url="/yandex?auth=success", status_code=303)

        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "success",
                "message": "Токен сохранен. Можно загружать информацию об альбомах.",
            },
        )
    except Exception as error:
        if not is_htmx(request):
            return templates.TemplateResponse(
                request,
                "yandex.html",
                {
                    "active_source": "yandex",
                    "status": {
                        "kind": "error",
                        "message": error_message(error),
                    },
                },
            )

        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "error",
                "message": error_message(error),
            },
        )


@router.post("/web/yandex/albums", response_class=HTMLResponse, include_in_schema=False)
async def load_yandex_album(
    request: Request,
    album_id: str = Form(...),
) -> HTMLResponse:
    try:
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        album_info = await run_blocking_yandex_call(provider.get_album_info, album_id)
        if not is_htmx(request):
            return templates.TemplateResponse(
                request,
                "yandex.html",
                {
                    "active_source": "yandex",
                    "album": album_info,
                },
            )

        return templates.TemplateResponse(
            request,
            "partials/album_info.html",
            {
                "album": album_info,
            },
        )

    except Exception as error:
        if not is_htmx(request):
            return templates.TemplateResponse(
                request,
                "yandex.html",
                {
                    "active_source": "yandex",
                    "status": {
                        "kind": "error",
                        "message": error_message(error),
                    },
                },
            )

        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "error",
                "message": error_message(error),
            },
        )


@router.get("/web/yandex/albums/download", include_in_schema=False)
async def download_yandex_album(album_id: str, quality: str = "normal") -> FileResponse:
    provider = await run_blocking_yandex_call(get_yandex_music_provider)
    archive = await asyncio.to_thread(
        provider.download_album_archive,
        album_id,
        quality,
    )
    return FileResponse(
        archive.path,
        media_type="application/zip",
        filename=archive.filename,
    )
