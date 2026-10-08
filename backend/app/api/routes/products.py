import codecs
import csv
import io
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from app.api.deps import CurrentShop, DbSession, HttpClient
from app.api.uploads import read_upload
from app.core.config import get_settings
from app.core.i18n import localize
from app.core.timeutil import utcnow
from app.models import (
    Product,
    ProductOrigin,
    ProductSource,
    ProductSourceKind,
    Shop,
)
from app.services import products
from app.services.products import ProductSourceError

router = APIRouter(prefix="/products", tags=["products"])


class FieldOut(BaseModel):
    key: str
    label: str
    required: bool


class PreviewOut(BaseModel):
    headers: list[str]
    sample_rows: list[dict[str, str]]
    row_count: int
    # {our_field: sheet_header}; the panel lets the owner correct it before saving.
    suggested_mapping: dict[str, str]


class SheetPreviewIn(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


class SheetConnectIn(BaseModel):
    url: str = Field(min_length=10, max_length=2000)
    column_mapping: dict[str, str]


class SourceOut(BaseModel):
    connected: bool
    kind: Literal["google_sheet", "upload"] | None = None
    url: str | None = None
    column_mapping: dict[str, str] = {}
    product_count: int = 0
    last_synced_at: datetime | None = None
    # Message when the last sync failed (e.g. sheet no longer shared). The previous
    # product data stays in use until a sync succeeds.
    last_error: str | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str | None
    name: str
    category: str | None
    color: str | None
    size: str | None
    # In the shop's currency.
    price: Decimal | None
    # None: unknown; 0: out of stock.
    stock: int | None
    description: str | None
    extra: dict[str, Any]
    # How Replisto learned this product: manual | sheet | file | teach
    origin: ProductOrigin
    # False for rows read from a live Google Sheet: change them in the sheet instead.
    editable: bool = True
    image_url: str | None
    post_url: str | None
    # Exactly what the bot sees about this product when a customer asks.
    bot_view: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int


class ProductSummary(BaseModel):
    total: int
    in_stock: int
    out_of_stock: int
    # Stock not given (the bot then just says it's available to order).
    stock_unknown: int
    by_origin: dict[str, int]
    limit: int


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=120)
    color: str | None = Field(default=None, max_length=64)
    size: str | None = Field(default=None, max_length=64)
    price: Decimal | None = Field(
        default=None, ge=0, le=10**12, decimal_places=2, description="In the shop's currency"
    )
    stock: int | None = Field(default=None, ge=0, le=10**7)
    description: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=2000)
    post_url: str | None = Field(default=None, max_length=500)


class ProductPatch(BaseModel):
    """Only the fields sent are changed; send null to clear one (except name)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=120)
    color: str | None = Field(default=None, max_length=64)
    size: str | None = Field(default=None, max_length=64)
    price: Decimal | None = Field(
        default=None, ge=0, le=10**12, decimal_places=2, description="In the shop's currency"
    )
    stock: int | None = Field(default=None, ge=0, le=10**7)
    description: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=2000)
    post_url: str | None = Field(default=None, max_length=500)


SHEET_LOCKED = (
    "This product comes from your Google Sheet and is re-read from it every few minutes; "
    "change it in the sheet itself."
)


@router.get("/fields", response_model=list[FieldOut])
async def fields() -> list[FieldOut]:
    """Our product fields, for the column-mapping step."""
    return [
        FieldOut(key=f, label=localize(products.FIELD_LABELS[f]) or "", required=f == "name")
        for f in products.FIELDS
    ]


@router.get("/template.csv", response_class=Response)
async def template() -> Response:
    """A ready-made product table; opens correctly in Excel and imports into Google Sheets."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(products.TEMPLATE_HEADERS)
    writer.writerow(products.TEMPLATE_EXAMPLE)
    return Response(
        content=codecs.BOM_UTF8 + buffer.getvalue().encode(),  # BOM so Excel detects UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="products-template.csv"'},
    )


@router.post("/sheet/preview", response_model=PreviewOut)
async def preview_sheet(body: SheetPreviewIn, shop: CurrentShop, http: HttpClient) -> PreviewOut:
    try:
        table = await products.fetch_table(http, body.url)
    except ProductSourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return _preview(table)


@router.put("/sheet", response_model=SourceOut)
async def connect_sheet(
    body: SheetConnectIn, shop: CurrentShop, db: DbSession, http: HttpClient
) -> SourceOut:
    """Save the Google Sheet link + mapping and import it now. Re-synced every few minutes."""
    try:
        table = await products.fetch_table(http, body.url)
        products.validate_mapping(body.column_mapping, table.headers)
    except ProductSourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    source = await _upsert_source(
        db, shop, ProductSourceKind.GOOGLE_SHEET, body.url.strip(), body.column_mapping
    )
    try:
        await products.sync_source(db, source, http, table=table)
    except ProductSourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return await _source_out(db, shop)


@router.post("/file/preview", response_model=PreviewOut)
async def preview_file(file: UploadFile, shop: CurrentShop) -> PreviewOut:
    return _preview(await _parse_upload(file))


@router.post("/file", response_model=SourceOut)
async def import_file(
    file: UploadFile,
    shop: CurrentShop,
    db: DbSession,
    column_mapping: str = Form(description='JSON object, e.g. {"name": "Product name"}'),
) -> SourceOut:
    """One-off import of an Excel/CSV file (not re-synced; upload again to update)."""
    try:
        mapping = json.loads(column_mapping)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "column_mapping must be JSON"
        ) from None
    if not isinstance(mapping, dict) or not all(isinstance(v, str) for v in mapping.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid column_mapping")
    table = await _parse_upload(file)
    try:
        products.validate_mapping(mapping, table.headers)
    except ProductSourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    source = await _upsert_source(db, shop, ProductSourceKind.UPLOAD, None, mapping)
    await products.replace_products(db, source, products.rows_to_products(table, mapping))
    source.last_synced_at = utcnow()
    source.last_error = None
    await db.commit()
    return await _source_out(db, shop)


@router.post("/sync", response_model=SourceOut)
async def sync_now(shop: CurrentShop, db: DbSession, http: HttpClient) -> SourceOut:
    source = await _get_source(db, shop)
    if source is None or source.kind != ProductSourceKind.GOOGLE_SHEET:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No Google Sheet is connected.")
    try:
        await products.sync_source(db, source, http)
    except ProductSourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return await _source_out(db, shop)


@router.get("/source", response_model=SourceOut)
async def get_source(shop: CurrentShop, db: DbSession) -> SourceOut:
    return await _source_out(db, shop)


@router.delete("/source", status_code=status.HTTP_204_NO_CONTENT)
async def remove_source(shop: CurrentShop, db: DbSession) -> None:
    """Disconnect the product table and delete the products imported from it.

    Products added any other way (by hand, taught to the AI, channel posts) stay.
    """
    source = await _get_source(db, shop)
    if source is not None:
        await db.execute(delete(Product).where(Product.source_id == source.id))
        await db.delete(source)
        await db.commit()


@router.get("", response_model=ProductPage)
async def list_products(
    shop: CurrentShop,
    db: DbSession,
    q: str | None = Query(default=None, max_length=100, description="search name/code/text"),
    origin: ProductOrigin | None = None,
    stock: Literal["in_stock", "out_of_stock", "unknown"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ProductPage:
    """The shop's catalogue: everything Replisto knows, however it was taught. Searchable."""
    if q:
        found = await products.search_products(db, shop.id, q, limit=None)
        found = [p for p in found if _matches(p, origin, stock)]
        return ProductPage(
            items=await _out_many(db, found[offset : offset + limit]), total=len(found)
        )
    query = select(Product).where(Product.shop_id == shop.id)
    if origin is not None:
        query = query.where(Product.origin == origin)
    if stock == "in_stock":
        query = query.where(Product.stock > 0)
    elif stock == "out_of_stock":
        query = query.where(Product.stock == 0)
    elif stock == "unknown":
        query = query.where(Product.stock.is_(None))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(Product.name, Product.color, Product.size).offset(offset).limit(limit)
        )
    ).all()
    return ProductPage(items=await _out_many(db, list(rows)), total=total or 0)


@router.get("/summary", response_model=ProductSummary)
async def summary(shop: CurrentShop, db: DbSession) -> ProductSummary:
    rows = (await db.scalars(select(Product).where(Product.shop_id == shop.id))).all()
    by_origin: dict[str, int] = {}
    for p in rows:
        by_origin[p.origin.value] = by_origin.get(p.origin.value, 0) + 1
    return ProductSummary(
        total=len(rows),
        in_stock=sum(1 for p in rows if p.stock is not None and p.stock > 0),
        out_of_stock=sum(1 for p in rows if p.stock == 0),
        stock_unknown=sum(1 for p in rows if p.stock is None),
        by_origin=by_origin,
        limit=get_settings().product_row_limit,
    )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductIn, shop: CurrentShop, db: DbSession) -> ProductOut:
    """Add one product by hand."""
    await check_room(db, shop, 1)
    product = Product(shop_id=shop.id, origin=ProductOrigin.MANUAL, extra={})
    _apply(product, body.model_dump())
    db.add(product)
    await db.commit()
    return await _out(db, product)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> ProductOut:
    return await _out(db, await _get_product(db, shop, product_id))


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID, body: ProductPatch, shop: CurrentShop, db: DbSession
) -> ProductOut:
    """Change a product (price, stock, ...). Rows from a live Google Sheet can't be edited."""
    product = await _get_product(db, shop, product_id)
    if product.origin == ProductOrigin.SHEET:
        raise HTTPException(status.HTTP_409_CONFLICT, SHEET_LOCKED)
    _apply(product, body.model_dump(exclude_unset=True))
    await db.commit()
    return await _out(db, product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> None:
    product = await _get_product(db, shop, product_id)
    if product.origin == ProductOrigin.SHEET:
        raise HTTPException(status.HTTP_409_CONFLICT, SHEET_LOCKED)
    await db.delete(product)
    await db.commit()


def _apply(product: Product, values: dict[str, Any]) -> None:
    for field, raw in values.items():
        value = raw.strip() or None if isinstance(raw, str) else raw
        if field == "name" and not value:
            continue  # the name can be changed, never cleared
        if field == "price" and value is not None:
            value = Decimal(value)
        if field == "post_url" and value is not None:
            value = products.instagram_url(value) or value[:500]
        setattr(product, field, value)


def _matches(product: Product, origin: ProductOrigin | None, stock: str | None) -> bool:
    if origin is not None and product.origin != origin:
        return False
    if stock == "in_stock":
        return product.stock is not None and product.stock > 0
    if stock == "out_of_stock":
        return product.stock == 0
    if stock == "unknown":
        return product.stock is None
    return True


async def _get_product(db: DbSession, shop: Shop, product_id: uuid.UUID) -> Product:
    product = await db.get(Product, product_id)
    if product is None or product.shop_id != shop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


async def check_room(db: DbSession, shop: Shop, adding: int) -> None:
    limit = get_settings().product_row_limit
    count = await db.scalar(
        select(func.count()).select_from(Product).where(Product.shop_id == shop.id)
    )
    if (count or 0) + adding > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"This would go over the limit of {limit:,} products.",
        )


async def _out_many(db: DbSession, items: list[Product]) -> list[ProductOut]:
    out = []
    for product in items:
        item = ProductOut.model_validate(product)
        item.editable = product.origin != ProductOrigin.SHEET
        item.bot_view = products.product_for_bot(product)
        out.append(item)
    return out


async def _out(db: DbSession, product: Product) -> ProductOut:
    await db.refresh(product)
    return (await _out_many(db, [product]))[0]


def _preview(table: products.Table) -> PreviewOut:
    return PreviewOut(
        headers=table.headers,
        sample_rows=table.rows[:5],
        row_count=len(table.rows),
        suggested_mapping=products.suggest_mapping(table.headers),
    )


async def _parse_upload(file: UploadFile) -> products.Table:
    data = await read_upload(file)
    name = (file.filename or "").lower()
    if name.endswith(".xlsx"):
        kind = "xlsx"
    elif name.endswith(".csv"):
        kind = "csv"
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only .xlsx and .csv files are supported."
        )
    try:
        return products.parse_table(data, kind)
    except ProductSourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


async def _get_source(db: DbSession, shop: Shop) -> ProductSource | None:
    return await db.scalar(select(ProductSource).where(ProductSource.shop_id == shop.id))


async def _upsert_source(
    db: DbSession, shop: Shop, kind: ProductSourceKind, url: str | None, mapping: dict[str, str]
) -> ProductSource:
    source = await _get_source(db, shop)
    if source is None:
        source = ProductSource(shop_id=shop.id, kind=kind)
        db.add(source)
    source.kind = kind
    source.url = url
    source.column_mapping = mapping
    await db.commit()
    return source


async def _source_out(db: DbSession, shop: Shop) -> SourceOut:
    source = await _get_source(db, shop)
    if source is None:
        return SourceOut(connected=False)
    await db.refresh(source)
    count = await db.scalar(
        select(func.count()).select_from(Product).where(Product.source_id == source.id)
    )
    return SourceOut(
        connected=True,
        kind=source.kind.value,
        url=source.url,
        column_mapping=source.column_mapping,
        product_count=count or 0,
        last_synced_at=source.last_synced_at,
        last_error=localize(source.last_error),
    )
