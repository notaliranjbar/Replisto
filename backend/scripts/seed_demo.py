"""Fill a local database with a realistic demo shop, so the panel can be built against real data.

  uv run python -m scripts.seed_demo

Log in with  demo@shop.ir / demopass123 . Safe to re-run: it recreates the demo account.
"""

import asyncio
from datetime import timedelta

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

EMAIL = "demo@shop.ir"
PASSWORD = "demopass123"
# The same credit a new shop gets as its gift (50,000 toman by default).
DEMO_CREDIT_RIAL = get_settings().signup_credit_rial

KNOWLEDGE = [
    (KnowledgeSection.ABOUT, "", "مزون مهسا، تولیدکننده‌ی مانتو و شومیز زنانه از سال ۱۳۹۸."),
    (
        KnowledgeSection.SHIPPING,
        "",
        "ارسال با پست پیشتاز ۳ تا ۵ روز کاری، هزینه ۸۵ هزار تومان. خرید بالای ۲ میلیون رایگان.",
    ),
    (KnowledgeSection.PAYMENT, "", "کارت‌به‌کارت یا درگاه سایت. پرداخت در محل فقط تهران."),
    (KnowledgeSection.RETURNS, "", "تا ۷ روز بعد از تحویل امکان تعویض سایز هست."),
    (KnowledgeSection.FAQ, "جنس پارچه؟", "کتان ترک درجه یک، بدون آبرفت."),
    (KnowledgeSection.FAQ, "راهنمای سایز؟", "سایز ۳۸ تا ۴۴ معادل S تا XL."),
]
PRODUCTS = [
    ("M-101", "مانتو کتان", "مانتو", "مشکی", "40", 1250000, 4),
    ("M-101", "مانتو کتان", "مانتو", "مشکی", "44", 1250000, 3),
    ("M-101", "مانتو کتان", "مانتو", "سرمه‌ای", "44", 1250000, 0),
    ("S-220", "شومیز حریر", "شومیز", "سفید", "آزاد", 890000, 7),
    ("S-221", "شومیز لینن", "شومیز", "کرم", "آزاد", 950000, 2),
]
# (username, [(sender, text, unanswered, minutes_ago)], paused)
CONVERSATIONS = [
    (
        "sara.style",
        [
            ("customer", "سلام، مانتو کتان مشکی سایز ۴۴ دارید؟", False, 42),
            ("bot", "سلام عزیزم 🌸 بله موجوده، قیمتش ۱,۲۵۰,۰۰۰ تومانه.", False, 41),
            ("customer", "ارسال به شیراز چقدر طول میکشه؟", False, 40),
            ("bot", "با پست پیشتاز ۳ تا ۵ روز کاری میرسه و هزینه‌اش ۸۵ هزار تومانه.", False, 39),
        ],
        False,
    ),
    (
        "neda_k",
        [
            ("customer", "سلام", False, 15),
            ("customer", "فاکتور رسمی برای شرکت میدید؟", False, 15),
            ("bot", "سوالتون رو ثبت کردم، همکارم به زودی جواب میده 🙏", True, 14),
        ],
        False,
    ),
    (
        "maryam.r",
        [
            ("customer", "سرمه‌ای ۴۴ کی موجود میشه؟", False, 8),
            ("bot", "سوالتون رو ثبت کردم، همکارم به زودی جواب میده 🙏", True, 7),
            ("owner", "سلام مریم جان، هفته‌ی بعد میرسه 🌷", False, 3),
        ],
        True,
    ),
]
# Instagram posts of the demo page: (media id, shortcode, caption, days ago). The bot links a
# post to a product when the caption names it (or its code); the last one names no product.
POSTS = [
    (
        "17900000000000001",
        "DEMOmanto01",
        "مانتو کتان ترک 🖤 مشکی و سرمه‌ای، سایز ۴۰ تا ۴۴\nکد M-101 · دوخت خودمون",
        3,
    ),
    ("17900000000000002", "DEMOharir02", "شومیز حریر سفید، سبک و خنک برای مهمونی‌ها 🤍 فری‌سایز", 9),
    ("17900000000000003", "DEMOlinen03", "شومیز لینن کرم ☀️ مناسب تابستون", 15),
    ("17900000000000004", "DEMOstudio4", "پشت صحنه‌ی عکاسی کالکشن جدید 📸", 20),
]
# username -> (question, reason, handed off minutes ago, resolved minutes ago or None)
HANDOFFS = {
    "neda_k": ("سلام\nفاکتور رسمی برای شرکت میدید؟", "مشتری فاکتور رسمی می‌خواهد", 14, None),
    "maryam.r": ("سرمه‌ای ۴۴ کی موجود میشه؟", "زمان موجود شدن کالا مشخص نیست", 7, 3),
}


async def main() -> None:
    async with SessionLocal() as db:
        old = await db.scalar(select(User.id).where(User.email == EMAIL))
        if old is not None:
            await delete_user(db, old)

        now = utcnow()
        user = User(
            email=EMAIL,
            password_hash=hash_password(PASSWORD),
            full_name="مهسا",
            email_verified_at=now,
        )
        user.shop = Shop(
            name="مزون مهسا",
            bot_enabled=True,
            balance_rial=DEMO_CREDIT_RIAL,
            signup_gift_at=now,
        )
        db.add(user)
        await db.flush()
        shop_id = user.shop.id

        db.add(
            InstagramAccount(
                shop_id=shop_id,
                ig_user_id="17840000000000000",
                username="mahsa.boutique",
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
                amount_rial=DEMO_CREDIT_RIAL,
                balance_after_rial=DEMO_CREDIT_RIAL,
                description="هدیه‌ی شروع کار",
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
                question, reason, minutes_ago, resolved_minutes_ago = handoff
                conversation.handoff_at = now - timedelta(minutes=minutes_ago)
                conversation.handoff_question = question
                conversation.handoff_reason = reason
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
    asyncio.run(main())
