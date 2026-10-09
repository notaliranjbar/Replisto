import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ContentReport,
    Conversation,
    InstagramAccount,
    InstagramComment,
    InstagramInsights,
    InstagramPost,
    KnowledgeEntry,
    Message,
    Payment,
    Product,
    ProductSource,
    ScheduledStory,
    Shop,
    TeachProposal,
    User,
    WalletEntry,
)
from app.services import stories


async def delete_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Permanently delete a user, their shop and everything stored for it, then commit.

    Explicit deletes instead of relying on ON DELETE CASCADE, so it also works on SQLite.
    """
    shop_id = await db.scalar(select(Shop.id).where(Shop.owner_id == user_id))
    if shop_id is not None:
        conversations = select(Conversation.id).where(Conversation.shop_id == shop_id)
        await db.execute(delete(Message).where(Message.conversation_id.in_(conversations)))
        for story in (
            await db.scalars(select(ScheduledStory).where(ScheduledStory.shop_id == shop_id))
        ).all():
            stories.delete_file(story)
        for model in (
            Conversation,
            Product,
            ProductSource,
            KnowledgeEntry,
            InstagramPost,
            InstagramComment,
            InstagramInsights,
            ContentReport,
            ScheduledStory,
            InstagramAccount,
            TeachProposal,
            WalletEntry,
            Payment,
        ):
            await db.execute(delete(model).where(model.shop_id == shop_id))
        await db.execute(delete(Shop).where(Shop.id == shop_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
