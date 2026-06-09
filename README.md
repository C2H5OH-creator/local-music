# local-music

## FastAPI

The API exposes Yandex Music metadata endpoints and Swagger docs.

Environment:

```env
TOKEN=...
```

`TOKEN` can also be passed at runtime through the authorization endpoint.

Install dependencies and start the service:

```bash
uv sync
uv run uvicorn api.main:app --reload
```

Or start with Docker Compose:

```bash
docker compose up --build
```

Swagger UI:

```bash
http://127.0.0.1:8000/docs
```

Web UI:

```bash
http://127.0.0.1:8000/yandex
```

Initial endpoints:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Service healthcheck |
| `GET` | `/yandex` | Yandex Music web page |
| `POST` | `/api/yandex/auth` | Initialize Yandex Music provider with token |
| `GET` | `/api/yandex/tracks/{track_id}` | Yandex Music track info |
| `GET` | `/api/yandex/tracks/{track_id}/audio` | Low-traffic cached audio preview |
| `GET` | `/api/yandex/albums/{album_id}` | Yandex Music album info with tracks |
| `GET` | `/web/yandex/albums/download?album_id=...&quality=normal` | Download album archive through browser |

Authorize Yandex Music:

```bash
curl -X POST http://127.0.0.1:8000/api/yandex/auth \
  -H "Content-Type: application/json" \
  -d '{"token": "..."}'
```

Responses use a common envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Audio preview files are cached in:

```bash
storage/cache/yandex/tracks/
```

Native FLAC downloads require `ffmpeg` for remuxing Yandex Music `flac-mp4`
responses to `.flac` without re-encoding. The Docker image installs `ffmpeg`
automatically.
