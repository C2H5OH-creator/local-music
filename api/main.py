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

from api.auth import CurrentUser, get_current_user
from api.credentials import (
    get_service_credentials,
    save_service_credentials,
)
from api.settings import get_settings
from api.threading import run_blocking_yandex_call
from connectors.yandex_links import extract_album_id
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


def get_yandex_music_provider_for_user(
    current_user: CurrentUser | None,
):
    if current_user is not None:
        credentials = get_service_credentials(current_user.id, "yandex_music")
        if credentials and credentials.get("token"):
            return get_yandex_music_provider(credentials["token"])

    return get_yandex_music_provider()


def save_yandex_music_token_for_user(
    current_user: CurrentUser | None,
    token: str,
) -> None:
    token = token.strip()
    if not token:
        raise ValueError("Yandex Music token is empty")

    if current_user is not None:
        save_service_credentials(
            user_id=current_user.id,
            service="yandex_music",
            auth_type="token",
            data={"token": token},
        )
    else:
        set_yandex_music_token(token)


def resolve_server_music_path(base_path: Path, music_path: str) -> Path:
    relative_path = Path(music_path.strip() or ".")
    if relative_path.is_absolute() or any(part == ".." for part in relative_path.parts):
        raise ValueError("Music path must be relative")

    resolved_base_path = base_path.resolve()
    target_path = (resolved_base_path / relative_path).resolve()
    if target_path != resolved_base_path and resolved_base_path not in target_path.parents:
        raise ValueError("Music path is outside server music directory")

    return target_path


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
async def authorize_yandex_music(
    request: Request,
    payload: YandexAuthRequest,
) -> ApiResponse:
    try:
        current_user = await run_blocking_yandex_call(get_current_user, request)
        await run_blocking_yandex_call(
            save_yandex_music_token_for_user,
            current_user,
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
        current_user = await run_blocking_yandex_call(get_current_user, request)
        await run_blocking_yandex_call(
            save_yandex_music_token_for_user,
            current_user,
            token,
        )
        message = (
            "Токен сохранен в аккаунте. Можно загружать информацию об альбомах."
            if current_user is not None
            else "Токен сохранен до перезапуска сервера. Войди в аккаунт, чтобы сохранить его постоянно."
        )
        return templates.TemplateResponse(
            request,
            "partials/status.html",
            {
                "kind": "success",
                "message": message,
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
async def get_yandex_track_info(request: Request, track_id: str) -> ApiResponse:
    try:
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
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
        album_id = extract_album_id(album_id)
        settings = get_settings()
        started_at = time.monotonic()
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
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
    request: Request,
    album_id: str,
    albumQuality: str = "normal",
    coverQuality: str = "400",
    coverMode: str = "embedded",
    quality: str | None = None,
) -> FileResponse:
    try:
        album_id = extract_album_id(album_id)
        settings = get_settings()
        track_quality = quality or albumQuality
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
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
    request: Request,
    album_id: str,
    albumQuality: str = "normal",
    coverQuality: str = "400",
    coverMode: str = "embedded",
    quality: str | None = None,
) -> StreamingResponse:
    try:
        album_id = extract_album_id(album_id)
        track_quality = quality or albumQuality
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
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


@app.post(
    "/api/yandex/albums/download/server",
    response_model=ApiResponse,
    tags=["yandex-music"],
)
async def download_yandex_album_to_server(
    request: Request,
    album_id: str = Form(...),
    albumQuality: str = Form("normal"),
    coverQuality: str = Form("400"),
    coverMode: str = Form("embedded"),
    musicPath: str = Form(""),
) -> ApiResponse:
    try:
        album_id = extract_album_id(album_id)
        settings = get_settings()
        target_path = resolve_server_music_path(
            settings.server_music_base_path,
            musicPath,
        )
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
        downloaded = await run_blocking_yandex_call(
            provider.download_album_to_directory,
            album_id,
            albumQuality,
            target_path,
            coverQuality,
            coverMode,
            timeout=settings.yandex_music_album_request_timeout,
        )
        return ok_response(
            {
                "path": str(downloaded.path),
                "track_count": downloaded.track_count,
            }
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
async def get_yandex_album_info(request: Request, album_id: str) -> ApiResponse:
    try:
        settings = get_settings()
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
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
async def get_yandex_track_audio(request: Request, track_id: str) -> FileResponse:
    try:
        current_user = await run_blocking_yandex_call(get_current_user, request)
        provider = await run_blocking_yandex_call(
            get_yandex_music_provider_for_user,
            current_user,
        )
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
