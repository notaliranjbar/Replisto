"""Stories the owner schedules for the bot to publish, and the public links to their files."""

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentShop, DbSession, Instagram
from app.core.config import get_settings
from app.core.i18n import localize
from app.core.timeutil import as_utc, utcnow
from app.models import InstagramAccount, ScheduledStory, StoryStatus
from app.services import stories
from app.services.instagram import SCOPE_PUBLISH

router = APIRouter(prefix="/stories", tags=["stories"])
# No login: Instagram downloads the files from here. The token in the name is the key.
media_router = APIRouter(prefix="/media", include_in_schema=False)


class StoryOut(BaseModel):
    id: uuid.UUID
    media_kind: str
    media_url: str
    note: str
    scheduled_at: datetime
    status: StoryStatus
    published_at: datetime | None
    error: str | None
    size_bytes: int


class StoriesOut(BaseModel):
    # Instagram connected with permission to publish.
    available: bool
    needs_reconnect: bool
    upcoming: list[StoryOut]
    # Published or failed, newest first (the last 30 days).
    past: list[StoryOut]


class StoryUpdate(BaseModel):
    scheduled_at: datetime | None = None
    note: str | None = Field(default=None, max_length=stories.MAX_NOTE)


def _out(story: ScheduledStory) -> StoryOut:
    return StoryOut(
        id=story.id,
        media_kind=story.media_kind,
        media_url=stories.public_url(story),
        note=story.note,
        scheduled_at=story.scheduled_at,
        status=story.status,
        published_at=story.published_at,
        error=localize(story.error),
        size_bytes=story.size_bytes,
    )


@router.get("", response_model=StoriesOut)
async def list_stories(shop: CurrentShop, db: DbSession) -> StoriesOut:
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    items = (
        await db.scalars(
            select(ScheduledStory)
            .where(ScheduledStory.shop_id == shop.id)
            .order_by(ScheduledStory.scheduled_at)
        )
    ).all()
    waiting = (StoryStatus.SCHEDULED, StoryStatus.PROCESSING)
    connected = account is not None and account.is_active
    return StoriesOut(
        available=connected and account.has_scope(SCOPE_PUBLISH),
        needs_reconnect=connected and not account.has_scope(SCOPE_PUBLISH),
        upcoming=[_out(s) for s in items if s.status in waiting],
        past=[_out(s) for s in reversed(items) if s.status not in waiting],
    )


@router.post("", response_model=StoryOut, status_code=status.HTTP_201_CREATED)
async def schedule_story(
    shop: CurrentShop,
    db: DbSession,
    file: UploadFile = File(...),
    scheduled_at: datetime = Form(...),
    note: str = Form(default=""),
) -> StoryOut:
    """Upload a photo or video and the time to publish it."""
    limit = max(get_settings().story_video_max_bytes, get_settings().story_image_max_bytes * 3)
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "This file is too large.")
    try:
        story = await stories.create_story(
            db, shop, data, file.content_type or "", scheduled_at, note
        )
    except stories.StoryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, localize(str(exc))) from None
    return _out(story)


async def _own(db: DbSession, shop_id: uuid.UUID, story_id: uuid.UUID) -> ScheduledStory:
    story = await db.get(ScheduledStory, story_id)
    if story is None or story.shop_id != shop_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found")
    return story


@router.patch("/{story_id}", response_model=StoryOut)
async def update_story(
    story_id: uuid.UUID, body: StoryUpdate, shop: CurrentShop, db: DbSession
) -> StoryOut:
    """Move a story to another time, or change its note (the note works even after publishing:
    the bot reads it when people reply to the story)."""
    story = await _own(db, shop.id, story_id)
    if body.note is not None:
        story.note = body.note.strip()
    if body.scheduled_at is not None:
        if story.status != StoryStatus.SCHEDULED:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "This story is already on its way to Instagram."
            )
        when = as_utc(body.scheduled_at)
        if when < utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a time in the future.")
        story.scheduled_at = when
    await db.commit()
    return _out(story)


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(story_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> None:
    """Cancel a scheduled story, or remove a finished one from the list."""
    story = await _own(db, shop.id, story_id)
    if story.status == StoryStatus.PROCESSING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This story is already on its way to Instagram."
        )
    stories.delete_file(story)
    await db.delete(story)
    await db.commit()


@router.post("/{story_id}/publish-now", response_model=StoryOut)
async def publish_now(
    story_id: uuid.UUID, shop: CurrentShop, db: DbSession, instagram: Instagram
) -> StoryOut:
    story = await _own(db, shop.id, story_id)
    if story.status != StoryStatus.SCHEDULED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This story is already on its way to Instagram."
        )
    story.scheduled_at = utcnow()
    await db.commit()
    await stories.advance(db, story, instagram)
    # Photos are usually live at once; a video finishes processing within a few minutes.
    if story.status == StoryStatus.PROCESSING:
        await stories.advance(db, story, instagram)
    return _out(story)


@media_router.get("/stories/{story_id}/{name}")
async def story_file(story_id: uuid.UUID, name: str, db: DbSession) -> FileResponse:
    story = await db.get(ScheduledStory, story_id)
    token = name.rsplit(".", 1)[0]
    if story is None or not secrets.compare_digest(token, story.token):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = stories.file_path(story)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return FileResponse(
        path, media_type=story.content_type, headers={"Cache-Control": "private, max-age=3600"}
    )
