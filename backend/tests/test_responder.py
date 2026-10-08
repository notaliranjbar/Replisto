import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeEntry, KnowledgeSection, Product, Shop
from app.services.llm import LLMClient, LLMError
from app.services.responder import ChatTurn, LLMResponder, history_to_messages
from tests.conftest import FakeWeb


@pytest.fixture
async def shop(db: AsyncSession) -> Shop:
    shop = Shop(
        owner_id=uuid.uuid4(),
        name="Layla Boutique",
        fallback_message="A teammate will reply soon",
        forbidden_rules="Never give discounts",
        use_emoji=False,
    )
    db.add(shop)
    await db.flush()
    db.add_all(
        [
            KnowledgeEntry(
                shop_id=shop.id, section=KnowledgeSection.SHIPPING, content="3-day express post"
            ),
            Product(
                shop_id=shop.id,
                name="Linen dress",
                color="Black",
                size="M",
                price=125,
                stock=3,
                extra={},
            ),
        ]
    )
    await db.commit()
    return shop


def _responder(db: AsyncSession, fake_web: FakeWeb) -> LLMResponder:
    return LLMResponder(LLMClient(fake_web.client()), db)


async def test_answers_from_product_lookup(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [
        FakeWeb.tool_call(
            "search_products", {"query": "Linen dress", "color": "Black", "size": "M"}
        ),
        {"content": "Yes, it's **in stock** and costs $125"},
    ]
    reply = await _responder(db, fake_web).generate(
        shop,
        [
            ChatTurn("customer", "Hi"),
            ChatTurn("customer", "Do you have the black linen dress in M?"),
        ],
    )
    assert reply is not None
    assert reply.text == "Yes, it's in stock and costs $125"  # markdown stripped
    assert reply.unanswered is False
    assert reply.prompt_tokens == 200 and reply.completion_tokens == 40  # two LLM calls

    [lookup] = reply.tool_trace
    assert lookup["result"]["matches"][0]["price"] == 125
    assert lookup["result"]["matches"][0]["in_stock"] is True

    first, second = fake_web.llm_requests
    system = first["messages"][0]["content"]
    assert "Layla Boutique" in system
    assert "3-day express post" in system
    assert "Never give discounts" in system
    assert "Never use emoji" in system
    assert "never offer or promise" in system  # no fake "I can register your order"
    # Consecutive customer messages are merged into one user turn.
    assert first["messages"][1] == {
        "role": "user",
        "content": "Hi\nDo you have the black linen dress in M?",
    }
    assert {t["function"]["name"] for t in first["tools"]} == {
        "search_products",
        "handoff_to_human",
    }
    # The tool result is sent back to the model for the second call.
    assert second["messages"][-1]["role"] == "tool"
    assert "125" in second["messages"][-1]["content"]


async def test_missing_variant_suggests_others(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [
        FakeWeb.tool_call("search_products", {"query": "Linen dress", "color": "Red"}),
        {"content": "We don't have it in red, but black is available"},
    ]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "Do you have it in red?")]
    )
    assert reply is not None
    result = reply.tool_trace[0]["result"]
    assert result["matches"] == []
    assert result["other_in_stock_variants"][0]["color"] == "Black"


async def test_handoff_sends_fallback_and_flags(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [FakeWeb.tool_call("handoff_to_human", {"reason": "asks for invoice"})]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "Do you issue formal invoices?")]
    )
    assert reply is not None
    assert reply.text == "A teammate will reply soon"
    assert reply.unanswered is True
    assert reply.handoff_reason == "asks for invoice"


async def test_no_product_tool_without_products(
    db: AsyncSession, fake_web: FakeWeb, llm_on
) -> None:
    shop = Shop(owner_id=uuid.uuid4(), name="No products")
    db.add(shop)
    await db.commit()
    fake_web.llm_replies = [{"content": "Hi, how can I help?"}]
    await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Hi")])
    tools = fake_web.llm_requests[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["handoff_to_human"]


async def test_endless_tool_calls_fall_back(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [FakeWeb.tool_call("search_products", {"query": "x"})] * 10
    reply = await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "?")])
    assert reply is not None and reply.unanswered
    assert len(fake_web.llm_requests) == 4  # capped


async def test_provider_errors(db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on) -> None:
    fake_web.llm_status = 429
    with pytest.raises(LLMError) as busy:
        await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Hi")])
    assert busy.value.retryable
    fake_web.llm_status = 401
    with pytest.raises(LLMError) as rejected:
        await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Hi")])
    assert not rejected.value.retryable


def test_history_starts_with_customer() -> None:
    messages = history_to_messages(
        [ChatTurn("owner", "Welcome"), ChatTurn("customer", "Hi"), ChatTurn("bot", "Hi!")]
    )
    assert [m["role"] for m in messages] == ["user", "assistant"]


async def test_playground(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [{"content": "We ship by express post"}]
    resp = await client.post(
        "/api/v1/playground/chat",
        headers=auth_headers,
        json={"messages": [{"role": "customer", "text": "How does shipping work?"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "We ship by express post"
    assert resp.json()["ai_ready"] is True

    ends_with_bot = await client.post(
        "/api/v1/playground/chat",
        headers=auth_headers,
        json={"messages": [{"role": "bot", "text": "Hi"}]},
    )
    assert ends_with_bot.status_code == 422

    fake_web.llm_status = 500
    down = await client.post(
        "/api/v1/playground/chat",
        headers=auth_headers,
        json={"messages": [{"role": "customer", "text": "Hi"}]},
    )
    assert down.status_code == 502


async def test_playground_without_ai(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/playground/chat",
        headers=auth_headers,
        json={"messages": [{"role": "customer", "text": "Hi"}]},
    )
    body = resp.json()
    assert body["ai_ready"] is False
    assert body["unanswered"] is True


async def test_adapts_to_models_that_reject_classic_parameters(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    """Newer models refuse max_tokens/temperature; switching model must stay a config change."""
    fake_web.llm_rejects = {"max_tokens", "temperature"}
    fake_web.llm_replies = [{"content": "Hi, how can I help?"}]
    reply = await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Hi")])
    assert reply is not None and reply.text == "Hi, how can I help?"
    final = fake_web.llm_requests[-1]
    assert "max_tokens" not in final and "temperature" not in final
    assert final["max_completion_tokens"] > 0


async def test_other_bad_requests_still_fail_clearly(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_status = 400
    with pytest.raises(LLMError) as exc_info:
        await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Hi")])
    assert not exc_info.value.retryable
    assert len(fake_web.llm_requests) == 1  # no pointless resends


async def test_handoff_keeps_the_part_the_bot_could_answer(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    """Asked about refunds when the shop only covers size exchange: say what's known, hand off."""
    fake_web.llm_replies = [
        FakeWeb.tool_call(
            "handoff_to_human",
            {
                "reason": "Refunds aren't in the shop information",
                "message": "Size exchanges are **possible** within 7 days of delivery. "
                "I'll pass your refund question to a colleague.",
                "answered_part": True,
            },
        )
    ]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "Can I return things?")]
    )
    assert reply is not None and reply.unanswered
    expected = (
        "Size exchanges are possible within 7 days of delivery. "
        "I'll pass your refund question to a colleague."
    )
    # One natural message written by the model, not the known part glued to the fallback.
    assert reply.partial_answer == expected
    assert reply.text == expected


async def test_plain_handoff_uses_the_models_own_words(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    """An Arabic customer must not get the shop's English template."""
    fake_web.llm_replies = [
        FakeWeb.tool_call(
            "handoff_to_human",
            {
                "reason": "Shipping to Canada isn't in the shop information",
                "message": "Good question! I'll ask a colleague about shipping to Canada.",
                "answered_part": False,
            },
        )
    ]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "do you ship to Ontario?")]
    )
    assert reply is not None and reply.unanswered
    assert reply.text == "Good question! I'll ask a colleague about shipping to Canada."
    assert reply.partial_answer is None  # nothing answered: not re-sent while waiting


async def test_sold_out_variant_offers_in_stock_alternatives(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    db.add(Product(shop_id=shop.id, name="Linen dress", color="Navy", size="M", stock=0, extra={}))
    await db.commit()
    fake_web.llm_replies = [
        FakeWeb.tool_call("search_products", {"query": "Linen dress", "color": "Navy"}),
        {"content": "Navy is sold out, but black is available"},
    ]
    reply = await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Navy?")])
    assert reply is not None
    result = reply.tool_trace[0]["result"]
    assert [m["in_stock"] for m in result["matches"]] == [False]
    # Only what can actually be sold is suggested.
    assert [(v["color"], v["in_stock"]) for v in result["other_in_stock_variants"]] == [
        ("Black", True)
    ]


async def test_prompt_has_catalogue_and_rules(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [{"content": "Hi"}]
    await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "What do you sell?")])
    system = fake_web.llm_requests[0]["messages"][0]["content"]
    assert "PRODUCT OVERVIEW" in system
    assert "- Linen dress; $125; colours in stock: Black; sizes in stock: M" in system
    assert '"A teammate will reply soon"' in system  # the owner's handoff wording, as a tone guide
    assert "Never hand these off" in system  # weather & small talk
    assert "shop's AI assistant" in system  # honest about being a bot
