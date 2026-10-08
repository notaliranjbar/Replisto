"""Questions unrelated to the shop: a cheap check, a canned reply, no charge, then silence."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import as_utc, utcnow
from app.models import Conversation, Message, MessageSender, Shop, WalletEntry
from app.services.llm import LLMClient
from app.services.messaging import reply_to_conversation
from app.services.responder import ChatTurn, LLMResponder, Reply, looks_on_topic, off_topic_text
from tests.conftest import FakeMeta, FakeWeb
from tests.test_billing import shop as instagram_shop  # noqa: F401
from tests.test_responder import shop  # noqa: F401


@pytest.fixture
def guard_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "off_topic_guard", True)


def _responder(db: AsyncSession, fake_web: FakeWeb) -> LLMResponder:
    return LLMResponder(LLMClient(fake_web.client()), db)


async def test_unrelated_question_gets_the_canned_reply(
    db: AsyncSession,
    shop: Shop,  # noqa: F811
    fake_web: FakeWeb,
    llm_on: None,
    guard_on: None,
) -> None:
    fake_web.llm_replies = [FakeWeb.tool_call("classify", {"topic": "off_topic"})]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "what's the weather in Beirut today?")]
    )
    assert reply is not None and reply.off_topic
    assert "Layla Boutique" in reply.text and "products" in reply.text
    # Only the small check ran: no full answer with the shop's information.
    assert len(fake_web.llm_requests) == 1
    check = fake_web.llm_requests[0]
    assert check["tool_choice"]["function"]["name"] == "classify"
    assert "SHOP INFORMATION" not in check["messages"][0]["content"]
    assert reply.prompt_tokens == 100  # the check's tokens are still recorded


def test_the_redirect_speaks_the_customers_language(shop: Shop) -> None:  # noqa: F811
    assert "Layla Boutique" in off_topic_text(shop, "what's the weather?")
    assert "المنتجات" in off_topic_text(shop, "شو الطقس اليوم؟")
    assert "bas" in off_topic_text(shop, "kifak, shu el ta2es lyom?")
    assert "produits" in off_topic_text(shop, "bonjour, quel temps fait-il ?")


async def test_shopping_questions_skip_the_check(
    db: AsyncSession,
    shop: Shop,  # noqa: F811
    fake_web: FakeWeb,
    llm_on: None,
    guard_on: None,
) -> None:
    fake_web.llm_replies = [{"content": "Yes, it's in stock"}]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "is the linen dress still available?")]
    )
    assert reply is not None and not reply.off_topic
    assert len(fake_web.llm_requests) == 1
    assert "SHOP INFORMATION" in fake_web.llm_requests[0]["messages"][0]["content"]


async def test_unclear_questions_get_a_full_answer(
    db: AsyncSession,
    shop: Shop,  # noqa: F811
    fake_web: FakeWeb,
    llm_on: None,
    guard_on: None,
) -> None:
    fake_web.llm_replies = [
        FakeWeb.tool_call("classify", {"topic": "shop"}),
        {"content": "Three working days"},
    ]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "when would it reach me?")]
    )
    assert reply is not None and reply.text == "Three working days" and not reply.off_topic
    assert reply.prompt_tokens == 200  # the check and the answer


def test_keywords() -> None:
    assert looks_on_topic("how much is it?", [])
    assert looks_on_topic("adde 7a2o?", [])
    assert looks_on_topic("قديش سعرها؟", [])
    assert looks_on_topic("c'est combien ?", [])
    assert not looks_on_topic("what's the weather in Beirut", [])


class FixedResponder:
    def __init__(self, reply: Reply) -> None:
        self.reply = reply
        self.calls = 0

    async def generate(self, the_shop: Shop, history: list, **_: object) -> Reply:
        self.calls += 1
        return self.reply


async def _ask(db: AsyncSession, conversation: Conversation, text: str) -> None:
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.CUSTOMER,
            text=text,
            external_id=f"m-{uuid.uuid4()}",
        )
    )
    conversation.last_customer_message_at = utcnow()
    await db.commit()


async def test_canned_replies_are_free_then_the_bot_goes_quiet(
    db: AsyncSession,
    instagram_shop: Shop,  # noqa: F811
    fake_meta: FakeMeta,
    billing_on: None,
) -> None:
    conversation = Conversation(shop_id=instagram_shop.id, customer_id="c1")
    db.add(conversation)
    await db.commit()
    responder = FixedResponder(
        Reply(text="Only about the shop", off_topic=True, prompt_tokens=90, completion_tokens=5)
    )

    async def run() -> None:
        await reply_to_conversation(
            db,
            conversation.id,
            as_utc(conversation.last_customer_message_at),
            fake_meta.client(),
            responder,
        )

    for question in ("what's the weather?", "tell me a joke", "capital of France?"):
        await _ask(db, conversation, question)
        await run()

    bot_messages = (
        await db.scalars(select(Message).where(Message.sender == MessageSender.BOT))
    ).all()
    assert [m.off_topic for m in bot_messages] == [True, True]  # the third got no reply
    assert responder.calls == 2  # and no AI call at all
    assert (await db.scalars(select(WalletEntry))).all() == []  # never charged

    # A shopping question brings the bot back.
    responder.reply = Reply(text="Yes, in stock", prompt_tokens=4000, completion_tokens=150)
    await _ask(db, conversation, "how much is the linen dress?")
    await run()
    assert [m["message"]["text"] for m in fake_meta.sent][-1] == "Yes, in stock"
    assert len((await db.scalars(select(WalletEntry))).all()) == 1
