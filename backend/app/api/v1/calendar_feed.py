from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.services.calendar_feed import CalendarFeedService

router = APIRouter(tags=["calendar"])


class FeedOut(BaseModel):
    url: str
    webcal_url: str


def _urls(public_base_url: str, token: str) -> FeedOut:
    """ICS по PUBLIC_BASE_URL: Google забирает фид со своего сервера и не видит localhost из запроса."""
    base = (public_base_url or "").strip().rstrip("/") or "http://localhost:8000"
    url = f"{base}/api/v1/calendar/{token}.ics"
    parts = urlsplit(url)
    webcal_url = urlunsplit(("webcal", parts.netloc, parts.path, "", ""))
    return FeedOut(url=url, webcal_url=webcal_url)


@router.get(
    "/calendar/feed",
    response_model=FeedOut,
    summary="Личная ссылка на календарь (ICS) для Google/Apple Календаря",
    responses=responses(401),
)
def get_feed(user: UserDep, c: ContainerDep, db: DbDep) -> FeedOut:
    return _urls(c.settings.public_base_url, CalendarFeedService(db, c.clock).token_for(user))


@router.post(
    "/calendar/feed/rotate",
    response_model=FeedOut,
    summary="Сменить ссылку на календарь (старая перестанет работать)",
    responses=responses(401),
)
def rotate_feed(user: UserDep, c: ContainerDep, db: DbDep) -> FeedOut:
    return _urls(c.settings.public_base_url, CalendarFeedService(db, c.clock).token_for(user, rotate=True))


@router.get(
    "/calendar/{token}.ics",
    summary="Календарь платежей в формате iCalendar (доступ по секретной ссылке)",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, **responses(404)},
)
def ics(token: str, c: ContainerDep, db: DbDep) -> Response:
    svc = CalendarFeedService(db, c.clock)
    owner = svc.user_by_token(token)
    return Response(
        content=svc.render(owner, c.settings.app_timezone),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300", "Content-Disposition": 'inline; filename="invoice-keeper.ics"'},
    )
