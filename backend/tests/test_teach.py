"""Teaching Replisto in free form: text, documents and links become proposals the owner confirms."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeEntry, KnowledgeSection, Product, ProductOrigin, Shop, User
from app.services import teach
from app.services.llm import LLMClient
from tests.conftest import FakeWeb

API = "/api/v1/teach"


def _propose(fake_web: FakeWeb, **arguments) -> None:
    fake_web.llm_replies.append(FakeWeb.tool_call("propose_changes", arguments))


@pytest.fixture
async def shop(db: AsyncSession) -> Shop:
    user = User(email="owner@shop.ir", password_hash="x")
    user.shop = Shop(name="مزون مهسا")
    db.add(user)
    await db.commit()
    return user.shop


async def test_text_becomes_products_and_knowledge(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on: None
) -> None:
    db.add(KnowledgeEntry(shop_id=shop.id, section=KnowledgeSection.SHIPPING, content="پست"))
    await db.commit()
    _propose(
        fake_web,
        summary="دو سایز مانتو و شرایط ارسال را فهمیدم.",
        products=[
            {
                "name": "مانتو کتان",
                "color": "مشکی",
                "size": "44",
                "price_toman": 1250000,
                "stock": 3,
            },
            {"name": "مانتو کتان", "color": "مشکی", "size": "46", "price_toman": "۱٬۲۵۰٬۰۰۰"},
            {"description": "no name: ignored"},
        ],
        knowledge=[
            {"section": "shipping", "content": "پست پیشتاز ۳ تا ۵ روز، ۸۵ هزار تومان"},
            {"section": "faq", "title": "جنس؟", "content": "کتان ترک"},
            {"section": "nonsense", "content": "x"},
        ],
    )
    llm = LLMClient(fake_web.client())
    proposal = await teach.propose(
        db, llm, shop, "مانتو کتان مشکی ۴۴ و ۴۶ یک و دویست و پنجاه...", source="text", label="t"
    )
    changes = proposal.changes
    assert [c["action"] for c in changes["products"]] == ["create", "create"]
    assert changes["products"][1]["fields"]["price"] == 1250000  # Persian digits parsed
    assert [k["mode"] for k in changes["knowledge"]] == ["replace", "add"]
    # The AI saw the current single-section text so it can merge into it.
    system = fake_web.llm_requests[-1]["messages"][0]["content"]
    assert "[shipping]\nپست" in system
    assert "➕ مانتو کتان مشکی 44" in teach.describe(proposal)

    result = await teach.apply(db, shop, proposal)
    assert "2 محصول اضافه شد" in result
    rows = (await db.scalars(select(Product).order_by(Product.size))).all()
    assert [(p.size, p.stock, p.origin) for p in rows] == [
        ("44", 3, ProductOrigin.TEACH),
        ("46", None, ProductOrigin.TEACH),
    ]
    shipping = await db.scalar(
        select(KnowledgeEntry).where(KnowledgeEntry.section == KnowledgeSection.SHIPPING)
    )
    assert shipping is not None and shipping.content.startswith("پست پیشتاز")
    with pytest.raises(teach.TeachError):
        await teach.apply(db, shop, proposal)  # only once


async def test_updates_use_refs_and_respect_the_sheet(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on: None
) -> None:
    db.add_all(
        [
            Product(
                shop_id=shop.id, name="مانتو کتان", size="44", price=1250000, stock=3, extra={}
            ),
            Product(
                shop_id=shop.id,
                name="شومیز حریر",
                price=890000,
                stock=2,
                extra={},
                origin=ProductOrigin.SHEET,
            ),
            Product(shop_id=shop.id, name="شال", stock=1, extra={}),
        ]
    )
    await db.commit()
    _propose(
        fake_web,
        summary="دو تا مانتو فروختید، قیمت شومیز عوض شد، شال دیگر فروخته نمی‌شود.",
        products=[
            # Refs follow the catalogue order: #1 شال, #2 شومیز حریر, #3 مانتو کتان.
            {"ref": "#3", "stock": 1},
            {"ref": "#2", "price_toman": 950000},
            {"ref": "1", "delete": True},
            {"ref": "#99", "stock": 4},
        ],
    )
    proposal = await teach.propose(
        db, LLMClient(fake_web.client()), shop, "دو تا مانتو فروختم...", source="text", label="v"
    )
    system = fake_web.llm_requests[-1]["messages"][0]["content"]
    assert "#3 | مانتو کتان | - | 44 | 1,250,000 | 3" in system
    assert "[sheet]" in system
    actions = [(c["action"], c["locked"]) for c in proposal.changes["products"]]
    assert actions == [("update", False), ("update", True), ("delete", False)]

    result = await teach.apply(db, shop, proposal)
    assert "1 مورد مربوط به گوگل شیت" in result
    db.expire_all()
    rows = {p.name: p for p in (await db.scalars(select(Product))).all()}
    assert rows["مانتو کتان"].stock == 1
    assert rows["شومیز حریر"].price == 890000  # the sheet wins
    assert "شال" not in rows


async def test_panel_text_and_google_doc(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, llm_on: None
) -> None:
    fake_web.files["https://docs.google.com/document/d/DOC1/export?format=txt"] = (
        200,
        "لیست قیمت\nکیف چرم ۱.۹ میلیون".encode(),
        "text/plain",
    )
    _propose(fake_web, summary="یک کیف", products=[{"name": "کیف چرم", "price_toman": 1900000}])
    resp = await client.post(
        f"{API}/url",
        json={"url": "https://docs.google.com/document/d/DOC1/edit?usp=sharing"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    proposal = resp.json()
    assert proposal["status"] == "pending" and "کیف چرم" in proposal["preview"]
    assert "کیف چرم ۱.۹ میلیون" in fake_web.llm_requests[-1]["messages"][1]["content"]

    resp = await client.post(
        f"{API}/proposals/{proposal['id']}/apply", json={}, headers=auth_headers
    )
    assert resp.json()["status"] == "applied"
    products = (await client.get("/api/v1/products", headers=auth_headers)).json()
    assert [p["origin"] for p in products["items"]] == ["teach"]

    # Unticked items are skipped.
    _propose(fake_web, summary="دو", products=[{"name": "الف"}, {"name": "ب"}])
    second = (
        await client.post(f"{API}/text", json={"text": "الف و ب"}, headers=auth_headers)
    ).json()
    await client.post(
        f"{API}/proposals/{second['id']}/apply", json={"skip_products": [0]}, headers=auth_headers
    )
    names = [
        p["name"]
        for p in (await client.get("/api/v1/products", headers=auth_headers)).json()["items"]
    ]
    assert sorted(names) == ["ب", "کیف چرم"]

    pending = (
        await client.get(f"{API}/proposals", params={"status": "pending"}, headers=auth_headers)
    ).json()
    assert pending["total"] == 0


async def test_sheet_link_becomes_a_live_source(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, llm_on: None
) -> None:
    from tests.test_products import SHEET_URL, _serve_sheet

    _serve_sheet(fake_web)
    resp = await client.post(f"{API}/url", json={"url": SHEET_URL}, headers=auth_headers)
    proposal = resp.json()
    assert proposal["changes"]["sheet"]["rows"] == 4
    assert fake_web.llm_requests == []  # recognised columns: no AI needed
    await client.post(f"{API}/proposals/{proposal['id']}/apply", json={}, headers=auth_headers)
    source = (await client.get("/api/v1/products/source", headers=auth_headers)).json()
    assert source["connected"] and source["kind"] == "google_sheet"
    assert source["product_count"] == 4


async def test_other_hosts_are_refused(
    client: AsyncClient, auth_headers: dict, llm_on: None
) -> None:
    resp = await client.post(
        f"{API}/url", json={"url": "http://169.254.169.254/latest"}, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_empty_wallet_blocks_teaching(
    client: AsyncClient, auth_headers: dict, llm_on: None, billing_on: None, db: AsyncSession
) -> None:
    shop = await db.scalar(select(Shop))
    assert shop is not None
    shop.balance_rial = 0
    await db.commit()
    resp = await client.post(f"{API}/text", json={"text": "سلام"}, headers=auth_headers)
    assert resp.status_code == 422 and "کیف پول" in resp.json()["detail"]
