from fastapi import Depends, Request
from sqlmodel import Session, select

from jellyfin_flag_setter.auth.db import get_session
from jellyfin_flag_setter.auth.models import ServerConfig, User


class RequiresLogin(Exception):
    pass


class RequiresSetup(Exception):
    pass


class RequiresJellyfinSetup(Exception):
    pass


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        if not session.exec(select(User)).first():
            raise RequiresSetup()
        raise RequiresLogin()
    user = session.get(User, user_id)
    if not user:
        request.session.clear()
        raise RequiresLogin()
    if not session.exec(select(ServerConfig)).first():
        raise RequiresJellyfinSetup()
    return user
