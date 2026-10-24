from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import ContainerDep, DbDep, UserDep
from app.api.errors import responses
from app.services.calendar_feed import CalendarFeedService

router = APIRouter(tags=["calendar"])


class FeedOut(BaseModel):
    url: str
    webcal_url: str


def _urls(request: Request, token: str) -> FeedOut:
    base = str(request.base_url).rstrip("/")
    url = f"{base}/api/v1/calendar/{token}.ics"
    return FeedOut(url=url, webcal_url="webcal://" + url.split("://", 1)[1])


@router.get(
    "/calendar/feed",
    response_model=FeedOut,
    summary="Личная ссылка на календарь (ICS) для Google/Apple Календаря",
    responses=responses(401),
)
def get_feed(request: Request, user: UserDep, c: ContainerDep, db: DbDep) -> FeedOut:
    return _urls(request, CalendarFeedService(db, c.clock).token_for(user))


@router.post(
    "/calendar/feed/rotate",
    response_model=FeedOut,
    summary="Сменить ссылку на календарь (старая перестанет работать)",
    responses=responses(401),
)
def rotate_feed(request: Request, user: UserDep, c: ContainerDep, db: DbDep) -> FeedOut:
    return _urls(request, CalendarFeedService(db, c.clock).token_for(user, rotate=True))


@router.get(
    "/calendar/{token}.ics",
    summary="Календарь платежей в формате iCalendar (доступ по секретной ссылке)",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, **responses(404)},
)
def ics(token: str, c: ContainerDep, db: DbDep) -> Response:
    svc = CalendarFeedService(db, c.clock)
    svc.user_by_token(token)
    return Response(
        content=svc.render(c.settings.app_timezone),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300", "Content-Disposition": 'inline; filename="invoice-keeper.ics"'},
    )
