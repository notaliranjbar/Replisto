"""The page's insights, the findings drawn from them and the content assistant."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import LLM, CurrentShop, DbSession, Instagram
from app.core.i18n import localize
from app.models import ContentReport, InstagramAccount
from app.services import insights
from app.services.instagram import SCOPE_INSIGHTS

router = APIRouter(prefix="/insights", tags=["insights"])

Format = Literal["reel", "post", "carousel", "story"]


class ProfileOut(BaseModel):
    username: str
    name: str = ""
    picture_url: str | None = None
    followers: int = 0
    follows: int = 0
    posts: int = 0


class MediaOut(BaseModel):
    id: str
    caption: str
    format: Literal["reel", "carousel", "video", "photo"]
    permalink: str | None
    preview_url: str | None
    timestamp: str | None
    likes: int
    comments: int
    reach: int | None = None
    views: int | None = None
    saves: int | None = None
    shares: int | None = None
    engagement: int
    # Engagement as a share of reach, in percent.
    rate: float | None = None


class SeriesPoint(BaseModel):
    date: str
    value: int


class FormatStat(BaseModel):
    format: str
    posts: int
    avg_engagement: float
    avg_reach: float | None
    avg_rate: float | None


class DayStat(BaseModel):
    day: int  # 0 = Monday
    posts: int
    avg_engagement: float


class HourStat(BaseModel):
    from_hour: int  # start of a 3-hour block, local time
    posts: int
    avg_engagement: float


class HashtagStat(BaseModel):
    tag: str
    posts: int
    avg_engagement: float


class AnalysisOut(BaseModel):
    posts_analyzed: int
    posts_last_30_days: int
    posts_per_week: float
    avg_engagement: float | None
    avg_engagement_rate: float | None
    formats: list[FormatStat]
    weekdays: list[DayStat]
    best_days: list[int]
    hours: list[HourStat]
    best_hours: list[int]
    hashtags: list[HashtagStat]
    top_posts: list[str]
    weakest_posts: list[str]
    # Change of each weekly total against the week before, in percent.
    week_change: dict[str, float | None]
    new_followers_30_days: int


class Recommendation(BaseModel):
    title: str
    detail: str


class Idea(BaseModel):
    format: Format
    title: str
    hook: str
    caption: str
    when: str = ""


class PlanDay(BaseModel):
    day: str
    format: Format
    idea: str


class ReportOut(BaseModel):
    created_at: datetime
    summary: str
    strengths: list[str] = []
    improvements: list[str] = []
    recommendations: list[Recommendation] = []
    ideas: list[Idea] = []
    weekly_plan: list[PlanDay] = []


class InsightsOut(BaseModel):
    # Instagram connected with permission to read insights.
    available: bool
    needs_reconnect: bool
    fetched_at: datetime | None
    error: str | None
    profile: ProfileOut | None
    week: dict[str, int]
    previous_week: dict[str, int]
    reach_series: list[SeriesPoint]
    follower_series: list[SeriesPoint]
    media: list[MediaOut]
    analysis: AnalysisOut | None
    report: ReportOut | None


class AssistantTurn(BaseModel):
    role: Literal["owner", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class AssistantIn(BaseModel):
    messages: list[AssistantTurn] = Field(min_length=1, max_length=24)


class AssistantOut(BaseModel):
    reply: str


def _report(report: ContentReport | None) -> ReportOut | None:
    if report is None:
        return None
    data = dict(report.data or {})
    try:
        return ReportOut(created_at=report.created_at, **_clean(data))
    except ValueError:
        return None


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Drop ideas/plan rows the model wrote in a shape we can't show."""
    allowed = {"reel", "post", "carousel", "story"}
    data["ideas"] = [
        i for i in data.get("ideas") or [] if isinstance(i, dict) and i.get("format") in allowed
    ]
    data["weekly_plan"] = [
        p
        for p in data.get("weekly_plan") or []
        if isinstance(p, dict) and p.get("format") in allowed
    ]
    return {k: v for k, v in data.items() if k in ReportOut.model_fields}


async def _account(db: DbSession, shop_id: Any) -> InstagramAccount | None:
    return await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop_id))


async def _build(db: DbSession, shop: CurrentShop) -> InsightsOut:
    account = await _account(db, shop.id)
    connected = account is not None and account.is_active
    row = await insights.get_row(db, shop.id)
    data = row.data if row and row.data else {}
    media: list[MediaOut] = []
    for m in data.get("media") or []:
        if not m.get("id"):
            continue
        reach, eng = m.get("reach"), insights.engagement(m)
        media.append(
            MediaOut(
                id=m["id"],
                caption=m.get("caption") or "",
                format=insights.media_format(m),  # type: ignore[arg-type]
                permalink=m.get("permalink"),
                preview_url=m.get("preview_url"),
                timestamp=m.get("timestamp"),
                likes=int(m.get("likes") or 0),
                comments=int(m.get("comments") or 0),
                reach=reach,
                views=m.get("views"),
                saves=m.get("saves"),
                shares=m.get("shares"),
                engagement=eng,
                rate=round(eng / reach * 100, 2) if reach else None,
            )
        )
    series = data.get("series") or {}
    return InsightsOut(
        available=connected and account.has_scope(SCOPE_INSIGHTS),
        needs_reconnect=connected and not account.has_scope(SCOPE_INSIGHTS),
        fetched_at=row.fetched_at if row else None,
        error=localize(row.error) if row else None,
        profile=ProfileOut(**data["profile"]) if data.get("profile") else None,
        week=data.get("week") or {},
        previous_week=data.get("previous_week") or {},
        reach_series=[SeriesPoint(**p) for p in series.get("reach") or []],
        follower_series=[SeriesPoint(**p) for p in series.get("follower_count") or []],
        media=media,
        analysis=AnalysisOut(**insights.analyze(data, shop.timezone)) if data else None,
        report=_report(await insights.latest_report(db, shop.id)),
    )


@router.get("", response_model=InsightsOut)
async def get_insights(shop: CurrentShop, db: DbSession) -> InsightsOut:
    return await _build(db, shop)


@router.post("/refresh", response_model=InsightsOut)
async def refresh_insights(shop: CurrentShop, db: DbSession, instagram: Instagram) -> InsightsOut:
    """Read the page's numbers from Instagram now (they're also refreshed every day)."""
    account = await _account(db, shop.id)
    if account is None or not account.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connect your Instagram account first.")
    if not account.has_scope(SCOPE_INSIGHTS):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Reconnect Instagram and allow access to insights."
        )
    try:
        await insights.refresh(db, account, instagram)
    except insights.InsightsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, localize(str(exc))) from None
    return await _build(db, shop)


@router.post("/report", response_model=ReportOut)
async def make_report(shop: CurrentShop, db: DbSession, llm: LLM) -> ReportOut:
    """The content assistant analyses the page and writes ideas and a weekly plan."""
    try:
        report = await insights.make_report(db, shop, llm)
    except insights.InsightsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, localize(str(exc))) from None
    out = _report(report)
    if out is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The content assistant is busy. Please try again in a moment.",
        )
    return out


@router.post("/assistant", response_model=AssistantOut)
async def ask_assistant(
    body: AssistantIn, shop: CurrentShop, db: DbSession, llm: LLM
) -> AssistantOut:
    """A question to the content assistant (captions, ideas, what the numbers mean)."""
    if body.messages[-1].role != "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The last message must be yours.")
    try:
        reply = await insights.ask(db, shop, llm, [(m.role, m.text) for m in body.messages])
    except insights.InsightsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, localize(str(exc))) from None
    return AssistantOut(reply=reply)
