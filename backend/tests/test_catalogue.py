"""The product catalogue in Replisto: products added by hand, search, and how a live Google Sheet
coexists with products taught any other way."""

from httpx import AsyncClient

from tests.conftest import FakeWeb
from tests.test_products import SHEET_URL, _serve_sheet

API = "/api/v1/products"
MAPPING = {
    "name": "نام کالا",
    "color": "رنگ",
    "size": "سایز",
    "price": "قیمت (تومان)",
    "stock": "موجودی",
}


async def _add(client: AsyncClient, headers: dict, **fields) -> dict:
    resp = await client.post(API, json=fields, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_add_edit_and_delete_by_hand(client: AsyncClient, auth_headers: dict) -> None:
    product = await _add(
        client, auth_headers, name="  کیف چرم ", color="قهوه‌ای", price=1_900_000, stock=2
    )
    assert product["name"] == "کیف چرم"
    assert product["origin"] == "manual" and product["editable"]
    # The panel shows exactly what the bot will see.
    assert product["bot_view"] == {
        "name": "کیف چرم",
        "color": "قهوه‌ای",
        "price_toman": 1_900_000,
        "in_stock": True,
        "stock_count": 2,
    }

    resp = await client.patch(
        f"{API}/{product['id']}", json={"stock": 0, "color": None}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["stock"] == 0 and resp.json()["color"] is None
    assert resp.json()["name"] == "کیف چرم"  # untouched fields stay

    assert (await client.delete(f"{API}/{product['id']}", headers=auth_headers)).status_code == 204
    assert (await client.get(f"{API}/{product['id']}", headers=auth_headers)).status_code == 404


async def test_search_and_filters(client: AsyncClient, auth_headers: dict) -> None:
    await _add(client, auth_headers, name="مانتو کتان", color="مشکی", size="44", stock=3)
    await _add(client, auth_headers, name="مانتو کتان", color="سرمه‌ای", size="46", stock=0)
    await _add(client, auth_headers, name="شومیز حریر", description="یقه‌ی انگلیسی")

    found = (await client.get(API, params={"q": "مانتو"}, headers=auth_headers)).json()
    assert found["total"] == 2
    # Search also reads descriptions, and Arabic letters match Persian ones.
    found = (await client.get(API, params={"q": "انگليسي"}, headers=auth_headers)).json()
    assert [p["name"] for p in found["items"]] == ["شومیز حریر"]

    out = (await client.get(API, params={"stock": "out_of_stock"}, headers=auth_headers)).json()
    assert [p["color"] for p in out["items"]] == ["سرمه‌ای"]
    unknown = (await client.get(API, params={"stock": "unknown"}, headers=auth_headers)).json()
    assert unknown["total"] == 1

    summary = (await client.get(f"{API}/summary", headers=auth_headers)).json()
    assert summary["total"] == 3
    assert (summary["in_stock"], summary["out_of_stock"], summary["stock_unknown"]) == (1, 1, 1)
    assert summary["by_origin"] == {"manual": 3}


async def test_sheet_rows_are_locked_and_sync_keeps_other_products(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb
) -> None:
    manual = await _add(client, auth_headers, name="شال نخی", price=350_000)
    _serve_sheet(fake_web)
    resp = await client.put(
        f"{API}/sheet", json={"url": SHEET_URL, "column_mapping": MAPPING}, headers=auth_headers
    )
    assert resp.status_code == 200 and resp.json()["product_count"] == 4

    listing = (await client.get(API, params={"origin": "sheet"}, headers=auth_headers)).json()
    assert listing["total"] == 4
    sheet_row = listing["items"][0]
    assert not sheet_row["editable"]
    resp = await client.patch(f"{API}/{sheet_row['id']}", json={"stock": 9}, headers=auth_headers)
    assert resp.status_code == 409 and "گوگل شیت" in resp.json()["detail"]

    # Re-syncing replaces only the sheet's own rows.
    assert (await client.post(f"{API}/sync", headers=auth_headers)).status_code == 200
    assert (await client.get(API, headers=auth_headers)).json()["total"] == 5

    # Disconnecting the sheet removes its rows and nothing else.
    assert (await client.delete(f"{API}/source", headers=auth_headers)).status_code == 204
    left = (await client.get(API, headers=auth_headers)).json()
    assert [p["id"] for p in left["items"]] == [manual["id"]]


async def test_product_limit(client: AsyncClient, auth_headers: dict, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "product_row_limit", 1)
    await _add(client, auth_headers, name="یک")
    resp = await client.post(API, json={"name": "دو"}, headers=auth_headers)
    assert resp.status_code == 413
