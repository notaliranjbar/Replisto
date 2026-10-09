"""Create (or refresh) Replisto's own shop: the "Ask Replisto" assistant on the website.

    uv run python -m scripts.seed_house --email team@example.com
    uv run python -m scripts.seed_house --email team@example.com --reset-knowledge

The shop belongs to the given account (created with a printed random password if it doesn't
exist), is marked `is_house` and gets a first version of what Replisto is. From then on the
team keeps it up to date like any shop: log in with that account and edit "Business info".
Its prices come live from the server's settings, so they are not written here. Its chats show
up in that account's inbox, and questions it can't answer are emailed to that account.
"""

import argparse
import asyncio
import secrets
import sys

from sqlalchemy import delete, select, update

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.models import KnowledgeEntry, KnowledgeSection, Shop, User

KNOWLEDGE: list[tuple[KnowledgeSection, str, str]] = [
    (
        KnowledgeSection.ABOUT,
        "What Replisto is",
        "Replisto is an AI assistant for online shops and small businesses. It answers customers' "
        "messages in seconds, day and night, using only the shop's own information and product "
        "list: prices, stock, sizes and colours, delivery, payment and the usual questions. It "
        "never makes things up: when the answer isn't in the shop's information, it tells the "
        "customer a colleague will reply and hands the conversation to the owner. It replies in "
        "the customer's language and script, including Lebanese Arabic, Arabizi, French and "
        "English. Today it works on Instagram (direct messages, story replies and comments), "
        "plus a chat widget like this one.",
    ),
    (
        KnowledgeSection.FREE_TEXT,
        "Comments, stories and insights",
        "Comments: it answers comments under your posts and reels, using the post's caption to "
        "know which product 'how much?' is about. You choose how: a public reply under the "
        "comment, a private message to the commenter, or both (the answer by DM and a short "
        "public note). What it doesn't know, it doesn't reply to: the comment waits for you in "
        "the panel, sorted by topic (price, stock, ordering, complaint...). It can thank people "
        "for compliments and hide spam. You can try any comment in the panel first.\n"
        "Stories: upload story photos or videos and choose when each goes live; Replisto "
        "publishes them on time. You add a line about what each story shows, so when someone "
        "replies to the story the assistant knows what they mean.\n"
        "Insights: it reads your page's reach, engagement, followers and each post's numbers and "
        "shows what works (format, best days and hours, hashtags). An AI content assistant turns "
        "them into ideas, captions and a weekly plan, and answers questions like 'what should I "
        "post this week?'. Comment replies and the content assistant are paid from the wallet "
        "like any answer; skipped comments cost nothing.",
    ),
    (
        KnowledgeSection.FREE_TEXT,
        "Getting started",
        "1. Create a free account and confirm your email.\n"
        "2. Connect your Instagram professional account (Instagram's official login; we never "
        "ask for your password).\n"
        "3. Teach it your products and business info (see below).\n"
        "4. Try it on the test page, asking as a customer would.\n"
        "5. Turn it on. It usually takes 10 to 15 minutes and no technical skills.",
    ),
    (
        KnowledgeSection.FREE_TEXT,
        "Teaching it your products",
        "Any way you like: describe products in your own words, upload a PDF, Word or Excel "
        "file or a photo of your price list, or paste a Google Sheet or Google Doc link. A "
        "Google Sheet with clear columns stays connected and is re-read every few minutes. "
        "Before saving, it shows you a summary of what it understood for your OK, and you can "
        "edit any product by hand in the catalogue.",
    ),
    (
        KnowledgeSection.FREE_TEXT,
        "Staying in control",
        "You choose its tone (friendly or formal, with or without emoji) and rules it must "
        "always follow, like 'never offer discounts'. When you reply to a customer yourself it "
        "steps back in that conversation. Questions it couldn't answer are listed so you can "
        "add the answer once. Questions unrelated to your shop get a short polite reply and "
        "cost you nothing.",
    ),
    (
        KnowledgeSection.PAYMENT,
        "Pricing",
        "Replisto is prepaid and pay-as-you-go: you top up your wallet and each answer is "
        "deducted by how much text the AI reads and writes. There is no subscription. When the "
        "balance runs out, the assistant passes customers' messages to you until you top up. "
        "Wallet credit is non-refundable.",
    ),
    (
        KnowledgeSection.FAQ,
        "Can it give wrong answers?",
        "It answers only from what you've given it and hands over what it doesn't know. Try "
        "it on the test page before turning it on, and switch it off for one customer or "
        "entirely whenever you want.",
    ),
    (
        KnowledgeSection.FAQ,
        "Does it take orders or payments?",
        "No. It answers questions and explains how to order using your information; orders "
        "and payments stay with you.",
    ),
    (
        KnowledgeSection.FAQ,
        "Is my data safe?",
        "Connections are encrypted, access tokens are stored encrypted, and your data is never "
        "sold or used for advertising or to train AI models. Deleting your account deletes "
        "everything. Details are in the privacy policy on the website.",
    ),
    (
        KnowledgeSection.CONTACT,
        "Talking to the team",
        "This chat reaches the Replisto team: if I don't know an answer, someone from the team "
        "replies right here.",
    ),
]

RULES = (
    "Don't comment on competitors.\n"
    "Never promise discounts, prices or features that aren't in the information.\n"
    "Don't discuss servers, AI providers or team members.\n"
    "If someone asks to talk to a person, hand off."
)
FALLBACK = "I've passed your question to the Replisto team; they'll answer right here."


async def main(email: str, reset_knowledge: bool, take_over: bool) -> None:
    email = email.strip().lower()
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        password = None
        if user is None:
            password = secrets.token_urlsafe(12)
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name="Replisto team",
                email_verified_at=utcnow(),
            )
            user.shop = Shop(name="Replisto")
            db.add(user)
            await db.flush()
        shop = await db.scalar(select(Shop).where(Shop.owner_id == user.id))
        assert shop is not None
        if not shop.is_house and password is None and not take_over:
            raise SystemExit(
                f"{email} already has the shop {shop.name!r}. Use a separate account for "
                "Replisto's own shop, or pass --take-over to turn that shop into it."
            )
        # Only one house shop.
        await db.execute(update(Shop).where(Shop.id != shop.id).values(is_house=False))
        shop.is_house = True
        shop.name = "Replisto"
        shop.bot_enabled = True
        shop.tone = "friendly"
        shop.use_emoji = True
        shop.language = "en"
        shop.fallback_message = FALLBACK
        shop.forbidden_rules = RULES
        shop.signup_gift_at = shop.signup_gift_at or utcnow()  # no gift for ourselves
        has_knowledge = await db.scalar(
            select(KnowledgeEntry.id).where(KnowledgeEntry.shop_id == shop.id).limit(1)
        )
        if reset_knowledge or has_knowledge is None:
            await db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.shop_id == shop.id))
            db.add_all(
                KnowledgeEntry(shop_id=shop.id, section=section, title=title, content=content)
                for section, title, content in KNOWLEDGE
            )
        await db.commit()

    print(f"Replisto's own shop is ready, owned by {email}.")
    if password:
        print(f"New account password (shown once): {password}")
    print("Log in with it to edit what the assistant knows and to answer its handed-off chats.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--reset-knowledge", action="store_true")
    parser.add_argument("--take-over", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.reset_knowledge, args.take_over))
