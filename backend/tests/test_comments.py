"""Comments on the shop's posts: the bot answers what it knows, the rest waits for the owner."""

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.core.timeutil import utcnow
from app.models import (
    CommentCategory,
    CommentStatus,
    Conversation,
    InstagramAccount,
    InstagramComment,
    InstagramPost,
    Message,
    MessageSender,
    Shop,
    User,
    WalletEntry,
)
from app.services import comments
from app.services.llm import LLMClient
from app.services.messaging import handle_event
from app.services.responder import LLMResponder, PlaceholderResponder
from app.services.webhook import CommentEvent, MessagingEvent, parse_comment_events
from tests.conftest import FakeMeta, FakeWeb, RecordingQueue

ACCOUNT = "17841400000000001"
COMMENTER = "556677"


@pytest.fixture
async def shop(db: AsyncSession) -> Shop:
    user = User(email="owner@shop.com", password_hash="x")
    user.shop = Shop(name="Layla Boutique", bot_enabled=True, comment_mode="both")
    db.add(user)
    await db.flush()
    db.add(
        InstagramAccount(
            shop_id=user.shop.id,
            ig_user_id=ACCOUNT,
            username="layla.boutique",
            access_token_encrypted=encrypt_secret("page-token"),
            scopes="instagram_business_basic,instagram_business_manage_messages,"
            "instagram_business_manage_comments",
        )
    )
    db.add(
        InstagramPost(
            shop_id=user.shop.id,
            ig_media_id="media-1",
            permalink="https://www.instagram.com/p/ABC/",
            caption="Linen summer dress, 4 colours #linen",
        )
    )
    await db.commit()
    return user.shop


def _event(text: str, comment_id: str = "c1", author: str = COMMENTER) -> CommentEvent:
    return CommentEvent(
        account_ig_id=ACCOUNT,
        comment_id=comment_id,
        text=text,
        author_id=author,
        author_username="rana.k",
        media_id="media-1",
        media_product_type="FEED",
        timestamp=utcnow(),
    )


def _responder(db: AsyncSession, fake_web: FakeWeb) -> LLMResponder:
    return LLMResponder(LLMClient(fake_web.client()), db)


def _decision(**arguments: object) -> dict:
    return FakeWeb.tool_call("respond_to_comment", dict(arguments))


async def _record_and_answer(
    db: AsyncSession,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    responder,  # type: ignore[no-untyped-def]
    event: CommentEvent,
) -> InstagramComment:
    comment = await comments.record_comment(db, event, queue, fake_meta.client())
    assert comment is not None
    comment_id = comment.id
    await comments.answer_comment(db, comment_id, fake_meta.client(), responder)
    db.expire_all()
    stored = await db.get(InstagramComment, comment_id)
    assert stored is not None
    return stored


def test_webhook_comments_are_parsed_and_own_replies_dropped() -> None:
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": ACCOUNT,
                "time": 1791500000,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "from": {"id": COMMENTER, "username": "rana.k"},
                            "media": {"id": "media-1", "media_product_type": "REELS"},
                            "id": "c1",
                            "text": "Price?",
                        },
                    },
                    {
                        "field": "comments",
                        "value": {
                            "from": {"id": ACCOUNT, "username": "layla.boutique"},
                            "media": {"id": "media-1"},
                            "id": "c2",
                            "parent_id": "c1",
                            "text": "Sent you a DM!",
                        },
                    },
                ],
            }
        ],
    }
    [event] = parse_comment_events(payload)
    assert event.comment_id == "c1"
    assert event.author_username == "rana.k"
    assert event.media_product_type == "REELS"


async def test_signed_comment_webhook_is_queued(client: AsyncClient, queue: RecordingQueue) -> None:
    body = json.dumps(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": ACCOUNT,
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "from": {"id": COMMENTER},
                                "media": {"id": "media-1"},
                                "id": "c9",
                                "text": "available in M?",
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()
    signature = hmac.new(b"ig-app-secret", body, hashlib.sha256).hexdigest()
    resp = await client.post(
        "/webhooks/instagram",
        content=body,
        headers={"X-Hub-Signature-256": f"sha256={signature}", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    [job] = queue.jobs
    assert job.function == "process_comment"
    assert job.job_id == "comment:c9"


async def test_answer_by_dm_with_a_public_note(
    db: AsyncSession,
    shop: Shop,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
    billing_on: None,
) -> None:
    shop.balance_cents = 500
    await db.commit()
    shop_id = shop.id
    fake_web.llm_replies.append(
        _decision(
            decision="answer",
            category="price",
            private_reply="Hi Rana! The linen dress is $45, in 4 colours.",
            public_reply="Sent you the details in a message 💌",
        )
    )
    comment = await _record_and_answer(
        db, queue, fake_meta, _responder(db, fake_web), _event("How much is it?")
    )

    # The bot saw the post's caption, so it knows "it" is the linen dress.
    system = fake_web.llm_requests[0]["messages"][0]["content"]
    assert "Linen summer dress" in system
    [dm] = fake_meta.sent
    assert dm["recipient"] == {"comment_id": "c1"}
    assert dm["message"]["text"].startswith("Hi Rana!")
    assert fake_meta.public_replies == [
        {"comment_id": "c1", "message": "Sent you the details in a message 💌"}
    ]
    assert comment.status == CommentStatus.ANSWERED
    assert comment.category == CommentCategory.PRICE
    assert comment.private_reply_sent and comment.public_reply_id == "reply-1"

    # The private reply opens the commenter's DM thread, so a reply there has context.
    conversation = await db.scalar(
        select(Conversation).where(Conversation.customer_id == COMMENTER)
    )
    assert conversation is not None and conversation.customer_username == "rana.k"
    texts = [
        (m.sender, m.text)
        for m in await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    ]
    assert texts == [
        (MessageSender.CUSTOMER, "[comment] How much is it?"),
        (MessageSender.BOT, "Hi Rana! The linen dress is $45, in 4 colours."),
    ]
    # Charged once, like a DM answer.
    entry = await db.scalar(select(WalletEntry).where(WalletEntry.shop_id == shop_id))
    assert entry is not None and entry.description == "Comment reply on Instagram"


async def test_private_reply_echo_is_not_mistaken_for_the_owner(
    db: AsyncSession,
    shop: Shop,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
) -> None:
    fake_web.llm_replies.append(
        _decision(decision="answer", category="price", private_reply="It's $45.")
    )
    await _record_and_answer(db, queue, fake_meta, _responder(db, fake_web), _event("price?"))
    await handle_event(
        db,
        MessagingEvent(
            account_ig_id=ACCOUNT,
            customer_igsid=COMMENTER,
            mid="bot-mid-1",
            text="It's $45.",
            is_echo=True,
            timestamp=utcnow(),
        ),
        queue,
        debounce_seconds=5,
    )
    conversation = await db.scalar(
        select(Conversation).where(Conversation.customer_id == COMMENTER)
    )
    assert conversation is not None and conversation.bot_paused_until is None


async def test_public_mode_replies_under_the_comment_only(
    db: AsyncSession,
    shop: Shop,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
) -> None:
    shop.comment_mode = "public"
    await db.commit()
    fake_web.llm_replies.append(
        _decision(decision="answer", category="availability", public_reply="Yes, M is in stock!")
    )
    comment = await _record_and_answer(
        db, queue, fake_meta, _responder(db, fake_web), _event("Do you have M?")
    )
    assert fake_meta.sent == []
    assert fake_meta.public_replies == [{"comment_id": "c1", "message": "Yes, M is in stock!"}]
    assert comment.status == CommentStatus.ANSWERED


async def test_unknown_question_is_left_for_the_owner_without_replying(
    db: AsyncSession,
    shop: Shop,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
) -> None:
    fake_web.llm_replies.append(
        _decision(
            decision="unknown",
            category="order",
            reason="Delivery to Tripoli isn't in the shop information",
        )
    )
    comment = await _record_and_answer(
        db, queue, fake_meta, _responder(db, fake_web), _event("Do you deliver to Tripoli?")
    )
    assert fake_meta.sent == [] and fake_meta.public_replies == []
    assert comment.status == CommentStatus.UNANSWERED
    assert comment.category == CommentCategory.ORDER
    assert comment.reason == "Delivery to Tripoli isn't in the shop information"


async def test_emoji_praise_gets_a_heart_without_the_ai(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta, fake_web: FakeWeb
) -> None:
    comment = await _record_and_answer(
        db, queue, fake_meta, _responder(db, fake_web), _event("😍😍🔥")
    )
    assert fake_web.llm_requests == []
    assert fake_meta.public_replies == [{"comment_id": "c1", "message": "🙏🤍"}]
    assert comment.category == CommentCategory.PRAISE

    tagged = await _record_and_answer(
        db, queue, fake_meta, _responder(db, fake_web), _event("@maya @lina", comment_id="c2")
    )
    assert tagged.status == CommentStatus.SKIPPED
    assert len(fake_meta.public_replies) == 1


async def test_spam_is_skipped_and_hidden_when_asked(
    db: AsyncSession,
    shop: Shop,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
) -> None:
    shop.comment_hide_spam = True
    await db.commit()
    fake_web.llm_replies.append(_decision(decision="ignore", category="spam"))
    comment = await _record_and_answer(
        db, queue, fake_meta, _responder(db, fake_web), _event("Get 10k followers at cheap.biz")
    )
    assert comment.status == CommentStatus.SKIPPED and comment.hidden
    assert fake_meta.hidden == {"c1": True}


async def test_comments_off_or_no_ai_wait_for_the_owner(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    shop.comment_mode = "off"
    await db.commit()
    comment = await _record_and_answer(
        db, queue, fake_meta, PlaceholderResponder(), _event("price?")
    )
    assert comment.status == CommentStatus.UNANSWERED
    assert comment.reason == comments.REASON_OFF

    shop.comment_mode = "both"
    await db.commit()
    comment = await _record_and_answer(
        db, queue, fake_meta, PlaceholderResponder(), _event("price?", comment_id="c2")
    )
    assert comment.status == CommentStatus.UNANSWERED
    assert fake_meta.sent == [] and fake_meta.public_replies == []


async def test_temporary_instagram_error_is_retried(
    db: AsyncSession,
    shop: Shop,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    llm_on: None,
) -> None:
    shop.comment_mode = "public"
    await db.commit()
    fake_meta.reply_error = (500, {"error": {"message": "busy", "code": 2}})
    fake_web.llm_replies.append(_decision(decision="answer", category="price", public_reply="$45"))
    comment = await comments.record_comment(db, _event("price?"), queue, fake_meta.client())
    assert comment is not None
    comment_id = comment.id
    with pytest.raises(Exception, match="busy"):
        await comments.answer_comment(db, comment_id, fake_meta.client(), _responder(db, fake_web))
    db.expire_all()
    assert (await db.get(InstagramComment, comment_id)).status == CommentStatus.PENDING


async def _seed_comment(db: AsyncSession, shop: Shop, **values: object) -> InstagramComment:
    comment = InstagramComment(
        shop_id=shop.id,
        ig_comment_id=values.pop("ig_comment_id", f"c-{uuid.uuid4().hex[:6]}"),
        author_id=COMMENTER,
        author_username="rana.k",
        text=values.pop("text", "Do you deliver to Tripoli?"),
        commented_at=utcnow() - timedelta(minutes=5),
        **values,
    )
    db.add(comment)
    await db.commit()
    return comment


async def _panel_shop(db: AsyncSession) -> Shop:
    """The shop the test client registered (auth_headers)."""
    user = await db.scalar(select(User).where(User.email == "owner@shop.com"))
    await db.refresh(user, ["shop"])
    db.add(
        InstagramAccount(
            shop_id=user.shop.id,
            ig_user_id=ACCOUNT,
            username="layla.boutique",
            access_token_encrypted=encrypt_secret("page-token"),
            scopes="instagram_business_manage_comments",
        )
    )
    await db.commit()
    return user.shop


async def test_panel_lists_waiting_comments_by_category_and_owner_replies(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    fake_meta: FakeMeta,
    queue: RecordingQueue,
) -> None:
    shop = await _panel_shop(db)
    waiting = await _seed_comment(
        db,
        shop,
        ig_comment_id="c-wait",
        status=CommentStatus.UNANSWERED,
        category=CommentCategory.ORDER,
        reason="The bot is switched off",
    )
    await _seed_comment(
        db,
        shop,
        status=CommentStatus.UNANSWERED,
        category=CommentCategory.COMPLAINT,
        text="My order is late!",
    )
    await _seed_comment(db, shop, status=CommentStatus.ANSWERED, category=CommentCategory.PRICE)

    resp = await client.get("/api/v1/comments", headers=auth_headers)
    body = resp.json()
    assert body["available"] is True
    assert body["counts"]["waiting"] == 2 and body["counts"]["answered"] == 1
    assert body["counts"]["waiting_by_category"] == {"order": 1, "complaint": 1}

    resp = await client.get(
        "/api/v1/comments?category=order",
        headers={**auth_headers, "Accept-Language": "ar"},
    )
    [item] = resp.json()["items"]
    assert item["reason"] == "البوت متوقف"

    resp = await client.post(
        f"/api/v1/comments/{waiting.id}/reply",
        json={"text": "Yes, 3 days to Tripoli!", "private": False},
        headers=auth_headers,
    )
    assert resp.json()["status"] == "owner_replied"
    assert fake_meta.public_replies[-1] == {
        "comment_id": "c-wait",
        "message": "Yes, 3 days to Tripoli!",
    }

    other = (await client.get("/api/v1/comments", headers=auth_headers)).json()["items"][0]
    resp = await client.post(f"/api/v1/comments/{other['id']}/retry", headers=auth_headers)
    assert resp.json()["status"] == "pending"
    assert queue.jobs[-1].function == "answer_comment"

    resp = await client.post(f"/api/v1/comments/{other['id']}/dismiss", headers=auth_headers)
    assert resp.json()["status"] == "dismissed"
    resp = await client.post(
        f"/api/v1/comments/{other['id']}/hide", json={"hidden": True}, headers=auth_headers
    )
    assert resp.json()["hidden"] is True


async def test_owner_can_send_only_one_private_reply(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession, fake_meta: FakeMeta
) -> None:
    shop = await _panel_shop(db)
    comment = await _seed_comment(db, shop, status=CommentStatus.UNANSWERED)
    url = f"/api/v1/comments/{comment.id}/reply"
    first = await client.post(url, json={"text": "Sent!", "private": True}, headers=auth_headers)
    assert first.status_code == 200 and first.json()["private_reply_sent"]
    assert fake_meta.sent[0]["recipient"] == {"comment_id": comment.ig_comment_id}
    again = await client.post(url, json={"text": "Again", "private": True}, headers=auth_headers)
    assert again.status_code == 400


async def test_try_a_comment_follows_the_mode(
    client: AsyncClient,
    auth_headers: dict[str, str],
    fake_web: FakeWeb,
    llm_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key")
    fake_web.llm_replies.append(
        _decision(
            decision="answer",
            category="price",
            private_reply="It's $45 in all colours.",
            public_reply="Check your DMs 💌",
        )
    )
    resp = await client.post(
        "/api/v1/comments/try",
        json={"text": "price?", "post_caption": "Linen dress"},
        headers=auth_headers,
    )
    body = resp.json()
    assert body["decision"] == "answer"
    assert body["private_reply"] == "It's $45 in all colours."
    assert body["public_reply"] == "Check your DMs 💌"

    await client.patch("/api/v1/shop", json={"comment_mode": "public"}, headers=auth_headers)
    fake_web.llm_replies.append(
        _decision(decision="answer", category="price", private_reply="It's $45.")
    )
    body = (
        await client.post("/api/v1/comments/try", json={"text": "price?"}, headers=auth_headers)
    ).json()
    assert body["public_reply"] == "It's $45." and body["private_reply"] == ""


async def test_story_reply_tells_the_bot_what_the_story_was(
    db: AsyncSession, shop: Shop, queue: RecordingQueue
) -> None:
    from app.models import ScheduledStory, StoryStatus

    db.add(
        ScheduledStory(
            shop_id=shop.id,
            media_kind="image",
            file_name="x.jpg",
            content_type="image/jpeg",
            token="t",
            note="New linen dresses, $45, sizes S-L",
            scheduled_at=utcnow(),
            status=StoryStatus.PUBLISHED,
            ig_media_id="story-77",
        )
    )
    await db.commit()
    await handle_event(
        db,
        MessagingEvent(
            account_ig_id=ACCOUNT,
            customer_igsid=COMMENTER,
            mid="m-story",
            text="in L?",
            is_echo=False,
            timestamp=utcnow(),
            attachment_types=("story_reply",),
            story_id="story-77",
        ),
        queue,
        debounce_seconds=5,
    )
    message = await db.scalar(select(Message).where(Message.external_id == "m-story"))
    assert message is not None
    assert message.text == "in L? [story_reply: New linen dresses, $45, sizes S-L]"


def test_the_story_marker_is_parsed_with_its_id() -> None:
    from app.services.webhook import parse_messaging_events

    [event] = parse_messaging_events(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": ACCOUNT,
                    "messaging": [
                        {
                            "sender": {"id": COMMENTER},
                            "recipient": {"id": ACCOUNT},
                            "timestamp": 1791500000000,
                            "message": {
                                "mid": "m1",
                                "text": "love it",
                                "reply_to": {"story": {"id": "story-77", "url": "https://x"}},
                            },
                        }
                    ],
                }
            ],
        }
    )
    assert event.story_id == "story-77"
    assert event.display_text == "love it [story_reply]"
