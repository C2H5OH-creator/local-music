import asyncio
import logging
import time
import urllib.parse
import urllib.request
from typing import Any
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, SecretStr

from api.settings import get_settings
from api.threading import run_blocking_yandex_call
from api.yandex_service import get_yandex_music_provider, set_yandex_music_token


class ErrorInfo(BaseModel):
    type: str
    message: str


class ApiResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ErrorInfo | None = None


class YandexAuthRequest(BaseModel):
    token: SecretStr


app = FastAPI(
    title="Local Music API",
    version="0.1.0",
    description="API for fetching music metadata from connected providers.",
)

STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = logging.getLogger("local-music.api")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def ok_response(data: dict[str, Any]) -> ApiResponse:
    return ApiResponse(ok=True, data=data)


def raise_provider_error(error: Exception) -> None:
    if isinstance(error, ValueError):
        status_code = 404
    elif (
        isinstance(error, RuntimeError)
        and str(error) == "Yandex Music token is not configured"
    ):
        status_code = 503
    elif isinstance(error, TimeoutError | asyncio.TimeoutError):
        status_code = 504
        message = "Yandex Music request timed out"
    else:
        status_code = 500
        message = str(error)

    if "message" not in locals():
        message = str(error)

    raise HTTPException(
        status_code=status_code,
        detail={
            "type": type(error).__name__,
            "message": message,
        },
    )


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


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/yandex/auth",
    response_model=ApiResponse,
    tags=["yandex-music"],
)
async def authorize_yandex_music(payload: YandexAuthRequest) -> ApiResponse:
    try:
        await run_blocking_yandex_call(
            set_yandex_music_token,
            payload.token.get_secret_value(),
        )
        return ok_response({"authorized": True})
    except Exception as error:
        raise_provider_error(error)


@app.post(
    "/api/yandex/auth/form",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def authorize_yandex_music_form(
    request: Request,
    token: str = Form(...),
) -> HTMLResponse:
    try:
        await run_blocking_yandex_call(set_yandex_music_token, token)
        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "success",
                "message": "Токен сохранен. Можно загружать информацию об альбомах.",
            },
        )
    except Exception as error:
        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "error",
                "message": error_message(error),
            },
        )


@app.get(
    "/api/yandex/tracks/{track_id}",
    response_model=ApiResponse,
    tags=["yandex-music"],
)
async def get_yandex_track_info(track_id: str) -> ApiResponse:
    try:
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        data = await run_blocking_yandex_call(provider.get_track_info, track_id)
        return ok_response(data)
    except Exception as error:
        raise_provider_error(error)


@app.get(
    "/api/yandex/albums/fragment",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def get_yandex_album_fragment(
    request: Request,
    album_id: str,
) -> HTMLResponse:
    try:
        settings = get_settings()
        started_at = time.monotonic()
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        album_info = await run_blocking_yandex_call(
            provider.get_album_info,
            album_id,
            timeout=settings.yandex_music_album_request_timeout,
        )
        logger.info(
            "Loaded Yandex album %s in %.2fs",
            album_id,
            time.monotonic() - started_at,
        )
        return templates.TemplateResponse(
            request,
            "partials/album_info.html",
            {
                "album": album_info,
            },
        )
    except Exception as error:
        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "error",
                "message": error_message(error),
            },
        )


@app.get("/api/yandex/cover", include_in_schema=False, name="yandex_cover")
async def get_yandex_cover(uri: str, size: str = "400x400") -> Response:
    try:
        content, content_type = await run_blocking_yandex_call(download_cover, uri, size)
        return Response(content=content, media_type=content_type)
    except Exception:
        return Response(status_code=404)


@app.get(
    "/api/yandex/albums/download",
    tags=["yandex-music"],
)
async def download_yandex_album(
    album_id: str,
    albumQuality: str = "normal",
    coverQuality: str = "400",
    coverMode: str = "embedded",
    quality: str | None = None,
) -> FileResponse:
    try:
        settings = get_settings()
        track_quality = quality or albumQuality
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        archive = await run_blocking_yandex_call(
            provider.download_album_archive,
            album_id,
            track_quality,
            coverQuality,
            coverMode,
            timeout=settings.yandex_music_album_request_timeout,
        )
        return FileResponse(
            archive.path,
            media_type="application/zip",
            filename=archive.filename,
        )
    except Exception as error:
        raise_provider_error(error)


@app.get(
    "/api/yandex/albums/download/stream",
    tags=["yandex-music"],
)
async def stream_yandex_album_download(
    album_id: str,
    albumQuality: str = "normal",
    coverQuality: str = "400",
    coverMode: str = "embedded",
    quality: str | None = None,
) -> StreamingResponse:
    try:
        track_quality = quality or albumQuality
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        archive = await run_blocking_yandex_call(
            provider.stream_album_archive,
            album_id,
            track_quality,
            coverQuality,
            coverMode,
        )
        quoted_filename = urllib.parse.quote(archive.filename)
        return StreamingResponse(
            archive.chunks,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quoted_filename}"
                ),
            },
        )
    except Exception as error:
        raise_provider_error(error)


@app.get("/web/yandex/albums/download", include_in_schema=False)
async def redirect_legacy_yandex_album_download(
    album_id: str,
    quality: str = "normal",
    albumQuality: str | None = None,
    coverQuality: str = "400",
    coverMode: str = "embedded",
) -> RedirectResponse:
    params = urllib.parse.urlencode(
        {
            "album_id": album_id,
            "albumQuality": albumQuality or quality,
            "coverQuality": coverQuality,
            "coverMode": coverMode,
        }
    )
    return RedirectResponse(
        url=f"/api/yandex/albums/download/stream?{params}",
        status_code=307,
    )


@app.get(
    "/api/yandex/albums/{album_id}",
    response_model=ApiResponse,
    tags=["yandex-music"],
)
async def get_yandex_album_info(album_id: str) -> ApiResponse:
    try:
        settings = get_settings()
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        data = await run_blocking_yandex_call(
            provider.get_album_info,
            album_id,
            timeout=settings.yandex_music_album_request_timeout,
        )
        return ok_response(data)
    except Exception as error:
        raise_provider_error(error)


@app.get(
    "/api/yandex/tracks/{track_id}/audio",
    tags=["yandex-music"],
)
async def get_yandex_track_audio(track_id: str) -> FileResponse:
    try:
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        cached_audio = await run_blocking_yandex_call(
            provider.get_track_audio_preview,
            track_id,
        )
        return FileResponse(
            cached_audio.path,
            media_type=cached_audio.media_type,
            filename=cached_audio.path.name,
        )
    except Exception as error:
        raise_provider_error(error)


from web.routes import router as web_router  # noqa: E402


app.include_router(web_router)
