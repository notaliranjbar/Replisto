"""Fill a local database with a realistic demo shop, so the panel can be built against real data.

  uv run python -m scripts.seed_demo
  uv run python -m scripts.seed_demo --language ar     # an owner using the panel in Arabic

Log in with  demo@shop.com / demopass123 . Safe to re-run: it recreates the demo account.
"""

import argparse
import asyncio
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import encrypt_secret, hash_password
from app.core.timeutil import utcnow
from app.models import (
    Conversation,
    HandoffResolution,
    InstagramAccount,
    InstagramPost,
    KnowledgeEntry,
    KnowledgeSection,
    Message,
    MessageSender,
    Product,
    ProductOrigin,
    Shop,
    User,
    WalletEntry,
    WalletEntryKind,
)
from app.services.accounts import delete_user

EMAIL = "demo@shop.com"
PASSWORD = "demopass123"
# The same credit a new shop gets as its gift ($5 by default).
DEMO_CREDIT_CENTS = get_settings().signup_credit_cents

KNOWLEDGE = [
    (
        KnowledgeSection.ABOUT,
        "",
        "Layla Boutique in Achrafieh, Beirut, makes women's dresses and blouses since 2019.",
    ),
    (
        KnowledgeSection.SHIPPING,
        "",
        "Delivery all over Lebanon in 2-3 working days for $4; same day inside Beirut. "
        "Free on orders over $100.",
    ),
    (
        KnowledgeSection.PAYMENT,
        "",
        "Cash on delivery (dollars or lira at the daily rate), or Whish Money before delivery.",
    ),
    (KnowledgeSection.CONTACT, "", "Open Monday to Saturday, 10am-7pm. Closed on Sundays."),
    (KnowledgeSection.RETURNS, "", "Size exchanges within 7 days of delivery."),
    (KnowledgeSection.FAQ, "What's the fabric?", "Premium linen, pre-washed so it won't shrink."),
    (KnowledgeSection.FAQ, "Size guide?", "S to XL; S fits US 4-6, M fits 8-10, L fits 12-14."),
]
PRODUCTS = [
    ("D-101", "Linen dress", "Dresses", "Black", "S", Decimal("49.90"), 4),
    ("D-101", "Linen dress", "Dresses", "Black", "M", Decimal("49.90"), 3),
    ("D-101", "Linen dress", "Dresses", "Navy", "M", Decimal("49.90"), 0),
    ("B-220", "Silk blouse", "Blouses", "White", "One size", Decimal("35.00"), 7),
    ("B-221", "Linen shirt", "Blouses", "Cream", "One size", Decimal("38.00"), 2),
]
FALLBACK = "Thanks for your message! A teammate will get back to you shortly 🙏"
# (username, [(sender, text, unanswered, minutes_ago)], paused)
CONVERSATIONS = [
    (
        "sara.style",
        [
            ("customer", "Hi! Do you have the black linen dress in size M?", False, 42),
            ("bot", "Hi there 🌸 Yes, it's in stock in M, and it's $49.90.", False, 41),
            ("customer", "How long does delivery to Jounieh take?", False, 40),
            ("bot", "Delivery takes 2-3 working days and costs $4.", False, 39),
        ],
        False,
    ),
    (
        "rita.khoury",
        [
            ("customer", "مرحبا", False, 15),
            ("customer", "فيكن تعملولي فاتورة رسمية للشركة؟", False, 15),
            ("bot", "أهلا فيكي! رح خلّي حدا من الفريق يجاوبك عن الفاتورة بأسرع وقت 🙏", True, 14),
        ],
        False,
    ),
    (
        "maya.haddad",
        [
            ("customer", "hi, aymta byerja3 el navy bl M?", False, 8),
            ("bot", FALLBACK, True, 7),
            ("owner", "Hi Maya, it's back next week 🌷", False, 3),
        ],
        True,
    ),
]
# Instagram posts of the demo page: (media id, shortcode, caption, days ago). The bot links a
# post to a product when the caption names it (or its code); the last one names no product.
POSTS = [
    (
        "17900000000000001",
        "DEMOdress01",
        "Linen dress 🖤 black and navy, sizes S to M\nCode D-101 · made in our studio",
        3,
    ),
    ("17900000000000002", "DEMOsilk002", "Silk blouse in white, light and breezy 🤍 one size", 9),
    ("17900000000000003", "DEMOlinen03", "Linen shirt in cream ☀️ made for summer", 15),
    ("17900000000000004", "DEMOstudio4", "Behind the scenes of our new collection shoot 📸", 20),
]
# username -> (question, reason by panel language, handed off minutes ago, resolved minutes
# ago or None). The bot writes reasons in the owner's panel language.
HANDOFFS = {
    "rita.khoury": (
        "مرحبا\nفيكن تعملولي فاتورة رسمية للشركة؟",
        {
            "en": "The customer wants a formal invoice for a company",
            "ar": "العميلة تريد فاتورة رسمية للشركة",
        },
        14,
        None,
    ),
    "maya.haddad": (
        "hi, aymta byerja3 el navy bl M?",
        {"en": "Restock date unknown", "ar": "موعد عودة المقاس إلى المخزون غير معروف"},
        7,
        3,
    ),
}


async def main(language: str) -> None:
    async with SessionLocal() as db:
        old = await db.scalar(select(User.id).where(User.email == EMAIL))
        if old is not None:
            await delete_user(db, old)

        now = utcnow()
        user = User(
            email=EMAIL,
            password_hash=hash_password(PASSWORD),
            full_name="Layla",
            email_verified_at=now,
        )
        user.shop = Shop(
            name="Layla Boutique",
            bot_enabled=True,
            fallback_message=FALLBACK,
            language=language,
            balance_cents=DEMO_CREDIT_CENTS,
            signup_gift_at=now,
        )
        db.add(user)
        await db.flush()
        shop_id = user.shop.id

        db.add(
            InstagramAccount(
                shop_id=shop_id,
                ig_user_id="17840000000000000",
                username="layla.boutique",
                access_token_encrypted=encrypt_secret("demo-token"),
                token_expires_at=now + timedelta(days=55),
                posts_synced_at=now - timedelta(hours=2),
            )
        )
        db.add_all(
            KnowledgeEntry(shop_id=shop_id, section=s, title=t, content=c) for s, t, c in KNOWLEDGE
        )
        db.add_all(
            InstagramPost(
                shop_id=shop_id,
                ig_media_id=media_id,
                permalink=f"https://www.instagram.com/p/{code}/",
                caption=caption,
                media_type="CAROUSEL_ALBUM",
                posted_at=now - timedelta(days=days),
            )
            for media_id, code, caption, days in POSTS
        )
        db.add(
            WalletEntry(
                shop_id=shop_id,
                kind=WalletEntryKind.BONUS,
                amount_cents=DEMO_CREDIT_CENTS,
                balance_after_cents=DEMO_CREDIT_CENTS,
                description="Welcome gift",
                details={},
            )
        )
        db.add_all(
            Product(
                shop_id=shop_id,
                sku=sku,
                name=name,
                category=cat,
                color=color,
                size=size,
                price=price,
                stock=stock,
                extra={},
                origin=ProductOrigin.MANUAL if index < 3 else ProductOrigin.TEACH,
            )
            for index, (sku, name, cat, color, size, price, stock) in enumerate(PRODUCTS)
        )
        for index, (username, messages, paused) in enumerate(CONVERSATIONS):
            last_customer = max(m[3] for m in messages if m[0] == "customer")
            conversation = Conversation(
                shop_id=shop_id,
                customer_id=f"90000000000000{index}",
                customer_username=username,
                last_customer_message_at=now - timedelta(minutes=last_customer),
                bot_paused_until=now + timedelta(minutes=100) if paused else None,
            )
            handoff = HANDOFFS.get(username)
            if handoff:
                question, reasons, minutes_ago, resolved_minutes_ago = handoff
                conversation.handoff_at = now - timedelta(minutes=minutes_ago)
                conversation.handoff_question = question
                conversation.handoff_reason = reasons[language]
                if resolved_minutes_ago is not None:
                    conversation.handoff_resolved_at = now - timedelta(minutes=resolved_minutes_ago)
                    conversation.handoff_resolved_by = HandoffResolution.OWNER_REPLY
            db.add(conversation)
            await db.flush()
            for order, (sender, text, unanswered, ago) in enumerate(messages):
                db.add(
                    Message(
                        conversation_id=conversation.id,
                        sender=MessageSender(sender),
                        text=text,
                        unanswered=unanswered,
                        # Keep order stable for messages sent in the same minute.
                        created_at=now - timedelta(minutes=ago) + timedelta(milliseconds=order),
                        prompt_tokens=900 if sender == "bot" else None,
                        completion_tokens=40 if sender == "bot" else None,
                    )
                )
        await db.commit()
    print(f"demo shop ready: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the demo shop.")
    parser.add_argument("--language", choices=["en", "ar"], default="en")
    asyncio.run(main(parser.parse_args().language))
