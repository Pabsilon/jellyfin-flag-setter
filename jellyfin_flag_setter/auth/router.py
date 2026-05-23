from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from jellyfin_flag_setter.auth.db import get_session
from jellyfin_flag_setter.auth.dependencies import get_current_user
from jellyfin_flag_setter.auth.models import User
from jellyfin_flag_setter.auth.security import hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login")
async def login_page(request: Request, session: Session = Depends(get_session)):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=401,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/setup")
async def setup_page(request: Request, session: Session = Depends(get_session)):
    if session.exec(select(User)).first():
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@router.post("/setup")
async def setup(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    password_confirm: str = Form(),
    session: Session = Depends(get_session),
):
    if session.exec(select(User)).first():
        return RedirectResponse("/login", status_code=302)
    if password != password_confirm:
        return templates.TemplateResponse(
            request, "setup.html", {"error": "Passwords do not match"}, status_code=400
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Password must be at least 8 characters"},
            status_code=400,
        )
    user = User(username=username, hashed_password=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.get("/settings")
async def settings_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    jobs = request.app.state.job_manager.list_statuses()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "user": current_user,
            "success": None,
            "error": None,
            "jobs": jobs,
            "libraries": request.app.state.libraries,
            "language_mappings": request.app.state.language_mappings,
        },
    )


@router.post("/settings/password")
async def change_password(
    request: Request,
    current_password: str = Form(),
    new_password: str = Form(),
    new_password_confirm: str = Form(),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    jobs = request.app.state.job_manager.list_statuses()
    lang_mappings = request.app.state.language_mappings

    def _render(error=None, success=None, status_code=200):
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "user": current_user,
                "error": error,
                "success": success,
                "jobs": jobs,
                "libraries": request.app.state.libraries,
                "language_mappings": lang_mappings,
            },
            status_code=status_code,
        )

    if not verify_password(current_password, current_user.hashed_password):
        return _render(error="Current password is incorrect", status_code=400)
    if new_password != new_password_confirm:
        return _render(error="New passwords do not match", status_code=400)
    if len(new_password) < 8:
        return _render(error="Password must be at least 8 characters", status_code=400)
    current_user.hashed_password = hash_password(new_password)
    session.add(current_user)
    session.commit()
    return _render(success="Password updated successfully")
