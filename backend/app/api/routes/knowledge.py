import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import LLM, CurrentShop, DbSession
from app.api.uploads import read_upload
from app.core.config import get_settings
from app.core.i18n import localize
from app.models import KnowledgeEntry, KnowledgeSection, Shop
from app.services import knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SectionOut(BaseModel):
    key: KnowledgeSection
    label: str
    hint: str
    placeholder: str
    multiple: bool


class SectionsOut(BaseModel):
    sections: list[SectionOut]
    supported_file_types: list[str]
    max_file_bytes: int
    char_limit: int


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section: KnowledgeSection
    title: str
    content: str
    source_filename: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeOut(BaseModel):
    entries: list[EntryOut]
    chars_used: int
    char_limit: int


class EntryCreate(BaseModel):
    section: KnowledgeSection
    title: str = Field(default="", max_length=255)
    content: str = Field(min_length=1, max_length=40_000)


class EntryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=40_000)


class SingleSectionUpdate(BaseModel):
    content: str = Field(max_length=40_000)


@router.get("/sections", response_model=SectionsOut)
async def sections() -> SectionsOut:
    """Static description of the knowledge form: render the panel from this."""
    settings = get_settings()
    return SectionsOut(
        sections=[
            SectionOut(**{**s.__dict__, "label": localize(s.label) or s.label})
            for s in knowledge.SECTIONS
        ],
        supported_file_types=knowledge.SUPPORTED_EXTENSIONS,
        max_file_bytes=settings.upload_max_bytes,
        char_limit=settings.knowledge_char_limit,
    )


@router.get("", response_model=KnowledgeOut)
async def list_entries(shop: CurrentShop, db: DbSession) -> KnowledgeOut:
    entries = await _entries(db, shop)
    return KnowledgeOut(
        entries=[EntryOut.model_validate(e) for e in entries],
        chars_used=knowledge.total_chars(entries),
        char_limit=get_settings().knowledge_char_limit,
    )


@router.post("", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(body: EntryCreate, shop: CurrentShop, db: DbSession) -> KnowledgeEntry:
    if not knowledge.SECTION_BY_KEY[body.section].multiple:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This section holds a single text; use PUT /knowledge/single/{section}.",
        )
    await _check_limit(db, shop, len(body.title) + len(body.content))
    entry = KnowledgeEntry(
        shop_id=shop.id, section=body.section, title=body.title.strip(), content=body.content
    )
    db.add(entry)
    await db.commit()
    return entry


@router.put("/single/{section}", response_model=EntryOut | None)
async def set_single_section(
    section: KnowledgeSection, body: SingleSectionUpdate, shop: CurrentShop, db: DbSession
) -> KnowledgeEntry | None:
    """Set the text of a one-box section (about, shipping, ...). Empty content clears it."""
    if knowledge.SECTION_BY_KEY[section].multiple:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This section holds several entries.")
    entry = await db.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.shop_id == shop.id, KnowledgeEntry.section == section
        )
    )
    content = body.content.strip()
    if not content:
        if entry is not None:
            await db.delete(entry)
            await db.commit()
        return None
    current = len(entry.content) if entry else 0
    await _check_limit(db, shop, len(content) - current)
    if entry is None:
        entry = KnowledgeEntry(shop_id=shop.id, section=section, content=content)
        db.add(entry)
    else:
        entry.content = content
    await db.commit()
    await db.refresh(entry)
    return entry


@router.post("/upload", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile, shop: CurrentShop, db: DbSession, llm: LLM
) -> KnowledgeEntry:
    """Extract text from a file into a new, editable entry in the "file" section."""
    data = await read_upload(file)
    filename = file.filename or "file"
    try:
        text = await knowledge.extract_text(filename, data, llm)
    except knowledge.ExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await _check_limit(db, shop, len(text))
    entry = KnowledgeEntry(
        shop_id=shop.id,
        section=KnowledgeSection.FILE,
        title=filename[:255],
        content=text,
        source_filename=filename[:255],
    )
    db.add(entry)
    await db.commit()
    return entry


@router.patch("/{entry_id}", response_model=EntryOut)
async def update_entry(
    entry_id: uuid.UUID, body: EntryUpdate, shop: CurrentShop, db: DbSession
) -> KnowledgeEntry:
    entry = await _get_entry(db, shop, entry_id)
    growth = 0
    if body.title is not None:
        growth += len(body.title) - len(entry.title)
    if body.content is not None:
        growth += len(body.content) - len(entry.content)
    await _check_limit(db, shop, growth)
    if body.title is not None:
        entry.title = body.title.strip()
    if body.content is not None:
        entry.content = body.content
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> None:
    await db.delete(await _get_entry(db, shop, entry_id))
    await db.commit()


async def _entries(db: DbSession, shop: Shop) -> list[KnowledgeEntry]:
    return list(
        (
            await db.scalars(
                select(KnowledgeEntry)
                .where(KnowledgeEntry.shop_id == shop.id)
                .order_by(KnowledgeEntry.created_at)
            )
        ).all()
    )


async def _get_entry(db: DbSession, shop: Shop, entry_id: uuid.UUID) -> KnowledgeEntry:
    entry = await db.get(KnowledgeEntry, entry_id)
    if entry is None or entry.shop_id != shop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    return entry


async def _check_limit(db: DbSession, shop: Shop, growth: int) -> None:
    if growth <= 0:
        return
    limit = get_settings().knowledge_char_limit
    used = knowledge.total_chars(await _entries(db, shop))
    if used + growth > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"This would go over the limit of {limit:,} characters.",
        )
