"""The page's insights, the findings from them, and the content assistant."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_secret
from app.models import InstagramAccount, User, WalletEntry
from app.services.insights import analyze
from tests.conftest import FakeMeta, FakeWeb

ACCOUNT = "17841400000000001"


def _post(media_id: str, when: str, product_type: str = "FEED", caption: str = "") -> dict:
    return {
        "id": media_id,
        "caption": caption,
        "media_type": "VIDEO" if product_type == "REELS" else "IMAGE",
        "media_product_type": product_type,
        "permalink": f"https://www.instagram.com/p/{media_id}/",
        "thumbnail_url": f"https://cdn.test/{media_id}.jpg",
        "timestamp": when,
        "like_count": 10,
        "comments_count": 2,
    }


@pytest.fixture
def page(fake_meta: FakeMeta) -> FakeMeta:
    fake_meta.media = [
        # Reels on Thursday evenings (Beirut time) do best.
        _post("r1", "2026-10-01T15:30:00+0000", "REELS", "New linen #summer #linen"),
        _post("r2", "2026-09-24T16:00:00+0000", "REELS", "Behind the scenes #linen"),
        _post("p1", "2026-09-28T06:00:00+0000", "FEED", "Restock #summer"),
        _post("p2", "2026-09-21T07:00:00+0000", "FEED", "Our shop"),
    ]
    fake_meta.media_numbers = {
        "r1": {"reach": 4000, "views": 9000, "saved": 120, "shares": 60, "total_interactions": 600},
        "r2": {"reach": 3000, "views": 7000, "saved": 80, "shares": 40, "total_interactions": 420},
        "p1": {"reach": 900, "saved": 10, "shares": 2, "total_interactions": 70},
        "p2": {"reach": 700, "saved": 4, "shares": 1, "total_interactions": 40},
    }
    fake_meta.account_totals = {"reach": 8600, "views": 20000, "total_interactions": 1130}
    fake_meta.series = {"reach": [1000, 1300, 1200], "follower_count": [12, 9, 15]}
    return fake_meta


async def _connect(db: AsyncSession, scopes: str) -> None:
    user = await db.scalar(select(User).where(User.email == "owner@shop.com"))
    await db.refresh(user, ["shop"])
    db.add(
        InstagramAccount(
            shop_id=user.shop.id,
            ig_user_id=ACCOUNT,
            username="layla.boutique",
            access_token_encrypted=encrypt_secret("page-token"),
            scopes=scopes,
        )
    )
    await db.commit()


async def test_refresh_reads_the_page_and_finds_what_works(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession, page: FakeMeta
) -> None:
    await _connect(db, "instagram_business_basic,instagram_business_manage_insights")
    empty = (await client.get("/api/v1/insights", headers=auth_headers)).json()
    assert empty["available"] is True and empty["profile"] is None and empty["analysis"] is None

    resp = await client.post("/api/v1/insights/refresh", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["followers"] == 1520
    assert body["week"]["reach"] == 8600
    assert [p["value"] for p in body["follower_series"]] == [12, 9, 15]
    reel = next(m for m in body["media"] if m["id"] == "r1")
    assert reel["format"] == "reel" and reel["reach"] == 4000 and reel["engagement"] == 600
    assert reel["rate"] == 15.0

    analysis = body["analysis"]
    assert analysis["formats"][0]["format"] == "reel"
    assert analysis["top_posts"][0] == "r1"
    assert analysis["best_days"][0] == 3  # Thursday
    assert analysis["best_hours"][0] == 18  # 18:30 in Beirut
    assert analysis["hashtags"][0]["tag"] in {"linen", "summer"}
    assert analysis["new_followers_30_days"] == 36


async def test_without_the_insights_permission_the_owner_is_asked_to_reconnect(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession, page: FakeMeta
) -> None:
    await _connect(db, "instagram_business_basic,instagram_business_manage_messages")
    body = (await client.get("/api/v1/insights", headers=auth_headers)).json()
    assert body["needs_reconnect"] is True
    resp = await client.post("/api/v1/insights/refresh", headers=auth_headers)
    assert resp.status_code == 400


async def test_content_report_and_questions_are_charged(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    page: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
    billing_on: None,
) -> None:
    await _connect(db, "instagram_business_manage_insights")
    user = await db.scalar(select(User).where(User.email == "owner@shop.com"))
    await db.refresh(user, ["shop"])
    user.shop.balance_cents = 500
    await db.commit()
    await client.post("/api/v1/insights/refresh", headers=auth_headers)

    fake_web.llm_replies.append(
        FakeWeb.tool_call(
            "content_report",
            {
                "summary": "Reels reach 4x more people than photos. Post two a week.",
                "strengths": ["Reels about new arrivals"],
                "improvements": ["Photos get little reach"],
                "recommendations": [{"title": "More reels", "detail": "Two per week."}],
                "ideas": [
                    {
                        "format": "reel",
                        "title": "Try-on",
                        "hook": "3 ways to wear linen",
                        "caption": "Which one is yours? #linen",
                        "when": "Thursday 18:00",
                    },
                    {"format": "tiktok", "title": "skip", "hook": "x", "caption": "x"},
                ],
                "weekly_plan": [{"day": "Thursday", "format": "reel", "idea": "Try-on"}],
            },
        )
    )
    resp = await client.post("/api/v1/insights/report", headers=auth_headers)
    assert resp.status_code == 200
    report = resp.json()
    assert report["summary"].startswith("Reels reach")
    assert [i["title"] for i in report["ideas"]] == ["Try-on"]  # the unknown format is dropped
    # The assistant was given the real numbers.
    context = fake_web.llm_requests[-1]["messages"][1]["content"]
    assert "Best days: Thursday" in context and "#linen" in context
    assert (await client.get("/api/v1/insights", headers=auth_headers)).json()["report"][
        "summary"
    ] == report["summary"]

    fake_web.llm_replies.append({"content": "**Try** a reel on Thursday at 6pm."})
    resp = await client.post(
        "/api/v1/insights/assistant",
        json={"messages": [{"role": "owner", "text": "When should I post my next reel?"}]},
        headers=auth_headers,
    )
    assert resp.json() == {"reply": "Try a reel on Thursday at 6pm."}

    descriptions = (
        await db.scalars(select(WalletEntry.description).where(WalletEntry.amount_cents < 0))
    ).all()
    assert sorted(descriptions) == ["Content assistant", "Content assistant report"]


async def test_empty_wallet_blocks_the_assistant(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    llm_on: None,
    billing_on: None,
) -> None:
    resp = await client.post(
        "/api/v1/insights/assistant",
        json={"messages": [{"role": "owner", "text": "Ideas?"}]},
        headers={**auth_headers, "Accept-Language": "ar"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "محفظتك فارغة. اشحنها لاستخدام مساعد المحتوى."


def test_analysis_handles_a_page_without_numbers() -> None:
    findings = analyze({"media": []}, "Asia/Beirut")
    assert findings["posts_analyzed"] == 0
    assert findings["best_days"] == [] and findings["avg_engagement_rate"] is None
    assert analyze({}, "Not/AZone")["formats"] == []
