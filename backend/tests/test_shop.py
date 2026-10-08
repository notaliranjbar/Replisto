from httpx import AsyncClient


async def test_get_and_update_shop(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    shop = (await client.get("/api/v1/shop", headers=auth_headers)).json()
    assert shop["tone"] == "friendly"

    resp = await client.patch(
        "/api/v1/shop",
        headers=auth_headers,
        json={"tone": "formal", "use_emoji": False, "forbidden_rules": "No discounts"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tone"] == "formal"
    assert body["use_emoji"] is False
    assert body["forbidden_rules"] == "No discounts"
    assert body["name"] == shop["name"]  # untouched fields are kept


async def test_update_shop_validates(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.patch("/api/v1/shop", headers=auth_headers, json={"tone": "angry"})
    assert resp.status_code == 422
    resp = await client.patch("/api/v1/shop", headers=auth_headers, json={"name": ""})
    assert resp.status_code == 422
