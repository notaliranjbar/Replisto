"""Teaching Replisto: turn whatever the owner sends into product and knowledge changes.

Owners describe their shop in every possible way: they type a price list or a change ("the
black linen dress is now $45, two left in size M"), paste a Google Doc link with no
particular structure, upload a PDF, or connect a sheet. All of it goes
through one path:

    input ──► text (download / extract) ──► AI extraction ──► TeachProposal
                                                                              │
                           owner confirms in the panel ──► apply ◄──┘

The proposal is shown before anything changes, so a misunderstanding never reaches the
catalogue. The AI sees the shop's current products (with short refs like "#3") so "the price
of X is now Y" or "I sold two" becomes an update of the right row instead of a duplicate.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.text import normalize, parse_decimal, parse_int
from app.core.timeutil import utcnow
from app.models import (
    KnowledgeEntry,
    KnowledgeSection,
    Product,
    ProductOrigin,
    ProductSource,
    ProductSourceKind,
    ProposalStatus,
    Shop,
    TeachProposal,
)
from app.services import billing, knowledge, products
from app.services.llm import LLMClient, Usage

logger = logging.getLogger(__name__)

# One AI call reads at most this much text; longer inputs are read in parts.
CHUNK_CHARS = 12_000
# Existing products shown to the AI so it can update them instead of adding duplicates.
MAX_CONTEXT_PRODUCTS = 250
MAX_PROPOSED_PRODUCTS = 300

_PRODUCT_FIELDS = ("name", "sku", "category", "color", "size", "description")
_SINGLE_SECTIONS = {s.key for s in knowledge.SECTIONS if not s.multiple}
_TEACHABLE_SECTIONS = [
    KnowledgeSection.ABOUT,
    KnowledgeSection.SHIPPING,
    KnowledgeSection.PAYMENT,
    KnowledgeSection.RETURNS,
    KnowledgeSection.CONTACT,
    KnowledgeSection.FAQ,
    KnowledgeSection.FREE_TEXT,
]


class TeachError(Exception):
    """User-facing reason the input could not be read or understood."""


@dataclass
class Extraction:
    summary: str
    changes: dict[str, Any]
    usage: Usage


# ---------------------------------------------------------------------------- the AI call

_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_changes",
        "description": "Record what the shop assistant should learn from the owner's input.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One or two short sentences to the owner, in the language "
                    "they wrote in: what you "
                    "understood and will change. If there is nothing to learn, say so.",
                },
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref": {
                                "type": "string",
                                "description": 'An EXISTING PRODUCTS ref like "#3" to update '
                                "or delete that row. Omit to add a new product.",
                            },
                            "delete": {
                                "type": "boolean",
                                "description": "True only if the owner says the product is "
                                "no longer sold. Sold out is stock 0, not delete.",
                            },
                            "name": {"type": "string"},
                            "sku": {"type": "string"},
                            "category": {"type": "string"},
                            "color": {"type": "string"},
                            "size": {"type": "string"},
                            "price": {"type": "number"},
                            "stock": {"type": "integer"},
                            "description": {"type": "string"},
                        },
                    },
                },
                "knowledge": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {
                                "type": "string",
                                "enum": [s.value for s in _TEACHABLE_SECTIONS],
                            },
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["section", "content"],
                    },
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Questions to the owner, in their language, only when something "
                    "essential is unclear (e.g. which product they mean).",
                },
            },
            "required": ["summary"],
        },
    },
}

_SOURCE_HINTS = {
    "text": "a message the owner typed",
    "url": "the content of a document the owner linked",
    "file": "the text of a file the owner uploaded",
}


def _system_prompt(shop: Shop, source: str, products_block: str, sections_block: str) -> str:
    return f"""You keep the knowledge of the AI sales assistant of the online shop "{shop.name}" up to date. The input below is {_SOURCE_HINTS.get(source, "something from the owner")}. Extract what the assistant should learn and call propose_changes.

PRODUCTS
- One entry per sellable variant. If colours or sizes have their own stock or price, make one entry per colour/size. If several sizes or colours are listed without separate stock, still make one entry per size/colour (stock unknown).
- price is a number in the shop's currency ({shop.currency}), without the currency sign: "$49.90" = 49.9, "1.2k" = 1200. If the input gives prices in another currency, keep the number and mention it in the summary.
- stock: a count; 0 for sold out ("sold out", "نفدت الكمية"); leave it out when unknown ("in stock" without a number: leave it out).
- To change an existing product, give its ref and ONLY the fields that change. For "I sold two" compute the new stock from the current one. If the change applies to several rows (all sizes of a product), give one entry per row.
- Never invent prices, stock, sizes or colours. Leave out what the input doesn't say.
- Rows marked [sheet] come from a live Google Sheet: don't change them; mention in the summary that the owner should edit the sheet.

SHOP INFORMATION
- Policies and facts go to knowledge: about (who the shop is), shipping, payment (and how to order), returns, contact (links, phone, address, hours), faq (title = the question, content = the answer), free_text (anything else, e.g. discount codes).
- about/shipping/payment/returns/contact hold ONE text each: give the complete new text, merging the current text below with what's new.

Write product names, descriptions and knowledge in the language the owner uses, as they would.

EXISTING PRODUCTS (ref | name | colour | size | price | stock)
{products_block or "(none yet)"}

CURRENT SHOP INFORMATION
{sections_block or "(empty)"}"""


async def extract(
    db: AsyncSession, llm: LLMClient, shop: Shop, text: str, source: str, context: str = ""
) -> Extraction:
    """Ask the AI what to learn from `text`. Raises TeachError / LLMError.

    `context` is earlier input from the owner, so a follow-up like "make its price 25"
    is understood.
    """
    text = text.strip()
    if not text:
        raise TeachError("There was no text to read.")
    limit = get_settings().teach_max_chars
    if len(text) > limit:
        raise TeachError(
            f"The text is over the limit of {limit:,} characters. Split it into parts."
        )
    if not llm.configured:
        raise TeachError("The AI isn't set up on the server.")

    refs, products_block = await _products_context(db, shop, f"{context}\n{text}")
    sections_block = await _sections_context(db, shop)
    system = _system_prompt(shop, source, products_block, sections_block)
    if context:
        system += (
            '\n\nRECENT CONVERSATION WITH THE OWNER (oldest first; "You" is you). Use it to '
            'understand what the new input refers to ("it", "its price", "that one" = the '
            "product just discussed). Learn only what the new input says.\n" + context
        )
    usage = Usage()
    summaries: list[str] = []
    merged: dict[str, Any] = {"products": [], "knowledge": [], "questions": []}
    for chunk in _chunks(text):
        result = await llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": chunk}],
            [_TOOL],
            tool_choice="propose_changes",
            max_tokens=4000,
        )
        usage.add(result.usage)
        raw = _tool_arguments(result.tool_calls, result.content)
        if raw.get("summary"):
            summaries.append(str(raw["summary"]).strip())
        for key in ("products", "knowledge", "questions"):
            value = raw.get(key)
            if isinstance(value, list):
                merged[key].extend(value)

    changes = _clean(merged, refs)
    return Extraction(summary="\n".join(summaries)[:2000], changes=changes, usage=usage)


def _chunks(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        while len(paragraph) > CHUNK_CHARS:
            parts.append(paragraph[:CHUNK_CHARS])
            paragraph = paragraph[CHUNK_CHARS:]
        if len(current) + len(paragraph) + 2 > CHUNK_CHARS and current:
            parts.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return parts


def _tool_arguments(tool_calls: list[dict[str, Any]], content: str) -> dict[str, Any]:
    for call in tool_calls:
        function = call.get("function") or {}
        if function.get("name") == "propose_changes":
            raw = function.get("arguments")
            if isinstance(raw, dict):
                return raw
            try:
                parsed = json.loads(raw or "{}")
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
    # Some models answer with the JSON as text instead of a tool call.
    match = re.search(r"\{.*\}", content or "", re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
    return {}


async def _products_context(
    db: AsyncSession, shop: Shop, text: str
) -> tuple[dict[str, Product], str]:
    total = await db.scalar(
        select(func.count()).select_from(Product).where(Product.shop_id == shop.id)
    )
    if (total or 0) <= MAX_CONTEXT_PRODUCTS:
        items = list(
            (
                await db.scalars(
                    select(Product)
                    .where(Product.shop_id == shop.id)
                    .order_by(Product.name, Product.color, Product.size)
                )
            ).all()
        )
    else:
        # Big catalogues: only the rows the input talks about.
        query = " ".join(normalize(text).split()[:400])
        items = await products.search_products(db, shop.id, query, limit=MAX_CONTEXT_PRODUCTS)
    refs: dict[str, Product] = {}
    lines = []
    for index, product in enumerate(items, start=1):
        ref = f"#{index}"
        refs[ref] = product
        price = _fmt_number(product.price) if product.price is not None else "-"
        stock = str(product.stock) if product.stock is not None else "-"
        locked = " [sheet]" if product.origin == ProductOrigin.SHEET else ""
        lines.append(
            f"{ref} | {product.name} | {product.color or '-'} | {product.size or '-'} | "
            f"{price} | {stock}{locked}"
        )
    return refs, "\n".join(lines)


async def _sections_context(db: AsyncSession, shop: Shop) -> str:
    entries = (
        await db.scalars(
            select(KnowledgeEntry).where(
                KnowledgeEntry.shop_id == shop.id, KnowledgeEntry.section.in_(_SINGLE_SECTIONS)
            )
        )
    ).all()
    blocks = [f"[{e.section.value}]\n{e.content.strip()[:2000]}" for e in entries]
    return "\n\n".join(blocks)


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def _int(value: Any) -> int | None:
    number = parse_int(value)
    return number if number is not None and number >= 0 else None


def _clean(raw: dict[str, Any], refs: dict[str, Product]) -> dict[str, Any]:
    """Validate the AI's output into the proposal format stored on TeachProposal.changes."""
    product_changes: list[dict[str, Any]] = []
    for item in raw["products"][:MAX_PROPOSED_PRODUCTS]:
        if not isinstance(item, dict):
            continue
        fields: dict[str, Any] = {}
        limits = {"name": 255, "sku": 64, "category": 120, "color": 64, "size": 64}
        for key in _PRODUCT_FIELDS:
            if key in item:
                value = _text(item[key], limits.get(key, 5000))
                if value is not None:
                    fields[key] = value
        price = parse_decimal(item.get("price"))
        if price is not None and price >= 0:
            fields["price"] = products.price_number(price.quantize(Decimal("0.01")))
        if "stock" in item and _int(item["stock"]) is not None:
            fields["stock"] = _int(item["stock"])

        ref = str(item.get("ref") or "").strip()
        if ref and not ref.startswith("#"):
            ref = f"#{ref}"
        existing = refs.get(ref) if ref else None
        if existing is not None:
            locked = existing.origin == ProductOrigin.SHEET
            before = _snapshot(existing)
            if item.get("delete") is True:
                product_changes.append(
                    {
                        "action": "delete",
                        "product_id": str(existing.id),
                        "before": before,
                        "fields": {},
                        "locked": locked,
                    }
                )
                continue
            fields = {k: v for k, v in fields.items() if before.get(k) != v}
            if fields:
                product_changes.append(
                    {
                        "action": "update",
                        "product_id": str(existing.id),
                        "before": before,
                        "fields": fields,
                        "locked": locked,
                    }
                )
        elif not ref and fields.get("name") and item.get("delete") is not True:
            product_changes.append(
                {
                    "action": "create",
                    "product_id": None,
                    "before": None,
                    "fields": fields,
                    "locked": False,
                }
            )

    knowledge_changes: list[dict[str, Any]] = []
    valid_sections = {s.value for s in _TEACHABLE_SECTIONS}
    for item in raw["knowledge"]:
        if not isinstance(item, dict) or item.get("section") not in valid_sections:
            continue
        content = _text(item.get("content"), 20_000)
        if not content:
            continue
        section = KnowledgeSection(item["section"])
        knowledge_changes.append(
            {
                "section": section.value,
                "title": _text(item.get("title"), 255) or "",
                "content": content,
                "mode": "replace" if section in _SINGLE_SECTIONS else "add",
            }
        )

    questions = [q for q in (_text(q, 500) for q in raw["questions"]) if q][:5]
    return {"products": product_changes, "knowledge": knowledge_changes, "questions": questions}


def _snapshot(product: Product) -> dict[str, Any]:
    return {
        "name": product.name,
        "sku": product.sku,
        "category": product.category,
        "color": product.color,
        "size": product.size,
        "price": products.price_number(product.price) if product.price is not None else None,
        "stock": product.stock,
        "description": product.description,
    }


# ---------------------------------------------------------------------------- proposals


async def propose(
    db: AsyncSession,
    llm: LLMClient,
    shop: Shop,
    text: str,
    *,
    source: str,
    label: str,
    image_url: str | None = None,
    context: str = "",
) -> TeachProposal:
    """Extract and store a proposal; the AI usage is paid from the wallet."""
    if not billing.can_spend(shop):
        raise TeachError("Your wallet is empty. Top it up to keep using this.")
    result = await extract(db, llm, shop, text, source, context)
    proposal = TeachProposal(
        shop_id=shop.id,
        source=source,
        source_label=label[:500],
        summary=result.summary,
        # The input is kept so a follow-up message can refine this proposal.
        changes={**result.changes, "input": text[:20_000]},
        image_url=image_url,
    )
    db.add(proposal)
    await db.commit()
    await billing.charge_usage(
        db,
        shop,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
        description="Learning shop information",
        details={"proposal_id": str(proposal.id), "source": source},
    )
    return proposal


def is_empty(proposal: TeachProposal) -> bool:
    changes = proposal.changes or {}
    return not (changes.get("products") or changes.get("knowledge") or changes.get("sheet"))


async def apply(
    db: AsyncSession,
    shop: Shop,
    proposal: TeachProposal,
    http: httpx.AsyncClient | None = None,
    *,
    skip_products: set[int] | None = None,
    skip_knowledge: set[int] | None = None,
) -> str:
    """Apply a pending proposal. Returns a description of what changed."""
    if proposal.status != ProposalStatus.PENDING:
        raise TeachError("This proposal was already applied or discarded.")
    settings = get_settings()
    skip_products = skip_products or set()
    skip_knowledge = skip_knowledge or set()
    changes = proposal.changes or {}
    created_ids: list[str] = []
    counts = {"created": 0, "updated": 0, "deleted": 0, "locked": 0, "skipped": 0, "knowledge": 0}

    total = (
        await db.scalar(select(func.count()).select_from(Product).where(Product.shop_id == shop.id))
        or 0
    )
    origin = ProductOrigin.TEACH
    for index, change in enumerate(changes.get("products") or []):
        if index in skip_products:
            continue
        if change.get("locked"):
            counts["locked"] += 1
            continue
        fields = dict(change.get("fields") or {})
        if "price" in fields and fields["price"] is not None:
            fields["price"] = Decimal(str(fields["price"]))
        if change["action"] == "create":
            if total >= settings.product_row_limit:
                counts["skipped"] += 1
                continue
            product = Product(
                shop_id=shop.id,
                origin=origin,
                extra={},
                image_url=proposal.image_url,
                **fields,
            )
            db.add(product)
            await db.flush()
            created_ids.append(str(product.id))
            total += 1
            counts["created"] += 1
            continue
        product = await db.get(Product, uuid.UUID(change["product_id"]))
        if product is None or product.shop_id != shop.id:
            counts["skipped"] += 1
            continue
        if change["action"] == "delete":
            await db.delete(product)
            counts["deleted"] += 1
        else:
            for key, value in fields.items():
                setattr(product, key, value)
            counts["updated"] += 1

    used = knowledge.total_chars(
        list(
            (
                await db.scalars(select(KnowledgeEntry).where(KnowledgeEntry.shop_id == shop.id))
            ).all()
        )
    )
    for index, change in enumerate(changes.get("knowledge") or []):
        if index in skip_knowledge:
            continue
        section = KnowledgeSection(change["section"])
        content = change["content"]
        if change.get("mode") == "replace":
            entry = await db.scalar(
                select(KnowledgeEntry).where(
                    KnowledgeEntry.shop_id == shop.id, KnowledgeEntry.section == section
                )
            )
            growth = len(content) - (len(entry.content) if entry else 0)
            if used + growth > settings.knowledge_char_limit:
                counts["skipped"] += 1
                continue
            if entry is None:
                db.add(KnowledgeEntry(shop_id=shop.id, section=section, content=content))
            else:
                entry.content = content
            used += growth
        else:
            growth = len(content) + len(change.get("title") or "")
            if used + growth > settings.knowledge_char_limit:
                counts["skipped"] += 1
                continue
            db.add(
                KnowledgeEntry(
                    shop_id=shop.id,
                    section=section,
                    title=change.get("title") or "",
                    content=content,
                )
            )
            used += growth
        counts["knowledge"] += 1

    sheet_note = ""
    sheet = changes.get("sheet")
    if sheet:
        sheet_note = await _connect_sheet(db, shop, sheet, http)

    proposal.status = ProposalStatus.APPLIED
    proposal.applied_at = utcnow()
    proposal.changes = {**changes, "created_ids": created_ids}
    proposal.result = describe_result(counts) + sheet_note
    await db.commit()
    return proposal.result


async def discard(db: AsyncSession, proposal: TeachProposal) -> None:
    if proposal.status == ProposalStatus.PENDING:
        proposal.status = ProposalStatus.DISCARDED
        await db.commit()


async def undo(db: AsyncSession, shop: Shop, proposal: TeachProposal) -> int:
    """Remove the products an applied proposal created (e.g. a channel post that wasn't a
    product after all). Updates and knowledge stay as they are."""
    ids = [uuid.UUID(i) for i in (proposal.changes or {}).get("created_ids", [])]
    if not ids:
        return 0
    result = await db.execute(
        delete(Product).where(Product.shop_id == shop.id, Product.id.in_(ids))
    )
    proposal.status = ProposalStatus.DISCARDED
    proposal.result = (proposal.result or "") + "\nUndone."
    await db.commit()
    return int(result.rowcount or 0)


def describe_result(counts: dict[str, int]) -> str:
    parts = []
    if counts["created"]:
        parts.append(_count(counts["created"], "product added", "products added"))
    if counts["updated"]:
        parts.append(_count(counts["updated"], "product updated", "products updated"))
    if counts["deleted"]:
        parts.append(_count(counts["deleted"], "product removed", "products removed"))
    if counts["knowledge"]:
        parts.append(
            _count(
                counts["knowledge"],
                "shop information entry saved",
                "shop information entries saved",
            )
        )
    if counts["locked"]:
        parts.append(
            f"{counts['locked']} from your Google Sheet (change those in the sheet itself)"
        )
    if counts["skipped"]:
        parts.append(f"{counts['skipped']} skipped (over the limit or already removed)")
    return "; ".join(parts) + "." if parts else "Nothing was changed."


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _fmt_number(value: Any) -> str:
    number = Decimal(str(value))
    return f"{int(number):,}" if number == number.to_integral_value() else f"{number:,.2f}"


def _fmt_price(value: Any) -> str:
    return _fmt_number(value) if value is not None else "no price"


def _product_line(fields: dict[str, Any]) -> str:
    name = fields.get("name") or ""
    variant = " ".join(v for v in (fields.get("color"), fields.get("size")) if v)
    parts = [f"{name} {variant}".strip()]
    if "price" in fields:
        parts.append(_fmt_price(fields["price"]))
    if "stock" in fields:
        parts.append(f"stock {fields['stock']}")
    return ", ".join(p for p in parts if p)


def describe(proposal: TeachProposal, max_lines: int = 30) -> str:
    """The proposal as a short message (the panel's preview)."""
    changes = proposal.changes or {}
    lines: list[str] = []
    if proposal.summary:
        lines.append(proposal.summary)
    product_lines: list[str] = []
    for change in changes.get("products") or []:
        lock = " 🔒 (change it in the Google Sheet)" if change.get("locked") else ""
        if change["action"] == "create":
            product_lines.append(f"➕ {_product_line(change['fields'])}")
        elif change["action"] == "delete":
            product_lines.append(f"🗑 Remove: {_product_line(change['before'] or {})}{lock}")
        else:
            before = change.get("before") or {}
            diffs = []
            for key, value in change["fields"].items():
                label = {
                    "price": "Price",
                    "stock": "Stock",
                    "name": "Name",
                    "color": "Colour",
                    "size": "Size",
                    "description": "Description",
                    "category": "Category",
                    "sku": "SKU",
                }.get(key, key)
                old = before.get(key)
                if key == "price":
                    diffs.append(f"{label}: {_fmt_price(old)} → {_fmt_price(value)}")
                elif key == "description":
                    diffs.append(label)
                else:
                    diffs.append(f"{label}: {old if old is not None else '-'} → {value}")
            name = " ".join(
                v for v in (before.get("name"), before.get("color"), before.get("size")) if v
            )
            product_lines.append(f"✏️ {name}: {', '.join(diffs)}{lock}")
    if product_lines:
        lines.append("")
        lines.extend(product_lines[:max_lines])
        if len(product_lines) > max_lines:
            lines.append(f"… and {len(product_lines) - max_lines} more")
    labels = {s.key.value: s.label for s in knowledge.SECTIONS}
    knowledge_lines = []
    for change in changes.get("knowledge") or []:
        label = labels.get(change["section"], change["section"])
        title = f" “{change['title']}”" if change.get("title") else ""
        verb = "updated" if change.get("mode") == "replace" else "added"
        knowledge_lines.append(f"📝 {label}{title}: {verb}")
    if knowledge_lines:
        lines.append("")
        lines.extend(knowledge_lines)
    sheet = changes.get("sheet")
    if sheet:
        lines.append("")
        lines.append(
            f"🔄 Live Google Sheet connection ({sheet.get('rows', 0)} rows); "
            "it's re-read every few minutes."
        )
    if changes.get("questions"):
        lines.append("")
        lines.extend(f"❓ {q}" for q in changes["questions"])
    if is_empty(proposal) and not changes.get("questions"):
        lines.append("I didn't find anything new to learn.")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------- inputs

_GOOGLE_HOSTS = {"docs.google.com", "drive.google.com"}
_DOC_PATH = re.compile(r"/document/d/([\w-]+)")
_SHEET_PATH = re.compile(r"/spreadsheets/d/([\w-]+)")
_DRIVE_FILE = re.compile(r"/file/d/([\w-]+)")
URL_PATTERN = re.compile(r"https?://\S+")


def is_sheet_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.hostname == "docs.google.com" and bool(_SHEET_PATH.search(parsed.path))


async def text_from_url(http: httpx.AsyncClient, llm: LLMClient, url: str) -> tuple[str, str]:
    """Download a Google Doc / Drive file the owner shared; returns (text, label).

    Only Google hosts are accepted, so the server can't be made to fetch arbitrary URLs.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or parsed.hostname not in _GOOGLE_HOSTS:
        raise TeachError(
            "Only Google Docs, Google Sheets and Google Drive file links are supported for "
            "now. You can also send the text directly."
        )
    doc = _DOC_PATH.search(parsed.path)
    if doc:
        export = f"https://docs.google.com/document/d/{doc.group(1)}/export?format=txt"
        data = await _download(http, export)
        return knowledge._decode(data), "Google Doc"
    if _SHEET_PATH.search(parsed.path):
        try:
            table = await products.fetch_table(http, url)
        except products.ProductSourceError as exc:
            raise TeachError(str(exc)) from None
        return table_to_text(table), "Google Sheet"
    drive = _DRIVE_FILE.search(parsed.path)
    if drive:
        data = await _download(
            http, f"https://drive.google.com/uc?export=download&id={drive.group(1)}"
        )
        return await text_from_file(_guess_name(data), data, llm), "Google Drive file"
    raise TeachError("This Google link can't be read.")


async def _download(http: httpx.AsyncClient, url: str) -> bytes:
    try:
        resp = await http.get(url, follow_redirects=True, timeout=30)
    except httpx.HTTPError as exc:
        raise TeachError("Couldn't reach Google. Please try again in a moment.") from exc
    content_type = resp.headers.get("content-type", "")
    if resp.status_code in (401, 403, 404) or "text/html" in content_type:
        raise TeachError(
            "The file isn't accessible. In Google, open Share and set "
            "“Anyone with the link” as Viewer."
        )
    if resp.is_error:
        raise TeachError("Google returned an error. Please try again in a moment.")
    if len(resp.content) > get_settings().upload_max_bytes:
        raise TeachError("The file is too large.")
    return resp.content


def _guess_name(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return "file.pdf"
    if data[:2] == b"PK":
        return "file.xlsx" if b"xl/" in data[:2000] else "file.docx"
    return "file.txt"


async def text_from_file(filename: str, data: bytes, llm: LLMClient) -> str:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".csv")):
        try:
            table = products.parse_table(data, "xlsx" if lower.endswith(".xlsx") else "csv")
        except products.ProductSourceError as exc:
            raise TeachError(str(exc)) from None
        return table_to_text(table)
    try:
        return await knowledge.extract_text(filename, data, llm)
    except knowledge.ExtractionError as exc:
        raise TeachError(str(exc)) from None


def table_to_text(table: products.Table) -> str:
    lines = [" | ".join(table.headers)]
    lines.extend(" | ".join(row.get(h, "") for h in table.headers) for row in table.rows)
    return "\n".join(lines)


async def sheet_proposal(
    db: AsyncSession, http: httpx.AsyncClient, shop: Shop, url: str
) -> TeachProposal | None:
    """A Google Sheet whose columns we recognise becomes a *live* source (re-read every few
    minutes), which keeps stock current. None if its layout needs the AI instead."""
    try:
        table = await products.fetch_table(http, url)
    except products.ProductSourceError as exc:
        raise TeachError(str(exc)) from None
    mapping = products.suggest_mapping(table.headers)
    if "name" not in mapping or not ({"price", "stock"} & mapping.keys()):
        return None
    labels = ", ".join(f"{products.FIELD_LABELS[f]} ← “{h}”" for f, h in mapping.items())
    proposal = TeachProposal(
        shop_id=shop.id,
        source="url",
        source_label=url[:500],
        summary=f"This Google Sheet is a product list. I matched the columns like this: {labels}",
        changes={
            "products": [],
            "knowledge": [],
            "questions": [],
            "sheet": {"url": url.strip(), "mapping": mapping, "rows": len(table.rows)},
        },
    )
    db.add(proposal)
    await db.commit()
    return proposal


async def _connect_sheet(
    db: AsyncSession, shop: Shop, sheet: dict[str, Any], http: httpx.AsyncClient | None
) -> str:
    if http is None:
        return "\nThe Google Sheet wasn't connected."
    source = await db.scalar(select(ProductSource).where(ProductSource.shop_id == shop.id))
    if source is None:
        source = ProductSource(shop_id=shop.id, kind=ProductSourceKind.GOOGLE_SHEET)
        db.add(source)
    source.kind = ProductSourceKind.GOOGLE_SHEET
    source.url = sheet["url"]
    source.column_mapping = sheet["mapping"]
    await db.flush()
    try:
        count = await products.sync_source(db, source, http)
    except products.ProductSourceError as exc:
        return f"\nReading the Google Sheet failed: {exc}"
    return f"\nThe Google Sheet is connected and {count} product rows were read."


async def propose_from_url(
    db: AsyncSession, http: httpx.AsyncClient, llm: LLMClient, shop: Shop, url: str
) -> TeachProposal:
    if is_sheet_url(url):
        proposal = await sheet_proposal(db, http, shop, url)
        if proposal is not None:
            return proposal
    text, label = await text_from_url(http, llm, url)
    return await propose(db, llm, shop, text, source="url", label=f"{label}: {url[:400]}")
