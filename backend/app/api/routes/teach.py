"""Teach Replisto from the panel: any text, a link or a file becomes a proposal to confirm."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import LLM, CurrentShop, DbSession, HttpClient
from app.api.uploads import read_upload
from app.models import ProposalStatus, Shop, TeachProposal
from app.services import teach
from app.services.llm import LLMError
from app.services.teach import TeachError

router = APIRouter(prefix="/teach", tags=["teach"])


class ProposalOut(BaseModel):
    id: uuid.UUID
    # text | url | file
    source: str
    source_label: str
    status: ProposalStatus
    # What the AI understood, for the owner.
    summary: str
    # The whole proposal as one readable message.
    preview: str
    # products: [{action: create|update|delete, product_id, before, fields, locked}]
    #   fields use the product field names (price in the shop's currency); locked rows come
    #   from a live Google Sheet and won't be changed.
    # knowledge: [{section, title, content, mode: replace|add}]
    # questions: [str] the AI's questions to the owner
    # sheet (optional): {url, mapping, rows} connects a Google Sheet as a live source
    changes: dict[str, Any]
    result: str | None
    created_at: datetime
    applied_at: datetime | None


class ProposalPage(BaseModel):
    items: list[ProposalOut]
    total: int


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=60_000)


class UrlIn(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


class ApplyIn(BaseModel):
    # Indexes (in changes.products / changes.knowledge) the owner unticked.
    skip_products: list[int] = []
    skip_knowledge: list[int] = []


def _out(proposal: TeachProposal) -> ProposalOut:
    return ProposalOut(
        id=proposal.id,
        source=proposal.source,
        source_label=proposal.source_label,
        status=proposal.status,
        summary=proposal.summary,
        preview=teach.describe(proposal),
        changes=proposal.changes or {},
        result=proposal.result,
        created_at=proposal.created_at,
        applied_at=proposal.applied_at,
    )


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMError):
        return HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The AI service didn't respond. Please try again in a moment.",
        )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.post("/text", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
async def teach_text(body: TextIn, shop: CurrentShop, db: DbSession, llm: LLM) -> ProposalOut:
    """Anything in words: a price list, "X is sold out", shipping rules, a pasted document."""
    try:
        proposal = await teach.propose(
            db, llm, shop, body.text, source="text", label=body.text[:100]
        )
    except (TeachError, LLMError) as exc:
        raise _error(exc) from None
    return _out(proposal)


@router.post("/url", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
async def teach_url(
    body: UrlIn, shop: CurrentShop, db: DbSession, llm: LLM, http: HttpClient
) -> ProposalOut:
    """A Google Doc, Google Sheet or Google Drive file link. A sheet with recognisable
    columns becomes a live product source; anything else is read by the AI."""
    try:
        proposal = await teach.propose_from_url(db, http, llm, shop, body.url)
    except (TeachError, LLMError) as exc:
        raise _error(exc) from None
    return _out(proposal)


@router.post("/file", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
async def teach_file(file: UploadFile, shop: CurrentShop, db: DbSession, llm: LLM) -> ProposalOut:
    """PDF, Word, Excel/CSV, text or a photo of a price list."""
    data = await read_upload(file)
    filename = file.filename or "file"
    try:
        text = await teach.text_from_file(filename, data, llm)
        proposal = await teach.propose(db, llm, shop, text, source="file", label=filename)
    except (TeachError, LLMError) as exc:
        raise _error(exc) from None
    return _out(proposal)


@router.get("/proposals", response_model=ProposalPage)
async def list_proposals(
    shop: CurrentShop,
    db: DbSession,
    status_filter: Literal["pending", "applied", "discarded"] | None = Query(
        default=None, alias="status"
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> ProposalPage:
    query = select(TeachProposal).where(TeachProposal.shop_id == shop.id)
    if status_filter:
        query = query.where(TeachProposal.status == ProposalStatus(status_filter))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.scalars(
        query.order_by(TeachProposal.created_at.desc()).offset(offset).limit(limit)
    )
    return ProposalPage(items=[_out(p) for p in rows], total=total or 0)


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
async def get_proposal(proposal_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> ProposalOut:
    return _out(await _get(db, shop, proposal_id))


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalOut)
async def apply_proposal(
    proposal_id: uuid.UUID, body: ApplyIn, shop: CurrentShop, db: DbSession, http: HttpClient
) -> ProposalOut:
    proposal = await _get(db, shop, proposal_id)
    try:
        await teach.apply(
            db,
            shop,
            proposal,
            http,
            skip_products=set(body.skip_products),
            skip_knowledge=set(body.skip_knowledge),
        )
    except TeachError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await db.refresh(proposal)
    return _out(proposal)


@router.post("/proposals/{proposal_id}/discard", response_model=ProposalOut)
async def discard_proposal(proposal_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> ProposalOut:
    proposal = await _get(db, shop, proposal_id)
    await teach.discard(db, proposal)
    return _out(proposal)


@router.post("/proposals/{proposal_id}/undo", response_model=ProposalOut)
async def undo_proposal(proposal_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> ProposalOut:
    """Remove the products an applied proposal added (e.g. a channel post read by mistake)."""
    proposal = await _get(db, shop, proposal_id)
    if proposal.status != ProposalStatus.APPLIED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only applied changes can be undone.")
    await teach.undo(db, shop, proposal)
    return _out(proposal)


async def _get(db: DbSession, shop: Shop, proposal_id: uuid.UUID) -> TeachProposal:
    proposal = await db.get(TeachProposal, proposal_id)
    if proposal is None or proposal.shop_id != shop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return proposal
