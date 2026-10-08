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
    user = User(email="owner@shop.com", password_hash="x")
    user.shop = Shop(name="Layla Boutique")
    db.add(user)
    await db.commit()
    return user.shop


async def test_text_becomes_products_and_knowledge(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on: None
) -> None:
    db.add(KnowledgeEntry(shop_id=shop.id, section=KnowledgeSection.SHIPPING, content="Post"))
    await db.commit()
    _propose(
        fake_web,
        summary="I understood two dress sizes and the shipping terms.",
        products=[
            {
                "name": "Linen dress",
                "color": "Black",
                "size": "M",
                "price": 125,
                "stock": 3,
            },
            {"name": "Linen dress", "color": "Black", "size": "L", "price": "$1,250.00"},
            {"description": "no name: ignored"},
        ],
        knowledge=[
            {"section": "shipping", "content": "Express post in 3 to 5 days, $8"},
            {"section": "faq", "title": "Material?", "content": "Premium linen"},
            {"section": "nonsense", "content": "x"},
        ],
    )
    llm = LLMClient(fake_web.client())
    proposal = await teach.propose(
        db, llm, shop, "Black linen dress in M and L, 125 dollars...", source="text", label="t"
    )
    changes = proposal.changes
    assert [c["action"] for c in changes["products"]] == ["create", "create"]
    assert changes["products"][1]["fields"]["price"] == 1250  # "$1,250.00" parsed
    assert [k["mode"] for k in changes["knowledge"]] == ["replace", "add"]
    # The AI saw the current single-section text so it can merge into it.
    system = fake_web.llm_requests[-1]["messages"][0]["content"]
    assert "[shipping]\nPost" in system
    assert "➕ Linen dress Black M" in teach.describe(proposal)

    result = await teach.apply(db, shop, proposal)
    assert "2 products added" in result
    rows = (await db.scalars(select(Product).order_by(Product.size))).all()
    assert [(p.size, p.stock, p.origin) for p in rows] == [
        ("L", None, ProductOrigin.TEACH),
        ("M", 3, ProductOrigin.TEACH),
    ]
    shipping = await db.scalar(
        select(KnowledgeEntry).where(KnowledgeEntry.section == KnowledgeSection.SHIPPING)
    )
    assert shipping is not None and shipping.content.startswith("Express post")
    with pytest.raises(teach.TeachError):
        await teach.apply(db, shop, proposal)  # only once


async def test_updates_use_refs_and_respect_the_sheet(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on: None
) -> None:
    db.add_all(
        [
            Product(shop_id=shop.id, name="Linen dress", size="M", price=125, stock=3, extra={}),
            Product(
                shop_id=shop.id,
                name="Silk blouse",
                price=89,
                stock=2,
                extra={},
                origin=ProductOrigin.SHEET,
            ),
            Product(shop_id=shop.id, name="Scarf", stock=1, extra={}),
        ]
    )
    await db.commit()
    _propose(
        fake_web,
        summary="You sold two dresses, the blouse price changed, and the scarf is no longer sold.",
        products=[
            # Refs follow the catalogue order: #1 Linen dress, #2 Scarf, #3 Silk blouse.
            {"ref": "#1", "stock": 1},
            {"ref": "#3", "price": 95},
            {"ref": "2", "delete": True},
            {"ref": "#99", "stock": 4},
        ],
    )
    proposal = await teach.propose(
        db, LLMClient(fake_web.client()), shop, "I sold two dresses...", source="text", label="v"
    )
    system = fake_web.llm_requests[-1]["messages"][0]["content"]
    assert "#1 | Linen dress | - | M | 125 | 3" in system
    assert "[sheet]" in system
    actions = [(c["action"], c["locked"]) for c in proposal.changes["products"]]
    assert actions == [("update", False), ("update", True), ("delete", False)]

    result = await teach.apply(db, shop, proposal)
    assert "1 from your Google Sheet" in result
    db.expire_all()
    rows = {p.name: p for p in (await db.scalars(select(Product))).all()}
    assert rows["Linen dress"].stock == 1
    assert rows["Silk blouse"].price == 89  # the sheet wins
    assert "Scarf" not in rows


async def test_panel_text_and_google_doc(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, llm_on: None
) -> None:
    fake_web.files["https://docs.google.com/document/d/DOC1/export?format=txt"] = (
        200,
        b"Price list\nLeather bag $190",
        "text/plain",
    )
    _propose(fake_web, summary="A bag", products=[{"name": "Leather bag", "price": 190}])
    resp = await client.post(
        f"{API}/url",
        json={"url": "https://docs.google.com/document/d/DOC1/edit?usp=sharing"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    proposal = resp.json()
    assert proposal["status"] == "pending" and "Leather bag" in proposal["preview"]
    assert "Leather bag $190" in fake_web.llm_requests[-1]["messages"][1]["content"]

    resp = await client.post(
        f"{API}/proposals/{proposal['id']}/apply", json={}, headers=auth_headers
    )
    assert resp.json()["status"] == "applied"
    products = (await client.get("/api/v1/products", headers=auth_headers)).json()
    assert [p["origin"] for p in products["items"]] == ["teach"]

    # Unticked items are skipped.
    _propose(fake_web, summary="two", products=[{"name": "A"}, {"name": "B"}])
    second = (
        await client.post(f"{API}/text", json={"text": "A and B"}, headers=auth_headers)
    ).json()
    await client.post(
        f"{API}/proposals/{second['id']}/apply", json={"skip_products": [0]}, headers=auth_headers
    )
    names = [
        p["name"]
        for p in (await client.get("/api/v1/products", headers=auth_headers)).json()["items"]
    ]
    assert sorted(names) == ["B", "Leather bag"]

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
    shop.balance_cents = 0
    await db.commit()
    resp = await client.post(f"{API}/text", json={"text": "Hi"}, headers=auth_headers)
    assert resp.status_code == 422 and "wallet" in resp.json()["detail"]
