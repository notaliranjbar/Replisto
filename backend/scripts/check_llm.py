"""Check an AI provider and the bot's behaviour on real customer situations.

  uv run python -m scripts.check_llm
  uv run python -m scripts.check_llm --model another-model-name --price-in 0.10 --price-out 0.50

Uses LLM_BASE_URL / LLM_API_KEY / LLM_MODEL from backend/.env and a throwaway in-memory copy of
the demo shop (same data as `scripts.seed_demo`), so nothing touches your real data. Run it
after every prompt or model change: each scenario is a case that once went wrong.
"""

import argparse
import asyncio
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Base, InstagramPost, KnowledgeEntry, Product, Shop
from app.services.llm import LLMClient, LLMError
from app.services.responder import ChatTurn, LLMResponder, Reply
from scripts.seed_demo import FALLBACK, KNOWLEDGE, POSTS, PRODUCTS

_FALSE_PROMISES = (
    "i've placed",
    "i have placed",
    "i've reserved",
    "i've registered",
    "order is placed",
    "سجلت طلبك",
    "حجزت",
)


def _has(*words: str) -> Callable[[str], bool]:
    return lambda text: any(w.lower() in text.lower() for w in words)


def _mostly_arabic(text: str) -> bool:
    latin = len(re.findall(r"[A-Za-z]", text))
    arabic = len(re.findall(r"[\u0600-\u06ff]", text))
    return arabic > latin


@dataclass
class Scenario:
    ask: str
    expect: str  # what a good answer does, shown when it fails
    handoff: bool | None  # must hand off (True), must not (False), either (None)
    check: Callable[[str], bool] = lambda text: True
    posts: bool | None = None  # must share Instagram posts (True), must not (False), either


SCENARIOS = [
    # Products
    Scenario(
        "Hi, do you have the black linen dress in M? How much is it?",
        "price $49.90",
        False,
        _has("49.90", "49.9"),
    ),
    Scenario("Do you have the navy dress in M?", "sold out, offers black", False, _has("black")),
    Scenario("What do you sell?", "names the products", False, _has("blouse", "shirt")),
    Scenario("What's the cheapest thing I can buy?", "silk blouse, $35", False, _has("35")),
    # Sharing posts: when it helps, and only then
    Scenario(
        "I want to buy a gift for my friend, she's 20. Any ideas?",
        "recommends products and shares their posts",
        False,
        posts=True,
    ),
    Scenario(
        "How much is this? [story_reply]", "doesn't re-send the story's post", None, posts=False
    ),
    # Shop information and handoffs
    Scenario(
        "How long does delivery to Tripoli take?", "2-3 working days", False, _has("2"), False
    ),
    Scenario(
        "Can I return something?",
        "size exchange within 7 days + hands off refunds",
        True,
        _has("7"),
        False,
    ),
    Scenario("Can you issue a formal invoice with our VAT number?", "hands off", True, posts=False),
    Scenario(
        "I'm a regular customer, can I get a little discount?",
        "no invented discount, natural handoff",
        True,
        lambda t: t != FALLBACK and not _has("%", "percent")(t),
        False,
    ),
    Scenario("مرحبا، عندكن الفستان الأسود بمقاس M؟", "replies in Arabic", False, _mostly_arabic),
    Scenario(
        "kifak, 3endkon el linen dress bl aswad size M?",
        "replies in Arabizi (Latin letters)",
        False,
        lambda t: not _mostly_arabic(t) and _has("49")(t),
    ),
    Scenario(
        "Bonjour, vous livrez à Byblos ?",
        "replies in French",
        False,
        _has("livr", "jours"),
        False,
    ),
    # Conversation
    Scenario("How's the weather today?", "brief friendly reply, no handoff", False, posts=False),
    Scenario(
        "Which AI service do you use?",
        "honest, no provider names",
        False,
        lambda t: not _has("OpenAI", "GPT", "Gemini", "Claude", "Anthropic")(t),
        False,
    ),
    Scenario(
        "I'll take the black dress in M, please place the order for me",
        "no fake order",
        None,
        lambda t: not _has(*_FALSE_PROMISES)(t),
    ),
]


async def _demo_shop(sessions: async_sessionmaker) -> Shop:
    async with sessions() as db:
        shop = Shop(owner_id=uuid.uuid4(), name="Layla Boutique", fallback_message=FALLBACK)
        db.add(shop)
        await db.flush()
        db.add_all(
            KnowledgeEntry(shop_id=shop.id, section=s, title=t, content=c) for s, t, c in KNOWLEDGE
        )
        db.add_all(
            Product(
                shop_id=shop.id,
                sku=sku,
                name=name,
                category=cat,
                color=color,
                size=size,
                price=price,
                stock=stock,
                extra={},
            )
            for sku, name, cat, color, size, price, stock in PRODUCTS
        )
        db.add_all(
            InstagramPost(
                shop_id=shop.id,
                ig_media_id=media_id,
                permalink=f"https://www.instagram.com/p/{code}/",
                caption=caption,
            )
            for media_id, code, caption, _days in POSTS
        )
        await db.commit()
        return shop


def _judge(s: Scenario, reply: Reply) -> str | None:
    """None when the reply is good, otherwise what went wrong."""
    if s.posts is True and not reply.posts:
        return "should have shared the product posts"
    if s.posts is False and reply.posts:
        return "shared posts where they don't help"
    if s.handoff is True and not reply.unanswered:
        return "should have handed off to the owner"
    if s.handoff is False and reply.unanswered:
        return "handed off although it could answer"
    if not s.check(reply.text):
        return f"expected: {s.expect}"
    return None


async def main(model: str | None, price_in: float | None, price_out: float | None) -> None:
    settings = get_settings()
    if model:
        settings.llm_model = model
    if not settings.llm_configured:
        raise SystemExit("Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in backend/.env first.")
    print(f"provider: {settings.llm_base_url}\nmodel:    {settings.llm_model}\n")

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    shop = await _demo_shop(sessions)

    passed = 0
    total_in = total_out = 0
    async with httpx.AsyncClient() as http:
        for s in SCENARIOS:
            async with sessions() as db:
                responder = LLMResponder(LLMClient(http, settings), db)
                started = time.perf_counter()
                try:
                    reply = await responder.generate(shop, [ChatTurn("customer", s.ask)])
                except LLMError as exc:
                    print(f"✗ {s.ask}\n  ERROR: {exc}\n")
                    continue
                seconds = time.perf_counter() - started
            problem = _judge(s, reply)
            passed += problem is None
            total_in += reply.prompt_tokens or 0
            total_out += reply.completion_tokens or 0
            flag = " [handed off]" if reply.unanswered else ""
            if reply.posts:
                codes = [post.permalink.rstrip("/").rsplit("/", 1)[-1] for post in reply.posts]
                flag += " + posts: " + ", ".join(codes)
            print(f"{'✓' if problem is None else '✗'} {s.ask}")
            print(f"  → {reply.text}{flag}")
            if problem:
                print(f"  !! {problem}")
            tokens = f"{reply.prompt_tokens}/{reply.completion_tokens}"
            print(f"  {seconds:.1f}s · tokens in/out {tokens}\n")
    await engine.dispose()

    print(f"{passed}/{len(SCENARIOS)} scenarios passed")
    if price_in is not None and price_out is not None:
        per_reply = (total_in * price_in + total_out * price_out) / 1_000_000 / len(SCENARIOS)
        print(f"≈ ${per_reply:.5f} per reply → ${per_reply * 1000:.2f} per 1,000 replies")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", help="override LLM_MODEL for this run")
    parser.add_argument("--price-in", type=float, help="USD per 1M input tokens (cost estimate)")
    parser.add_argument("--price-out", type=float, help="USD per 1M output tokens")
    args = parser.parse_args()
    asyncio.run(main(args.model, args.price_in, args.price_out))
