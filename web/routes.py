from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.auth import (
    AuthError,
    DuplicateUserError,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    authenticate_user,
    create_session_token,
    create_user,
    get_current_user,
)
from api.credentials import has_service_credentials


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
router = APIRouter()
STATIC_VERSION = "20260611-11"


def template_context(request: Request, **context: object) -> dict[str, object]:
    current_user = None
    try:
        current_user = get_current_user(request)
    except Exception:
        current_user = None

    return {
        "request": request,
        "current_user": current_user,
        "static_version": STATIC_VERSION,
        **context,
    }


def redirect_with_session(url: str, user_id: str) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user_id),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/yandex", status_code=303)


@router.get("/yandex", response_class=HTMLResponse, include_in_schema=False)
async def yandex_page(request: Request) -> HTMLResponse:
    current_user = get_current_user(request)
    status = None
    if current_user is not None and has_service_credentials(
        current_user.id,
        "yandex_music",
    ):
        status = {
            "kind": "success",
            "message": "Токен Яндекс Музыки сохранен в аккаунте.",
        }

    return templates.TemplateResponse(
        request,
        "yandex.html",
        template_context(
            request,
            active_source="yandex",
            current_user=current_user,
            status=status,
        ),
    )


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        template_context(
            request,
            active_account_page="login",
            profile_menu_open=True,
        ),
    )


@router.post("/login", include_in_schema=False)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    try:
        user = authenticate_user(username, password)
        return redirect_with_session("/yandex", user.id)
    except AuthError as error:
        return templates.TemplateResponse(
            request,
            "login.html",
            template_context(
                request,
                active_account_page="login",
                profile_menu_open=True,
                error_message=str(error),
                username=username,
            ),
            status_code=400,
        )


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "register.html",
        template_context(
            request,
            active_account_page="register",
            profile_menu_open=True,
        ),
    )


@router.post("/register", include_in_schema=False)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    try:
        user = create_user(username, password)
        return redirect_with_session("/yandex", user.id)
    except (AuthError, DuplicateUserError) as error:
        return templates.TemplateResponse(
            request,
            "register.html",
            template_context(
                request,
                active_account_page="register",
                profile_menu_open=True,
                error_message=str(error),
                username=username,
            ),
            status_code=400,
        )


@router.post("/logout", include_in_schema=False)
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/yandex", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(request: Request) -> HTMLResponse:
    current_user = get_current_user(request)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "settings.html",
        template_context(
            request,
            active_account_page="settings",
            active_source=None,
            profile_menu_open=True,
        ),
    )
