"""Sharing the shop's Instagram posts: syncing them, linking products, choosing, sending."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import encrypt_secret
from app.core.timeutil import utcnow
from app.models import (
    Conversation,
    InstagramAccount,
    InstagramPost,
    Message,
    MessageSender,
    Product,
    Shop,
)
from app.services.llm import LLMClient
from app.services.messaging import handle_event, reply_to_conversation
from app.services.posts import PostLink, link_products, post_key, sync_posts
from app.services.responder import ChatTurn, LLMResponder, Reply
from app.services.webhook import MessagingEvent, parse_messaging_events
from tests.conftest import FakeMeta, FakeWeb, RecordingQueue

ACCOUNT = "17841400000000001"
CUSTOMER = "998877"


def _post(shop_id, media_id: str, code: str, caption: str, days_ago: int) -> InstagramPost:
    return InstagramPost(
        shop_id=shop_id,
        ig_media_id=media_id,
        permalink=f"https://www.instagram.com/p/{code}/",
        caption=caption,
        posted_at=utcnow() - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------- linking


def test_post_key_ignores_url_noise() -> None:
    assert post_key("https://www.instagram.com/p/AbC_1-2/?igsh=xyz") == "p/AbC_1-2"
    assert post_key("instagram.com/layla.shop/reel/Zz9/") == "reel/Zz9"
    assert post_key("https://example.com/p/AbC") is None


def test_link_products() -> None:
    shop_id = uuid.uuid4()
    posts = [
        _post(shop_id, "1", "OLD", "Black linen dress", 30),
        _post(shop_id, "2", "NEW", "New linen dress just arrived", 2),  # Arabic kaf, still a match
        _post(shop_id, "3", "SKU", "Summer collection, code S-220", 5),
        _post(shop_id, "4", "EXP", "A photo the page owner chose", 40),
    ]
    items = [
        Product(shop_id=shop_id, name="Linen dress", extra={}),
        Product(shop_id=shop_id, name="Silk blouse", sku="S-220", extra={}),
        # Owner's explicit link wins over any caption match.
        Product(
            shop_id=shop_id,
            name="Cotton scarf",
            post_url="https://instagram.com/p/EXP?utm=1",
            extra={},
        ),
        # Explicit link to a post we haven't read: still shareable, as a plain link.
        Product(
            shop_id=shop_id, name="Bag", post_url="https://www.instagram.com/p/GONE/", extra={}
        ),
        # "Dress" alone must not grab a post about another product.
        Product(shop_id=shop_id, name="Dress", extra={}),
    ]
    links = link_products(items, posts)
    assert links["Linen dress"].media_id == "2"  # newest matching post
    assert links["Silk blouse"].media_id == "3"  # by product code
    assert links["Cotton scarf"].media_id == "4"
    assert links["Bag"] == PostLink(None, "https://www.instagram.com/p/GONE/")
    assert "Dress" in links  # its name is inside "Linen dress" captions: acceptable, newest wins


async def test_sync_reads_all_pages(db: AsyncSession, fake_meta: FakeMeta) -> None:
    shop_id = uuid.uuid4()
    account = InstagramAccount(
        shop_id=shop_id, ig_user_id="1", username="s", access_token_encrypted=encrypt_secret("t")
    )
    db.add(account)
    db.add(_post(shop_id, "old", "GONE", "deleted on Instagram", 1))
    await db.commit()
    fake_meta.media = [
        {
            "id": f"m{i}",
            "permalink": f"https://www.instagram.com/p/C{i}/",
            "caption": f"Post {i}",
            "media_type": "IMAGE",
            "media_url": f"https://cdn.test/{i}.jpg",
            "timestamp": "2026-09-20T10:15:30+0000",
        }
        for i in range(5)
    ]
    assert await sync_posts(db, account, fake_meta.client()) == 5
    stored = (await db.scalars(select(InstagramPost).order_by(InstagramPost.ig_media_id))).all()
    assert [p.ig_media_id for p in stored] == ["m0", "m1", "m2", "m3", "m4"]  # "old" removed
    assert stored[0].posted_at == datetime(2026, 9, 20, 10, 15, 30, tzinfo=UTC)
    assert stored[0].preview_url == "https://cdn.test/0.jpg"
    assert account.posts_synced_at is not None


# ---------------------------------------------------------------- choosing (responder)


@pytest.fixture
async def shop(db: AsyncSession) -> Shop:
    shop = Shop(
        owner_id=uuid.uuid4(), name="Boutique", fallback_message="A teammate will reply soon"
    )
    db.add(shop)
    await db.flush()
    db.add_all(
        [
            Product(shop_id=shop.id, name="Linen dress", price=125, stock=3, extra={}),
            Product(shop_id=shop.id, name="Silk blouse", price=89, stock=7, extra={}),
            Product(shop_id=shop.id, name="Scarf", price=30, stock=2, extra={}),
            _post(shop.id, "m1", "MANTO", "New linen dress", 1),
            _post(shop.id, "m2", "HARIR", "White silk blouse", 2),
        ]
    )
    await db.commit()
    return shop


def _responder(db: AsyncSession, fake_web: FakeWeb) -> LLMResponder:
    return LLMResponder(LLMClient(fake_web.client()), db)


async def test_bot_shares_recommended_posts(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [
        FakeWeb.tool_call("share_posts", {"post_refs": ["P2", "P1", "P9"]}),
        {"content": "I'd suggest the silk blouse and the linen dress, I've sent you their posts"},
    ]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "What would you suggest for a party?")]
    )
    assert reply is not None
    # Refs follow the overview (cheapest first): P1 = Silk blouse (m2), P2 = Linen dress (m1).
    assert [p.media_id for p in reply.posts] == ["m1", "m2"]
    first = fake_web.llm_requests[0]
    system = first["messages"][0]["content"]
    # Products with a post are marked in the overview; the one without a post is not.
    assert "Linen dress; $125; post P" in system
    assert "- Scarf; $30" in system and "Scarf; $30; post" not in system
    assert "SHARING POSTS" in system
    assert "share_posts" in {t["function"]["name"] for t in first["tools"]}
    shared = fake_web.llm_requests[1]["messages"][-1]["content"]
    assert "P9" in shared and "unknown reference" in shared


async def test_no_share_tool_without_posts(db: AsyncSession, fake_web: FakeWeb, llm_on) -> None:
    shop = Shop(owner_id=uuid.uuid4(), name="No posts")
    db.add(shop)
    await db.flush()
    db.add(Product(shop_id=shop.id, name="Dress", extra={}))
    await db.commit()
    fake_web.llm_replies = [{"content": "Hi"}]
    await _responder(db, fake_web).generate(shop, [ChatTurn("customer", "Hi")])
    request = fake_web.llm_requests[0]
    assert "share_posts" not in {t["function"]["name"] for t in request["tools"]}
    assert "SHARING POSTS" not in request["messages"][0]["content"]


async def test_post_is_never_sent_twice(
    db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on
) -> None:
    fake_web.llm_replies = [
        FakeWeb.tool_call("share_posts", {"post_refs": ["P1", "P2"]}),
        {"content": "Here are the posts"},
    ]
    history = [
        ChatTurn("customer", "Do you have dresses?"),
        ChatTurn("bot", "[post] https://www.instagram.com/p/MANTO/"),
        ChatTurn("customer", "Show me something else too"),
    ]
    reply = await _responder(db, fake_web).generate(shop, history)
    assert reply is not None
    assert [p.permalink for p in reply.posts] == ["https://www.instagram.com/p/HARIR/"]


async def test_share_limit(db: AsyncSession, shop: Shop, fake_web: FakeWeb, llm_on) -> None:
    for i in range(3, 6):
        db.add(Product(shop_id=shop.id, name=f"Item {i}", price=i, extra={}))
        db.add(_post(shop.id, f"m{i}", f"K{i}", f"Item {i}", i))
    await db.commit()
    fake_web.llm_replies = [
        FakeWeb.tool_call("share_posts", {"post_refs": ["P1", "P2", "P3", "P4", "P5"]}),
        {"content": "ok"},
    ]
    reply = await _responder(db, fake_web).generate(
        shop, [ChatTurn("customer", "Show me everything")]
    )
    assert reply is not None and len(reply.posts) == 3


# ---------------------------------------------------------------- sending (messaging)


@pytest.fixture
async def live_shop(sessions: async_sessionmaker, db: AsyncSession) -> Shop:
    shop = Shop(owner_id=uuid.uuid4(), name="s", bot_enabled=True, fallback_message="teammate")
    db.add(shop)
    await db.flush()
    db.add(
        InstagramAccount(
            shop_id=shop.id,
            ig_user_id=ACCOUNT,
            username="s",
            access_token_encrypted=encrypt_secret("t"),
        )
    )
    await db.commit()
    return shop


class WithPosts:
    def __init__(self, *posts: PostLink) -> None:
        self.posts = list(posts)

    async def generate(self, shop: Shop, history: list[ChatTurn], **_: object) -> Reply:
        return Reply(text="I've sent you its post", posts=self.posts)


async def _ask(db, queue, fake_meta, responder, text: str = "Dress?") -> None:
    event = MessagingEvent(
        account_ig_id=ACCOUNT,
        customer_igsid=CUSTOMER,
        mid=f"m-{uuid.uuid4().hex}",
        text=text,
        is_echo=False,
        timestamp=utcnow(),
    )
    await handle_event(db, event, queue, debounce_seconds=0)
    for job in [j for j in queue.jobs if j.function == "reply_conversation"]:
        await reply_to_conversation(
            db,
            uuid.UUID(job.args[0]),
            datetime.fromisoformat(job.args[1]),
            fake_meta.client(),
            responder,
        )
    queue.jobs.clear()
    db.expire_all()


async def test_posts_are_sent_as_cards_after_the_text(
    db: AsyncSession, live_shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    responder = WithPosts(
        PostLink("m1", "https://www.instagram.com/p/MANTO/"),
        PostLink(None, "https://www.instagram.com/p/LINKONLY/"),
    )
    await _ask(db, queue, fake_meta, responder)
    assert [m["message"] for m in fake_meta.sent] == [
        {"text": "I've sent you its post"},
        {"attachment": {"type": "MEDIA_SHARE", "payload": {"id": "m1"}}},
        {"text": "https://www.instagram.com/p/LINKONLY/"},
    ]
    texts = [m.text for m in (await db.scalars(select(Message).order_by(Message.created_at)))]
    assert texts[-2:] == [
        "[post] https://www.instagram.com/p/MANTO/",
        "[post] https://www.instagram.com/p/LINKONLY/",
    ]


async def test_failed_post_card_falls_back_to_link(
    db: AsyncSession, live_shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    fake_meta.post_error = (400, {"error": {"message": "media not found", "code": 100}})
    await _ask(db, queue, fake_meta, WithPosts(PostLink("gone", "https://www.instagram.com/p/X/")))
    assert fake_meta.sent[-1]["message"] == {"text": "https://www.instagram.com/p/X/"}


async def test_echo_of_shared_post_is_not_the_owner(
    db: AsyncSession, live_shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    """Instagram echoes our post card back without text; it must not pause the bot."""
    # The echo arrives while our post message is still "in flight" (no mid yet).
    await _ask(db, queue, fake_meta, WithPosts())
    conversation = await db.scalar(select(Conversation))
    assert conversation is not None
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.BOT,
            text="[post] https://www.instagram.com/p/MANTO/",
        )
    )
    await db.commit()
    echo = MessagingEvent(
        account_ig_id=ACCOUNT,
        customer_igsid=CUSTOMER,
        mid="echo-1",
        text="",
        is_echo=True,
        timestamp=utcnow(),
        attachment_types=("share",),
    )
    await handle_event(db, echo, queue, debounce_seconds=0)
    db.expire_all()
    conversation = await db.scalar(select(Conversation))
    assert conversation is not None and conversation.bot_paused_until is None
    owner = await db.scalar(select(Message).where(Message.sender == MessageSender.OWNER))
    assert owner is None


def test_story_reply_is_marked() -> None:
    [event] = parse_messaging_events(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": ACCOUNT,
                    "messaging": [
                        {
                            "sender": {"id": CUSTOMER},
                            "recipient": {"id": ACCOUNT},
                            "timestamp": 1,
                            "message": {
                                "mid": "s1",
                                "text": "How much?",
                                "reply_to": {"story": {"id": "st1", "url": "https://x"}},
                            },
                        }
                    ],
                }
            ],
        }
    )
    assert event.display_text == "How much? [story_reply]"


# ---------------------------------------------------------------- panel


async def test_posts_endpoint(client: AsyncClient, auth_headers: dict, fake_meta: FakeMeta) -> None:
    # Connect the page (reads posts on connect), then look at the linking.
    fake_meta.media = [
        {
            "id": "m1",
            "permalink": "https://www.instagram.com/p/MANTO/",
            "caption": "New linen dress",
            "timestamp": "2026-09-20T10:15:30+0000",
        }
    ]
    url = (await client.get("/api/v1/instagram/connect-url", headers=auth_headers)).json()["url"]
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(url).query)["state"][0]
    await client.get("/api/v1/instagram/callback", params={"code": "c", "state": state})

    csv = b"Product name,Price\nLinen dress,125\nScarf,30\n"
    await client.post(
        "/api/v1/products/file",
        headers=auth_headers,
        files={"file": ("p.csv", csv, "text/csv")},
        data={"column_mapping": '{"name": "Product name", "price": "Price"}'},
    )
    body = (await client.get("/api/v1/instagram/posts", headers=auth_headers)).json()
    assert body["total"] == 1 and body["synced_at"] is not None
    assert body["items"][0]["products"] == ["Linen dress"]
    assert body["products_without_post"] == ["Scarf"]

    fake_meta.media = []
    synced = await client.post("/api/v1/instagram/posts/sync", headers=auth_headers)
    assert synced.status_code == 200 and synced.json()["total"] == 0


async def test_sync_requires_connected_page(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post("/api/v1/instagram/posts/sync", headers=auth_headers)
    assert resp.status_code == 400
