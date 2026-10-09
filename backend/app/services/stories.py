"""Stories the owner schedules; the bot publishes each one at its time.

    panel upload ──► create_story (file kept under MEDIA_DIR/stories)
    worker, every minute ──► publish_due ──► advance:
        scheduled ──(Instagram downloads the file from our public URL)──► processing
        processing ──(container FINISHED)──► media_publish ──► published

Instagram fetches the media itself, so each file is served at an unguessable public URL
(`/api/v1/media/stories/<id>/<token>.<ext>`). Photos are converted to JPEG (the only image
format the API takes); videos must be MP4 or MOV. The owner's note says what the story is
about: when customers reply to the story, the bot reads it (see messaging._with_story_note).
"""

import io
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.core.timeutil import as_utc, utcnow
from app.models import InstagramAccount, ScheduledStory, Shop, StoryStatus
from app.services.instagram import SCOPE_PUBLISH, InstagramClient, InstagramError

logger = logging.getLogger(__name__)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov"}
# Instagram's story frame; bigger photos are scaled down to fit inside it.
STORY_MAX_SIZE = (1080, 1920)
MAX_NOTE = 500
# How far ahead a story can be scheduled.
MAX_AHEAD = timedelta(days=60)
# A video Instagram is still processing after this long is given up on.
PROCESSING_TIMEOUT = timedelta(minutes=30)
MAX_ATTEMPTS = 5
# Files of published or failed stories are deleted after this; Instagram has its own copy.
KEEP_FILES = timedelta(days=30)

NOT_CONNECTED = "Instagram isn't connected"
NEEDS_PERMISSION = "Reconnect Instagram and allow publishing to post stories"
PROCESSING_FAILED = "Instagram couldn't process this file"
REFUSED = "Instagram didn't accept this story"
TOO_SLOW = "Instagram took too long to process this video"


class StoryError(Exception):
    """A problem with the upload the owner should see."""


def media_root() -> Path:
    root = Path(get_settings().media_dir) / "stories"
    root.mkdir(parents=True, exist_ok=True)
    return root


def file_path(story: ScheduledStory) -> Path:
    return media_root() / story.file_name


def public_url(story: ScheduledStory) -> str:
    """Where Instagram (and the panel) downloads the story's file."""
    ext = story.file_name.rsplit(".", 1)[-1]
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/api/v1/media/stories/{story.id}/{story.token}.{ext}"


def prepare_media(data: bytes, content_type: str) -> tuple[str, bytes, str, str]:
    """Check an upload and make it Instagram-ready: (kind, bytes, content type, extension)."""
    settings = get_settings()
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type in IMAGE_TYPES:
        if len(data) > settings.story_image_max_bytes * 3:
            raise StoryError("This photo is too large.")
        from PIL import Image, ImageOps, UnidentifiedImageError

        try:
            image = Image.open(io.BytesIO(data))
            image = ImageOps.exif_transpose(image)
            image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            raise StoryError("This photo couldn't be read. Try a JPG or PNG file.") from None
        if image.width < 320 or image.height < 320:
            raise StoryError("This photo is too small; use at least 320 pixels on each side.")
        image.thumbnail(STORY_MAX_SIZE)
        if image.mode != "RGB":
            background = Image.new("RGB", image.size, (255, 255, 255))
            rgba = image.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        out = io.BytesIO()
        image.save(out, "JPEG", quality=90, optimize=True)
        jpeg = out.getvalue()
        if len(jpeg) > settings.story_image_max_bytes:
            raise StoryError("This photo is too large.")
        return "image", jpeg, "image/jpeg", "jpg"
    if content_type in VIDEO_TYPES:
        if len(data) > settings.story_video_max_bytes:
            raise StoryError("This video is too large; stories take videos up to 100 MB.")
        if data[4:8] != b"ftyp":
            raise StoryError("This video couldn't be read. Use an MP4 or MOV file.")
        return "video", data, content_type, VIDEO_TYPES[content_type]
    raise StoryError("Upload a photo (JPG, PNG, WebP) or a video (MP4, MOV).")


async def create_story(
    db: AsyncSession,
    shop: Shop,
    data: bytes,
    content_type: str,
    scheduled_at: datetime,
    note: str,
) -> ScheduledStory:
    now = utcnow()
    scheduled_at = as_utc(scheduled_at)
    if scheduled_at < now - timedelta(minutes=2):
        raise StoryError("Choose a time in the future.")
    if scheduled_at > now + MAX_AHEAD:
        raise StoryError("Stories can be scheduled up to 60 days ahead.")
    kind, content, stored_type, ext = prepare_media(data, content_type)
    story_id = uuid.uuid4()
    name = f"{story_id.hex}.{ext}"
    (media_root() / name).write_bytes(content)
    story = ScheduledStory(
        id=story_id,
        shop_id=shop.id,
        media_kind=kind,
        file_name=name,
        content_type=stored_type,
        size_bytes=len(content),
        token=secrets.token_urlsafe(24),
        note=note.strip()[:MAX_NOTE],
        scheduled_at=max(scheduled_at, now),
    )
    db.add(story)
    await db.commit()
    return story


def delete_file(story: ScheduledStory) -> None:
    try:
        file_path(story).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("couldn't delete story file %s: %s", story.file_name, exc)


# ---------------------------------------------------------------------------- publishing


async def publish_due(db: AsyncSession, instagram: InstagramClient) -> int:
    """Move every due story one step forward; returns how many were published."""
    now = utcnow()
    due = (
        await db.scalars(
            select(ScheduledStory)
            .where(
                or_(
                    (ScheduledStory.status == StoryStatus.SCHEDULED)
                    & (ScheduledStory.scheduled_at <= now),
                    ScheduledStory.status == StoryStatus.PROCESSING,
                )
            )
            .order_by(ScheduledStory.scheduled_at)
            .limit(50)
        )
    ).all()
    published = 0
    for story in due:
        await advance(db, story, instagram)
        published += story.status == StoryStatus.PUBLISHED
    return published


async def advance(db: AsyncSession, story: ScheduledStory, instagram: InstagramClient) -> None:
    """One step of publishing: hand the file to Instagram, then publish once it's ready."""
    account = await db.scalar(
        select(InstagramAccount).where(InstagramAccount.shop_id == story.shop_id)
    )
    if account is None or not account.is_active:
        await _fail(db, story, NOT_CONNECTED)
        return
    if not account.has_scope(SCOPE_PUBLISH):
        await _fail(db, story, NEEDS_PERMISSION)
        return
    token = decrypt_secret(account.access_token_encrypted)
    try:
        if story.status == StoryStatus.SCHEDULED:
            # Claim it, so a "publish now" and the minute job never both create a container.
            claimed = await db.execute(
                update(ScheduledStory)
                .where(
                    ScheduledStory.id == story.id,
                    ScheduledStory.status == StoryStatus.SCHEDULED,
                )
                .values(status=StoryStatus.PROCESSING, updated_at=utcnow())
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            if claimed.rowcount == 0:
                return
            story.status = StoryStatus.PROCESSING
            url = public_url(story)
            story.container_id = await instagram.create_story(
                token,
                account.ig_user_id,
                image_url=url if story.media_kind == "image" else None,
                video_url=url if story.media_kind == "video" else None,
            )
            await db.commit()
        if story.status != StoryStatus.PROCESSING or not story.container_id:
            return
        state = await instagram.container_status(token, story.container_id)
        if state in ("ERROR", "EXPIRED"):
            await _fail(db, story, PROCESSING_FAILED)
            return
        if state == "IN_PROGRESS":
            if utcnow() - as_utc(story.scheduled_at) > PROCESSING_TIMEOUT:
                await _fail(db, story, TOO_SLOW)
            return
        if state != "PUBLISHED":
            story.ig_media_id = await instagram.publish(
                token, account.ig_user_id, story.container_id
            )
        story.status = StoryStatus.PUBLISHED
        story.published_at = utcnow()
        story.error = None
        await db.commit()
    except InstagramError as exc:
        story.attempts += 1
        logger.warning("story %s step failed (try %s): %s", story.id, story.attempts, exc)
        if exc.retryable and story.attempts < MAX_ATTEMPTS:
            if not story.container_id:
                story.status = StoryStatus.SCHEDULED  # start over at the next run
            await db.commit()
            return
        await _fail(db, story, REFUSED)


async def _fail(db: AsyncSession, story: ScheduledStory, reason: str) -> None:
    story.status = StoryStatus.FAILED
    story.error = reason
    await db.commit()


async def cleanup(db: AsyncSession) -> int:
    """Delete the files (and rows) of stories that finished a while ago."""
    cutoff = utcnow() - KEEP_FILES
    old = (
        await db.scalars(
            select(ScheduledStory).where(
                ScheduledStory.status.in_([StoryStatus.PUBLISHED, StoryStatus.FAILED]),
                ScheduledStory.updated_at < cutoff,
            )
        )
    ).all()
    for story in old:
        delete_file(story)
        await db.delete(story)
    await db.commit()
    return len(old)
