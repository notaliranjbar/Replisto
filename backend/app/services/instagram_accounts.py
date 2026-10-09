import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret
from app.core.timeutil import as_utc, utcnow
from app.models import InstagramAccount, Shop
from app.services.instagram import SCOPES, InstagramClient, InstagramError
from app.services.posts import sync_posts

logger = logging.getLogger(__name__)

# Refresh long-lived (60 day) tokens once they are within this window of expiring.
REFRESH_BEFORE_EXPIRY = timedelta(days=10)


class AccountInUseError(Exception):
    """This Instagram account is already connected to a different shop."""


async def connect_account(
    db: AsyncSession, shop: Shop, code: str, instagram: InstagramClient
) -> InstagramAccount:
    short_lived = await instagram.exchange_code(code)
    token = await instagram.get_long_lived_token(short_lived.access_token)
    profile = await instagram.get_profile(token.access_token)

    owner = await db.scalar(
        select(InstagramAccount).where(InstagramAccount.ig_user_id == profile.ig_user_id)
    )
    if owner is not None and owner.shop_id != shop.id:
        raise AccountInUseError(profile.username)

    await instagram.subscribe_webhooks(token.access_token)

    # One account per shop: connecting a different page replaces the previous one.
    account = owner or await db.scalar(
        select(InstagramAccount).where(InstagramAccount.shop_id == shop.id)
    )
    if account is None:
        account = InstagramAccount(shop_id=shop.id)
        db.add(account)
    account.ig_user_id = profile.ig_user_id
    account.username = profile.username
    account.access_token_encrypted = encrypt_secret(token.access_token)
    account.token_expires_at = token.expires_at
    account.is_active = True
    # Meta lists what was granted; when it doesn't, the consent screen asked for all of them.
    account.scopes = ",".join(short_lived.permissions or SCOPES)
    await db.commit()
    try:
        await sync_posts(db, account, instagram)
    except InstagramError as exc:
        logger.warning("could not read posts for shop %s: %s", shop.id, exc)
    return account


async def refresh_expiring_tokens(db: AsyncSession, instagram: InstagramClient) -> int:
    """Refresh tokens close to expiry; deactivate accounts whose token was revoked."""
    deadline = utcnow() + REFRESH_BEFORE_EXPIRY
    accounts = (
        await db.scalars(select(InstagramAccount).where(InstagramAccount.is_active.is_(True)))
    ).all()
    refreshed = 0
    for account in accounts:
        if account.token_expires_at and as_utc(account.token_expires_at) > deadline:
            continue
        try:
            token = await instagram.refresh_token(decrypt_secret(account.access_token_encrypted))
        except InstagramError as exc:
            if exc.token_invalid:
                account.is_active = False
                await db.commit()
            logger.warning("token refresh failed for account %s: %s", account.id, exc)
            continue
        account.access_token_encrypted = encrypt_secret(token.access_token)
        account.token_expires_at = token.expires_at
        await db.commit()
        refreshed += 1
    return refreshed
