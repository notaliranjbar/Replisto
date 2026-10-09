"""The page's numbers from Instagram, what they say, and the content assistant.

- `refresh` reads the profile, this week's and last week's totals, 30-day daily series and
  the recent posts with their own numbers, and keeps them in one row per shop (refreshed
  daily, or when the owner asks).
- `analyze` turns that into plain findings: which formats work, the best days and hours
  (in the owner's time zone), hashtags that pull, how often the page posts.
- The content assistant (an AI) reads those findings with the shop's own information and
  writes a report (what works, what to improve, post and story ideas with captions, a
  weekly plan) and answers the owner's questions. Both are charged to the wallet.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.core.timeutil import utcnow
from app.models import (
    ContentReport,
    InstagramAccount,
    InstagramInsights,
    KnowledgeEntry,
    KnowledgeSection,
    Product,
    Shop,
)
from app.services import billing
from app.services.instagram import InstagramClient, InstagramError
from app.services.llm import LLMClient, LLMError, Usage

logger = logging.getLogger(__name__)

ACCOUNT_METRICS = [
    "reach",
    "views",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "shares",
    "saves",
    "replies",
    "follows_and_unfollows",
    "profile_links_taps",
]
MEDIA_METRICS = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions"]
# Posts whose own numbers are read on each refresh (one call each).
MEDIA_WITH_INSIGHTS = 24
# Asking again within this window returns what we already have.
REFRESH_COOLDOWN = timedelta(minutes=10)
KEEP_REPORTS = 5

_HASHTAG = re.compile(r"#(\w+)", re.UNICODE)
_INVALID_METRIC = 100


class InsightsError(Exception):
    """A problem the owner should see."""


# ---------------------------------------------------------------------------- reading


async def get_row(db: AsyncSession, shop_id: Any) -> InstagramInsights | None:
    return await db.scalar(select(InstagramInsights).where(InstagramInsights.shop_id == shop_id))


async def refresh(
    db: AsyncSession, account: InstagramAccount, instagram: InstagramClient, *, force: bool = False
) -> InstagramInsights:
    row = await get_row(db, account.shop_id)
    if row is None:
        row = InstagramInsights(shop_id=account.shop_id, data={})
        db.add(row)
    elif not force and row.fetched_at and utcnow() - row.fetched_at < REFRESH_COOLDOWN:
        return row
    if get_settings().instagram_dry_run:
        # Nothing to read without Instagram: keep the numbers we have (the demo shop's).
        if row.data:
            return row
        raise InsightsError(
            "Couldn't read your page's numbers from Instagram. Please try again in a moment."
        )
    token = decrypt_secret(account.access_token_encrypted)
    try:
        profile = await instagram.get_account(token)
    except InstagramError as exc:
        logger.warning("insights: profile read failed for shop %s: %s", account.shop_id, exc)
        row.error = "Couldn't read the page's numbers from Instagram"
        await db.commit()
        raise InsightsError(
            "Couldn't read your page's numbers from Instagram. Please try again in a moment."
        ) from None

    now = utcnow().replace(minute=0, second=0, microsecond=0)
    ig_id = account.ig_user_id
    week = await _totals(instagram, token, ig_id, now - timedelta(days=7), now)
    previous = await _totals(
        instagram, token, ig_id, now - timedelta(days=14), now - timedelta(days=7)
    )
    series: dict[str, list[dict[str, Any]]] = {}
    for metric in ("reach", "follower_count"):
        try:
            points = await instagram.account_series(
                token, ig_id, metric, now - timedelta(days=30), now
            )
        except InstagramError as exc:
            logger.info("insights: %s series unavailable: %s", metric, exc)
            points = []
        series[metric] = [{"date": day, "value": value} for day, value in points]

    try:
        media = await instagram.recent_media(token, 30)
    except InstagramError as exc:
        logger.info("insights: media list unavailable: %s", exc)
        media = []
    items: list[dict[str, Any]] = []
    for index, m in enumerate(media):
        item: dict[str, Any] = {
            "id": str(m.get("id") or ""),
            "caption": (m.get("caption") or "")[:600],
            "media_type": m.get("media_type") or "",
            "product_type": m.get("media_product_type") or "",
            "permalink": m.get("permalink"),
            "preview_url": m.get("thumbnail_url") or m.get("media_url"),
            "timestamp": m.get("timestamp"),
            "likes": int(m.get("like_count") or 0),
            "comments": int(m.get("comments_count") or 0),
        }
        if index < MEDIA_WITH_INSIGHTS and item["id"]:
            numbers = await _media_numbers(instagram, token, item["id"])
            item.update(
                reach=numbers.get("reach"),
                views=numbers.get("views"),
                saves=numbers.get("saved"),
                shares=numbers.get("shares"),
                interactions=numbers.get("total_interactions"),
            )
        items.append(item)

    row.data = {
        "profile": {
            "username": profile.get("username") or account.username,
            "name": profile.get("name") or "",
            "picture_url": profile.get("profile_picture_url"),
            "followers": int(profile.get("followers_count") or 0),
            "follows": int(profile.get("follows_count") or 0),
            "posts": int(profile.get("media_count") or 0),
        },
        "week": week,
        "previous_week": previous,
        "series": series,
        "media": items,
    }
    row.fetched_at = utcnow()
    row.error = None
    await db.commit()
    return row


async def _totals(
    instagram: InstagramClient, token: str, ig_id: str, since: datetime, until: datetime
) -> dict[str, int]:
    """All account totals at once; if Instagram rejects one metric, each on its own."""
    try:
        return await instagram.account_totals(token, ig_id, ACCOUNT_METRICS, since, until)
    except InstagramError as exc:
        if exc.code != _INVALID_METRIC:
            logger.info("insights: totals unavailable: %s", exc)
            return {}
    totals: dict[str, int] = {}
    for metric in ACCOUNT_METRICS:
        try:
            totals.update(await instagram.account_totals(token, ig_id, [metric], since, until))
        except InstagramError:
            continue
    return totals


async def _media_numbers(instagram: InstagramClient, token: str, media_id: str) -> dict[str, int]:
    try:
        return await instagram.media_insights(token, media_id, MEDIA_METRICS)
    except InstagramError as exc:
        if exc.code != _INVALID_METRIC:
            return {}
    numbers: dict[str, int] = {}
    for metric in MEDIA_METRICS:
        try:
            numbers.update(await instagram.media_insights(token, media_id, [metric]))
        except InstagramError:
            continue
    return numbers


# ---------------------------------------------------------------------------- findings


def media_format(item: dict[str, Any]) -> str:
    if str(item.get("product_type")).upper() == "REELS":
        return "reel"
    kind = str(item.get("media_type")).upper()
    if kind == "CAROUSEL_ALBUM":
        return "carousel"
    return "video" if kind == "VIDEO" else "photo"


def engagement(item: dict[str, Any]) -> int:
    if item.get("interactions") is not None:
        return int(item["interactions"])
    return sum(int(item.get(k) or 0) for k in ("likes", "comments", "saves", "shares"))


def _local_time(value: Any, tz: ZoneInfo) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").astimezone(tz)
    except ValueError:
        return None


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _change(now: int | None, before: int | None) -> float | None:
    if now is None or not before:
        return None
    return round((now - before) / before * 100, 1)


def analyze(data: dict[str, Any], timezone: str) -> dict[str, Any]:
    """Plain findings from the stored numbers (no AI involved)."""
    tz = _zone(timezone)
    media = [m for m in data.get("media") or [] if m.get("id")]
    rows = []
    for m in media:
        reach = m.get("reach")
        eng = engagement(m)
        rows.append(
            {
                "item": m,
                "format": media_format(m),
                "engagement": eng,
                "rate": round(eng / reach * 100, 2) if reach else None,
                "at": _local_time(m.get("timestamp"), tz),
            }
        )

    by_format: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_format[row["format"]].append(row)
    formats = sorted(
        (
            {
                "format": name,
                "posts": len(group),
                "avg_engagement": round(mean(r["engagement"] for r in group), 1),
                "avg_reach": _avg([r["item"].get("reach") for r in group]),
                "avg_rate": _avg([r["rate"] for r in group]),
            }
            for name, group in by_format.items()
        ),
        key=lambda f: f["avg_engagement"],
        reverse=True,
    )

    days: dict[int, list[int]] = defaultdict(list)
    hours: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        if row["at"] is not None:
            days[row["at"].weekday()].append(row["engagement"])
            hours[row["at"].hour // 3 * 3].append(row["engagement"])
    weekday_avg = [
        {"day": day, "posts": len(v), "avg_engagement": round(mean(v), 1)}
        for day, v in sorted(days.items())
    ]
    hour_avg = [
        {"from_hour": hour, "posts": len(v), "avg_engagement": round(mean(v), 1)}
        for hour, v in sorted(hours.items())
    ]

    tags: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        for tag in set(_HASHTAG.findall(row["item"].get("caption") or "")):
            tags[tag.lower()].append(row["engagement"])
    hashtags = sorted(
        (
            {"tag": tag, "posts": len(v), "avg_engagement": round(mean(v), 1)}
            for tag, v in tags.items()
            if len(v) >= 2
        ),
        key=lambda t: t["avg_engagement"],
        reverse=True,
    )[:8]

    recent_cutoff = utcnow().astimezone(tz) - timedelta(days=30)
    recent = [r for r in rows if r["at"] is not None and r["at"] >= recent_cutoff]
    ranked = sorted(rows, key=lambda r: r["engagement"], reverse=True)
    week, previous = data.get("week") or {}, data.get("previous_week") or {}
    followers = data.get("series", {}).get("follower_count") or []
    return {
        "posts_analyzed": len(rows),
        "posts_last_30_days": len(recent),
        "posts_per_week": round(len(recent) / (30 / 7), 1),
        "avg_engagement": _avg([r["engagement"] for r in rows]),
        "avg_engagement_rate": _avg([r["rate"] for r in rows]),
        "formats": formats,
        "weekdays": weekday_avg,
        "best_days": [d["day"] for d in sorted(weekday_avg, key=lambda d: -d["avg_engagement"])][
            :2
        ],
        "hours": hour_avg,
        "best_hours": [
            h["from_hour"] for h in sorted(hour_avg, key=lambda h: -h["avg_engagement"])
        ][:2],
        "hashtags": hashtags,
        "top_posts": [r["item"]["id"] for r in ranked[:5]],
        "weakest_posts": [r["item"]["id"] for r in ranked[-3:]] if len(ranked) > 5 else [],
        "week_change": {k: _change(week.get(k), previous.get(k)) for k in week},
        "new_followers_30_days": sum(int(p.get("value") or 0) for p in followers),
    }


def _avg(values: list[Any]) -> float | None:
    numbers = [v for v in values if isinstance(v, int | float)]
    return round(mean(numbers), 1) if numbers else None


# ---------------------------------------------------------------------------- assistant

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_LANGUAGES = {"en": "English", "ar": "Arabic"}

_REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "content_report",
        "description": "The analysis of the page and the content plan.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "2-3 sentences: how the page is doing and the one thing to focus on.",
                },
                "strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "improvements": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "recommendations": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["title", "detail"],
                    },
                },
                "ideas": {
                    "type": "array",
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "format": {
                                "type": "string",
                                "enum": ["reel", "post", "carousel", "story"],
                            },
                            "title": {"type": "string"},
                            "hook": {
                                "type": "string",
                                "description": "The first line or first seconds that stop the scroll.",
                            },
                            "caption": {
                                "type": "string",
                                "description": "A ready caption with a few fitting hashtags, in the language the page posts in.",
                            },
                            "when": {"type": "string", "description": "Best day and time."},
                        },
                        "required": ["format", "title", "hook", "caption"],
                    },
                },
                "weekly_plan": {
                    "type": "array",
                    "maxItems": 7,
                    "items": {
                        "type": "object",
                        "properties": {
                            "day": {"type": "string"},
                            "format": {
                                "type": "string",
                                "enum": ["reel", "post", "carousel", "story"],
                            },
                            "idea": {"type": "string"},
                        },
                        "required": ["day", "format", "idea"],
                    },
                },
            },
            "required": ["summary", "strengths", "improvements", "recommendations", "ideas"],
        },
    },
}


async def context_for_ai(db: AsyncSession, shop: Shop, data: dict[str, Any]) -> str:
    """The page's numbers and findings, and what the shop sells, as compact text."""
    findings = analyze(data, shop.timezone)
    profile = data.get("profile") or {}
    media = {m["id"]: m for m in data.get("media") or [] if m.get("id")}

    def post_line(media_id: str) -> str:
        m = media.get(media_id) or {}
        caption = " ".join((m.get("caption") or "").split())[:160]
        return (
            f"- {media_format(m)}, {m.get('timestamp', '')[:10]}: reach {m.get('reach', '?')}, "
            f"likes {m.get('likes', 0)}, comments {m.get('comments', 0)}, saves "
            f"{m.get('saves', '?')}, shares {m.get('shares', '?')} | {caption}"
        )

    about = (
        await db.scalars(
            select(KnowledgeEntry.content).where(
                KnowledgeEntry.shop_id == shop.id, KnowledgeEntry.section == KnowledgeSection.ABOUT
            )
        )
    ).all()
    names = (
        await db.scalars(select(Product.name).where(Product.shop_id == shop.id).limit(40))
    ).all()
    lines = [
        f'Shop "{shop.name}" (@{profile.get("username", "")}). About: '
        f"{' '.join(about)[:600] or '(not given)'}",
        f"Some products: {', '.join(dict.fromkeys(n.strip() for n in names))[:500] or '(none listed)'}",
        f"Followers {profile.get('followers', '?')}, posts {profile.get('posts', '?')}, "
        f"new followers in 30 days {findings['new_followers_30_days']}.",
        f"Last 7 days: {json.dumps(data.get('week') or {})}",
        f"The 7 days before: {json.dumps(data.get('previous_week') or {})}",
        f"Posts analysed {findings['posts_analyzed']}, posted in the last 30 days "
        f"{findings['posts_last_30_days']} (~{findings['posts_per_week']}/week), average "
        f"engagement {findings['avg_engagement']} per post, rate "
        f"{findings['avg_engagement_rate']}% of reach.",
        "By format: "
        + "; ".join(
            f"{f['format']} x{f['posts']} avg engagement {f['avg_engagement']}, reach "
            f"{f['avg_reach']}"
            for f in findings["formats"]
        ),
        "Best days: "
        + ", ".join(_WEEKDAYS[d] for d in findings["best_days"])
        + f". Best hours (local, 3-hour blocks starting): {findings['best_hours']}",
        "Hashtags that pull: "
        + (", ".join(f"#{t['tag']} ({t['avg_engagement']})" for t in findings["hashtags"]) or "-"),
        "Top posts:",
        *[post_line(i) for i in findings["top_posts"]],
        "Weakest posts:",
        *([post_line(i) for i in findings["weakest_posts"]] or ["-"]),
    ]
    return "\n".join(lines)


async def make_report(db: AsyncSession, shop: Shop, llm: LLMClient) -> ContentReport:
    row = await get_row(db, shop.id)
    if row is None or not row.data:
        raise InsightsError("Read your page's numbers first.")
    if not llm.configured:
        raise InsightsError("The AI isn't set up on this server yet.")
    if not billing.can_spend(shop):
        raise InsightsError("Your wallet is empty. Top up to use the content assistant.")
    context = await context_for_ai(db, shop, row.data)
    language = _LANGUAGES.get(shop.language, "English")
    system = (
        "You are a social media strategist for small online shops on Instagram. Analyse the "
        "page's real numbers below and give practical, specific advice the owner can act on "
        "this week. Base every claim on the numbers; if something isn't measured, don't "
        f"invent it. Write the analysis in {language}. Write captions in the language the "
        "page's own captions use. Plain text in every field, no markdown."
    )
    usage = Usage()
    try:
        result = await llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": context}],
            [_REPORT_TOOL],
            tool_choice="content_report",
            max_tokens=2200,
        )
    except LLMError as exc:
        logger.warning("content report failed for shop %s: %s", shop.id, exc)
        raise InsightsError(
            "The content assistant is busy. Please try again in a moment."
        ) from None
    usage.add(result.usage)
    report: dict[str, Any] = {}
    for call in result.tool_calls:
        try:
            report = json.loads(call.get("function", {}).get("arguments") or "{}")
        except ValueError:
            report = {}
    if not isinstance(report, dict) or not report.get("summary"):
        raise InsightsError("The content assistant is busy. Please try again in a moment.")

    saved = ContentReport(
        shop_id=shop.id,
        language=shop.language,
        data=report,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
    db.add(saved)
    await db.commit()
    keep = (
        await db.scalars(
            select(ContentReport.id)
            .where(ContentReport.shop_id == shop.id)
            .order_by(ContentReport.created_at.desc())
            .limit(KEEP_REPORTS)
        )
    ).all()
    await db.execute(
        delete(ContentReport).where(ContentReport.shop_id == shop.id, ContentReport.id.not_in(keep))
    )
    await db.commit()
    await billing.charge_usage(
        db,
        shop,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        description="Content assistant report",
    )
    return saved


async def latest_report(db: AsyncSession, shop_id: Any) -> ContentReport | None:
    return await db.scalar(
        select(ContentReport)
        .where(ContentReport.shop_id == shop_id)
        .order_by(ContentReport.created_at.desc())
        .limit(1)
    )


async def ask(db: AsyncSession, shop: Shop, llm: LLMClient, turns: list[tuple[str, str]]) -> str:
    """The owner's question to the content assistant; `turns` are (role, text), oldest first."""
    if not llm.configured:
        raise InsightsError("The AI isn't set up on this server yet.")
    if not billing.can_spend(shop):
        raise InsightsError("Your wallet is empty. Top up to use the content assistant.")
    row = await get_row(db, shop.id)
    numbers = (
        await context_for_ai(db, shop, row.data)
        if row and row.data
        else "(The page's numbers haven't been read yet; give general advice and say so.)"
    )
    system = (
        "You are the content assistant of an online shop on Instagram: you help the owner plan "
        "posts, reels and stories, write captions and hooks, choose hashtags and times, and "
        "understand their numbers. Be specific and practical, and base advice on the page's "
        "numbers below when they're relevant. Reply in the language the owner writes in. "
        "Captions in the language the page posts in. Plain text: short paragraphs, simple "
        "lists starting with '-', no markdown headings or bold.\n\n"
        f"THE PAGE\n{numbers}"
    )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for role, text in turns[-12:]:
        messages.append({"role": "assistant" if role == "assistant" else "user", "content": text})
    usage = Usage()
    try:
        result = await llm.chat(messages, max_tokens=900)
    except LLMError as exc:
        logger.warning("content assistant failed for shop %s: %s", shop.id, exc)
        raise InsightsError(
            "The content assistant is busy. Please try again in a moment."
        ) from None
    usage.add(result.usage)
    answer = re.sub(r"\*\*|__|^#+\s*", "", result.content, flags=re.MULTILINE).strip()
    if not answer:
        raise InsightsError("The content assistant is busy. Please try again in a moment.")
    await billing.charge_usage(
        db,
        shop,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        description="Content assistant",
    )
    return answer
