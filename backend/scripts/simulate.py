"""Local stand-in for Meta, to exercise the DM pipeline before the Meta app is approved.

  # 1. attach a fake Instagram page to a registered user's shop and switch the bot on
  uv run python -m scripts.simulate link --email owner@shop.com

  # 2. send a signed webhook as if a customer had written to that page
  uv run python -m scripts.simulate dm --text "Hi, do you have this dress in M?"

  # a burst of short messages gets a single combined reply
  uv run python -m scripts.simulate dm --text "Hi" --text "this dress" --text "do you have M?"

  # 3. or as if the owner had answered by hand (pauses the bot for that customer)
  uv run python -m scripts.simulate dm --echo --text "Yes, it's in stock!"

  # 4. a comment under one of the page's posts (the bot answers publicly and/or by DM)
  uv run python -m scripts.simulate comment --text "How much is this?" --caption "Linen dress"

Run the API with QUEUE_BACKEND=inline and INSTAGRAM_DRY_RUN=true: the bot's reply then
shows up in the server log instead of being sent to Instagram.
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import time
import uuid

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import encrypt_secret
from app.models import InstagramAccount, InstagramPost, User
from app.services.instagram import SCOPES

FAKE_ACCOUNT_ID = "17840000000000000"
FAKE_CUSTOMER_ID = "1000000000000001"


async def link(email: str, ig_id: str, username: str) -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise SystemExit(f"no user with email {email}; register in the panel or /docs first")
        await db.refresh(user, ["shop"])
        account = await db.scalar(
            select(InstagramAccount).where(InstagramAccount.shop_id == user.shop.id)
        )
        if account is None:
            account = InstagramAccount(shop_id=user.shop.id)
            db.add(account)
        account.ig_user_id = ig_id
        account.username = username
        account.access_token_encrypted = encrypt_secret("fake-token")
        account.is_active = True
        account.scopes = ",".join(SCOPES)
        user.shop.bot_enabled = True
        await db.commit()
    print(f"linked @{username} ({ig_id}) to {email}'s shop; bot enabled")


def dm(url: str, texts: list[str], ig_id: str, customer_id: str, echo: bool) -> None:
    for text in texts:
        _send_one(url, text, ig_id, customer_id, echo)
        time.sleep(0.3)  # a realistic burst: faster than the reply debounce


async def _ensure_post(ig_id: str, media_id: str, caption: str) -> None:
    """The post the simulated comment is under, so the bot reads its caption."""
    async with SessionLocal() as db:
        account = await db.scalar(
            select(InstagramAccount).where(InstagramAccount.ig_user_id == ig_id)
        )
        if account is None:
            raise SystemExit("run `simulate link` first")
        post = await db.scalar(
            select(InstagramPost).where(
                InstagramPost.shop_id == account.shop_id, InstagramPost.ig_media_id == media_id
            )
        )
        if post is None:
            post = InstagramPost(
                shop_id=account.shop_id,
                ig_media_id=media_id,
                permalink=f"https://www.instagram.com/p/{media_id}/",
            )
            db.add(post)
        if caption:
            post.caption = caption
        await db.commit()


def comment(
    url: str, text: str, ig_id: str, commenter: str, username: str, media_id: str, caption: str
) -> None:
    asyncio.run(_ensure_post(ig_id, media_id, caption))
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": ig_id,
                "time": int(time.time()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "from": {"id": commenter, "username": username},
                            "media": {"id": media_id, "media_product_type": "FEED"},
                            "id": f"sim-comment-{uuid.uuid4().hex[:12]}",
                            "text": text,
                        },
                    }
                ],
            }
        ],
    }
    _post_signed(url, payload)


def _send_one(url: str, text: str, ig_id: str, customer_id: str, echo: bool) -> None:
    sender, recipient = (ig_id, customer_id) if echo else (customer_id, ig_id)
    message = {"mid": f"sim-{uuid.uuid4().hex}", "text": text} | ({"is_echo": True} if echo else {})
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": ig_id,
                "time": int(time.time()),
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": recipient},
                        "timestamp": int(time.time() * 1000),
                        "message": message,
                    }
                ],
            }
        ],
    }
    _post_signed(url, payload)


def _post_signed(url: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode()
    secret = get_settings().meta_app_secret
    if not secret:
        raise SystemExit("set META_APP_SECRET (any value locally) so the webhook can be signed")
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = httpx.post(
        url,
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    print(resp.status_code, resp.text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_link = sub.add_parser("link", help="attach a fake Instagram page to a shop")
    p_link.add_argument("--email", required=True)
    p_link.add_argument("--ig-id", default=FAKE_ACCOUNT_ID)
    p_link.add_argument("--username", default="test.shop")

    p_dm = sub.add_parser("dm", help="send a signed webhook for one DM")
    p_dm.add_argument(
        "--text", required=True, action="append", help="repeat to send a burst of messages"
    )
    p_dm.add_argument("--ig-id", default=FAKE_ACCOUNT_ID)
    p_dm.add_argument("--customer", default=FAKE_CUSTOMER_ID)
    p_dm.add_argument("--echo", action="store_true", help="message sent by the page owner")
    p_dm.add_argument("--url", default="http://127.0.0.1:8000/webhooks/instagram")

    p_comment = sub.add_parser("comment", help="send a signed webhook for one comment")
    p_comment.add_argument("--text", required=True)
    p_comment.add_argument("--caption", default="", help="caption of the post it's under")
    p_comment.add_argument("--media", default="sim-post-1", help="the post's media id")
    p_comment.add_argument("--ig-id", default=FAKE_ACCOUNT_ID)
    p_comment.add_argument("--commenter", default=FAKE_CUSTOMER_ID)
    p_comment.add_argument("--username", default="test.customer")
    p_comment.add_argument("--url", default="http://127.0.0.1:8000/webhooks/instagram")

    args = parser.parse_args()
    if args.command == "link":
        asyncio.run(link(args.email, args.ig_id, args.username))
    elif args.command == "comment":
        comment(
            args.url,
            args.text,
            args.ig_id,
            args.commenter,
            args.username,
            args.media,
            args.caption,
        )
    else:
        dm(args.url, args.text, args.ig_id, args.customer, args.echo)


if __name__ == "__main__":
    main()
