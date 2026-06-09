import asyncio
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, SecretStr

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
    "/api/yandex/albums/{album_id}",
    response_model=ApiResponse,
    tags=["yandex-music"],
)
async def get_yandex_album_info(album_id: str) -> ApiResponse:
    try:
        provider = await run_blocking_yandex_call(get_yandex_music_provider)
        data = await run_blocking_yandex_call(provider.get_album_info, album_id)
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
