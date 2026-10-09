import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import CurrentShop, DbSession, Instagram
from app.core.config import get_settings
from app.core.security import TokenError, create_token, decode_token
from app.models import InstagramAccount, InstagramInsights, InstagramPost, Product, Shop
from app.services.instagram import (
    SCOPE_COMMENTS,
    SCOPE_INSIGHTS,
    SCOPE_MESSAGES,
    SCOPE_PUBLISH,
    InstagramError,
)
from app.services.instagram_accounts import AccountInUseError, connect_account
from app.services.posts import link_products, load_posts, post_key, sync_posts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instagram", tags=["instagram"])


class ConnectUrlOut(BaseModel):
    url: str


INSTAGRAM_OFF = "Instagram is switched off on this server for now."


class InstagramFeatures(BaseModel):
    messages: bool  # answer DMs and story replies
    comments: bool  # answer comments publicly or privately, hide spam
    stories: bool  # publish scheduled stories
    insights: bool  # read the page's numbers


class InstagramStatusOut(BaseModel):
    # False while Instagram is switched off on the server (waiting for Meta's approval).
    available: bool = True
    connected: bool
    # False when Meta revoked access (password change, app removed): owner must reconnect.
    active: bool = False
    username: str | None = None
    ig_user_id: str | None = None
    token_expires_at: datetime | None = None
    # What the bot may do on this account, from the permissions the owner granted. Accounts
    # connected before a feature existed reconnect to turn it on.
    features: InstagramFeatures | None = None


@router.get("", response_model=InstagramStatusOut)
async def get_status(shop: CurrentShop, db: DbSession) -> InstagramStatusOut:
    available = get_settings().instagram_enabled
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    if account is None:
        return InstagramStatusOut(available=available, connected=False)
    return InstagramStatusOut(
        available=available,
        connected=True,
        active=account.is_active,
        username=account.username,
        ig_user_id=account.ig_user_id,
        token_expires_at=account.token_expires_at,
        features=InstagramFeatures(
            messages=account.has_scope(SCOPE_MESSAGES),
            comments=account.has_scope(SCOPE_COMMENTS),
            stories=account.has_scope(SCOPE_PUBLISH),
            insights=account.has_scope(SCOPE_INSIGHTS),
        ),
    )


@router.get("/connect-url", response_model=ConnectUrlOut)
async def connect_url(shop: CurrentShop, instagram: Instagram) -> ConnectUrlOut:
    """URL of Instagram's consent screen. The panel sends the browser there."""
    if not get_settings().instagram_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, INSTAGRAM_OFF)
    return ConnectUrlOut(url=instagram.authorize_url(create_token(shop.id, "ig_oauth")))


@router.get("/callback", include_in_schema=False)
async def callback(
    db: DbSession,
    instagram: Instagram,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Instagram redirects the browser here; we finish the connection and bounce to the panel.

    This request carries no auth header, so the shop is identified by the signed `state`.
    """
    if error:
        return _back_to_panel("denied")
    if not code or not state:
        return _back_to_panel("error", "missing_code")
    try:
        shop_id = decode_token(state, "ig_oauth")
    except TokenError:
        return _back_to_panel("error", "invalid_state")
    shop = await db.get(Shop, shop_id)
    if shop is None:
        return _back_to_panel("error", "invalid_state")

    # Instagram appends "#_" to the code in some redirects.
    code = code.removesuffix("#_")
    try:
        await connect_account(db, shop, code, instagram)
    except AccountInUseError:
        return _back_to_panel("error", "account_in_use")
    except InstagramError as exc:
        logger.warning("instagram connect failed for shop %s: %s", shop.id, exc)
        return _back_to_panel("error", "instagram")
    return _back_to_panel("connected")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(shop: CurrentShop, db: DbSession) -> None:
    await db.execute(delete(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    await db.execute(delete(InstagramPost).where(InstagramPost.shop_id == shop.id))
    await db.execute(delete(InstagramInsights).where(InstagramInsights.shop_id == shop.id))
    await db.commit()


def _back_to_panel(result: str, reason: str | None = None) -> RedirectResponse:
    params = {"status": result} | ({"reason": reason} if reason else {})
    base = get_settings().frontend_url.rstrip("/")
    return RedirectResponse(f"{base}/instagram/callback?{urlencode(params)}", status_code=302)


class PostOut(BaseModel):
    permalink: str
    caption: str
    preview_url: str | None
    media_type: str
    posted_at: datetime | None
    # Products the bot connects to this post (shares it when recommending them).
    products: list[str]


class PostsOut(BaseModel):
    synced_at: datetime | None
    total: int
    # Products with no post: the owner can add a post link in the product sheet.
    products_without_post: list[str]
    items: list[PostOut]


@router.get("/posts", response_model=PostsOut)
async def list_posts(shop: CurrentShop, db: DbSession) -> PostsOut:
    """The page's posts and which products the bot links to each (newest 60)."""
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    all_posts = await load_posts(db, shop.id)
    items = (await db.scalars(select(Product).where(Product.shop_id == shop.id))).all()
    links = link_products(list(items), all_posts)

    products_by_post: dict[str, list[str]] = {}
    for name, link in links.items():
        products_by_post.setdefault(post_key(link.permalink) or link.permalink, []).append(name)
    names = list(dict.fromkeys(p.name.strip() for p in items))

    newest = sorted(all_posts, key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC))
    return PostsOut(
        synced_at=account.posts_synced_at if account else None,
        total=len(all_posts),
        products_without_post=[n for n in names if n not in links],
        items=[
            PostOut(
                permalink=p.permalink,
                caption=p.caption[:300],
                preview_url=p.preview_url,
                media_type=p.media_type,
                posted_at=p.posted_at,
                products=products_by_post.get(post_key(p.permalink) or p.permalink, []),
            )
            for p in reversed(newest[-60:])
        ],
    )


@router.post("/posts/sync", response_model=PostsOut)
async def sync_posts_now(shop: CurrentShop, db: DbSession, instagram: Instagram) -> PostsOut:
    """Read the page's posts again now (they are also refreshed daily)."""
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    if account is None or not account.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Connect your Instagram account first.")
    try:
        await sync_posts(db, account, instagram)
    except InstagramError as exc:
        logger.warning("post sync failed for shop %s: %s", shop.id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Couldn't read your posts from Instagram. Please try again in a moment.",
        ) from None
    return await list_posts(shop, db)
