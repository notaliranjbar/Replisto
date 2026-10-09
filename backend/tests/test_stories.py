"""Stories the owner schedules, published by the bot at their time."""

import io
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.core.timeutil import utcnow
from app.models import InstagramAccount, ScheduledStory, StoryStatus, User
from app.services import stories
from tests.conftest import FakeMeta

ACCOUNT = "17841400000000001"
ALL_SCOPES = (
    "instagram_business_basic,instagram_business_manage_messages,"
    "instagram_business_manage_comments,instagram_business_content_publish,"
    "instagram_business_manage_insights"
)


@pytest.fixture(autouse=True)
def media_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "media_dir", str(tmp_path))
    return tmp_path


def _png(size: tuple[int, int] = (1200, 2000)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (200, 30, 90, 255)).save(out, "PNG")
    return out.getvalue()


async def _connect(db: AsyncSession, scopes: str = ALL_SCOPES) -> None:
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


async def _schedule(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    content: bytes | None = None,
    content_type: str = "image/png",
    minutes: int = 30,
    note: str = "New linen dresses, $45",
):  # type: ignore[no-untyped-def]
    when = (utcnow() + timedelta(minutes=minutes)).isoformat()
    return await client.post(
        "/api/v1/stories",
        files={"file": ("story.png", content if content is not None else _png(), content_type)},
        data={"scheduled_at": when, "note": note},
        headers=headers,
    )


async def test_photo_is_converted_and_served_at_a_secret_link(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession, media_dir: Path
) -> None:
    await _connect(db)
    resp = await _schedule(client, auth_headers)
    assert resp.status_code == 201
    story = resp.json()
    assert story["status"] == "scheduled" and story["media_kind"] == "image"
    assert story["media_url"].startswith(f"https://api.test/api/v1/media/stories/{story['id']}/")
    assert story["media_url"].endswith(".jpg")

    # Saved as a JPEG that fits Instagram's story frame.
    [saved] = list((media_dir / "stories").iterdir())
    with Image.open(saved) as image:
        assert image.format == "JPEG"
        assert image.width <= 1080 and image.height <= 1920

    path = story["media_url"].removeprefix("https://api.test")
    served = await client.get(path)
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"
    assert (await client.get(path.replace(path.rsplit("/", 1)[-1], "wrong.jpg"))).status_code == 404

    listing = (await client.get("/api/v1/stories", headers=auth_headers)).json()
    assert listing["available"] is True
    assert [s["id"] for s in listing["upcoming"]] == [story["id"]]


async def test_bad_uploads_are_refused(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession
) -> None:
    await _connect(db)
    resp = await _schedule(client, auth_headers, content=b"hello", content_type="text/plain")
    assert resp.status_code == 400
    resp = await _schedule(client, auth_headers, minutes=-30)
    assert resp.json()["detail"] == "Choose a time in the future."
    resp = await _schedule(client, auth_headers, content=_png((100, 100)))
    assert "too small" in resp.json()["detail"]
    resp = await _schedule(
        client, auth_headers, content=b"not a video at all", content_type="video/mp4"
    )
    assert resp.status_code == 400
    resp = await client.post(
        "/api/v1/stories",
        files={"file": ("a.txt", b"x", "text/plain")},
        data={"scheduled_at": (utcnow() + timedelta(hours=1)).isoformat()},
        headers={**auth_headers, "Accept-Language": "ar"},
    )
    assert resp.json()["detail"] == "ارفع صورة (JPG أو PNG أو WebP) أو فيديو (MP4 أو MOV)."


async def test_due_story_is_published(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    fake_meta: FakeMeta,
) -> None:
    await _connect(db)
    story_id = (await _schedule(client, auth_headers)).json()["id"]
    story = await db.scalar(select(ScheduledStory))
    assert story is not None

    # Not due yet: nothing happens.
    assert await stories.publish_due(db, fake_meta.client()) == 0
    assert fake_meta.containers == []

    story.scheduled_at = utcnow() - timedelta(seconds=5)
    await db.commit()
    assert await stories.publish_due(db, fake_meta.client()) == 1
    [container] = fake_meta.containers
    assert container["media_type"] == "STORIES"
    assert container["image_url"] == stories.public_url(story)
    assert fake_meta.published == ["container-1"]

    row_id = story.id
    db.expire_all()
    story = await db.get(ScheduledStory, row_id)
    assert story.status == StoryStatus.PUBLISHED
    assert story.ig_media_id == "story-media-1"
    listing = (await client.get("/api/v1/stories", headers=auth_headers)).json()
    assert listing["upcoming"] == [] and listing["past"][0]["id"] == story_id


async def test_video_waits_while_instagram_processes_it(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    fake_meta: FakeMeta,
) -> None:
    await _connect(db)
    video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
    resp = await _schedule(client, auth_headers, content=video, content_type="video/mp4")
    assert resp.json()["media_kind"] == "video"
    story = await db.scalar(select(ScheduledStory))
    story.scheduled_at = utcnow()
    await db.commit()

    fake_meta.container_status = "IN_PROGRESS"
    await stories.publish_due(db, fake_meta.client())
    assert "video_url" in fake_meta.containers[0]
    assert story.status == StoryStatus.PROCESSING and fake_meta.published == []

    fake_meta.container_status = "FINISHED"
    await stories.publish_due(db, fake_meta.client())
    assert story.status == StoryStatus.PUBLISHED
    assert len(fake_meta.containers) == 1  # the same container, not a second upload


async def test_without_the_publishing_permission_the_story_fails_clearly(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession, fake_meta: FakeMeta
) -> None:
    await _connect(db, scopes="instagram_business_basic,instagram_business_manage_messages")
    listing = (await client.get("/api/v1/stories", headers=auth_headers)).json()
    assert listing["needs_reconnect"] is True
    story_id = (await _schedule(client, auth_headers)).json()["id"]
    resp = await client.post(
        f"/api/v1/stories/{story_id}/publish-now",
        headers={**auth_headers, "Accept-Language": "ar"},
    )
    assert resp.json()["status"] == "failed"
    assert resp.json()["error"] == "أعد ربط إنستغرام واسمح بالنشر لتُنشر القصص"
    assert fake_meta.containers == []


async def test_publish_now_edit_and_cancel(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    fake_meta: FakeMeta,
    media_dir: Path,
) -> None:
    await _connect(db)
    first = (await _schedule(client, auth_headers)).json()
    resp = await client.post(f"/api/v1/stories/{first['id']}/publish-now", headers=auth_headers)
    assert resp.json()["status"] == "published"
    # The note can still change after publishing: the bot reads it for story replies.
    resp = await client.patch(
        f"/api/v1/stories/{first['id']}",
        json={"note": "Linen dresses, now $39"},
        headers=auth_headers,
    )
    assert resp.json()["note"] == "Linen dresses, now $39"
    resp = await client.patch(
        f"/api/v1/stories/{first['id']}",
        json={"scheduled_at": (utcnow() + timedelta(days=1)).isoformat()},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    second = (await _schedule(client, auth_headers, minutes=120)).json()
    later = (utcnow() + timedelta(days=2)).isoformat()
    resp = await client.patch(
        f"/api/v1/stories/{second['id']}", json={"scheduled_at": later}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(list((media_dir / "stories").iterdir())) == 2
    resp = await client.delete(f"/api/v1/stories/{second['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert len(list((media_dir / "stories").iterdir())) == 1
