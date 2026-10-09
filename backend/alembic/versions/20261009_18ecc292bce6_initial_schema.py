"""initial schema

The whole database in one step. A database already at this revision has the same schema and
needs nothing; a new one is created from here.

Revision ID: 18ecc292bce6
Revises:
Create Date: 2026-10-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18ecc292bce6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('gift_claims',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_gift_claims')),
    sa.UniqueConstraint('key', name=op.f('uq_gift_claims_key'))
    )
    op.create_table('site_chat_usage',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('day', sa.String(length=10), nullable=False),
    sa.Column('tokens', sa.BigInteger(), nullable=False),
    sa.Column('messages', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_site_chat_usage')),
    sa.UniqueConstraint('key', 'day', name=op.f('uq_site_chat_usage_key'))
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('phone_pending', sa.String(length=20), nullable=True),
    sa.Column('phone_code_hash', sa.String(length=64), nullable=True),
    sa.Column('phone_code_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('phone_code_attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('phone', name=op.f('uq_users_phone'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('shops',
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('bot_enabled', sa.Boolean(), nullable=False),
    sa.Column('tone', sa.String(length=16), nullable=False),
    sa.Column('use_emoji', sa.Boolean(), nullable=False),
    sa.Column('fallback_message', sa.Text(), nullable=False),
    sa.Column('forbidden_rules', sa.Text(), nullable=False),
    sa.Column('handoff_pause_minutes', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
    sa.Column('language', sa.String(length=2), server_default='en', nullable=False),
    sa.Column('timezone', sa.String(length=40), server_default='Asia/Beirut', nullable=False),
    sa.Column('comment_mode', sa.String(length=8), server_default='both', nullable=False),
    sa.Column('comment_thank_praise', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('comment_hide_spam', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('balance_cents', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('low_balance_notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('empty_wallet_notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('signup_gift_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_house', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_shops_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shops')),
    sa.UniqueConstraint('owner_id', name=op.f('uq_shops_owner_id'))
    )
    op.create_table('content_reports',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('language', sa.String(length=2), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_content_reports_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_reports'))
    )
    op.create_index(op.f('ix_content_reports_shop_id'), 'content_reports', ['shop_id'], unique=False)
    op.create_table('conversations',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('channel', sa.Enum('instagram', 'web', name='channel', native_enum=False, length=32), server_default='instagram', nullable=False),
    sa.Column('channel_ref', sa.String(length=80), server_default='', nullable=False),
    sa.Column('customer_id', sa.String(length=64), nullable=False),
    sa.Column('customer_username', sa.String(length=64), nullable=True),
    sa.Column('customer_name', sa.String(length=128), nullable=True),
    sa.Column('last_customer_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bot_paused_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('handoff_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('handoff_reason', sa.String(length=255), nullable=True),
    sa.Column('handoff_question', sa.Text(), nullable=True),
    sa.Column('handoff_resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('handoff_resolved_by', sa.Enum('owner_reply', 'manual', name='handoffresolution', native_enum=False, length=32), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_conversations_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    sa.UniqueConstraint('shop_id', 'channel', 'channel_ref', 'customer_id', name='uq_conversations_thread')
    )
    op.create_index(op.f('ix_conversations_handoff_at'), 'conversations', ['handoff_at'], unique=False)
    op.create_index(op.f('ix_conversations_shop_id'), 'conversations', ['shop_id'], unique=False)
    op.create_table('instagram_accounts',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('ig_user_id', sa.String(length=64), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('access_token_encrypted', sa.Text(), nullable=False),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('posts_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('scopes', sa.Text(), server_default='', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_instagram_accounts_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_accounts')),
    sa.UniqueConstraint('shop_id', name=op.f('uq_instagram_accounts_shop_id'))
    )
    op.create_index(op.f('ix_instagram_accounts_ig_user_id'), 'instagram_accounts', ['ig_user_id'], unique=True)
    op.create_table('instagram_comments',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('ig_comment_id', sa.String(length=64), nullable=False),
    sa.Column('parent_ig_id', sa.String(length=64), nullable=True),
    sa.Column('media_id', sa.String(length=64), nullable=False),
    sa.Column('media_permalink', sa.Text(), nullable=True),
    sa.Column('media_caption', sa.Text(), nullable=False),
    sa.Column('media_preview_url', sa.Text(), nullable=True),
    sa.Column('media_product_type', sa.String(length=16), nullable=False),
    sa.Column('author_id', sa.String(length=64), nullable=False),
    sa.Column('author_username', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('commented_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('pending', 'answered', 'unanswered', 'owner_replied', 'skipped', 'dismissed', name='commentstatus', native_enum=False, length=32), nullable=False),
    sa.Column('category', sa.Enum('price', 'availability', 'product', 'order', 'complaint', 'praise', 'spam', 'other', name='commentcategory', native_enum=False, length=32), nullable=True),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('public_reply', sa.Text(), nullable=True),
    sa.Column('public_reply_id', sa.String(length=64), nullable=True),
    sa.Column('private_reply', sa.Text(), nullable=True),
    sa.Column('private_reply_sent', sa.Boolean(), nullable=False),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.String(length=255), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_instagram_comments_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_comments')),
    sa.UniqueConstraint('ig_comment_id', name=op.f('uq_instagram_comments_ig_comment_id'))
    )
    op.create_index(op.f('ix_instagram_comments_shop_id'), 'instagram_comments', ['shop_id'], unique=False)
    op.create_index(op.f('ix_instagram_comments_status'), 'instagram_comments', ['status'], unique=False)
    op.create_table('instagram_insights',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.String(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_instagram_insights_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_insights')),
    sa.UniqueConstraint('shop_id', name=op.f('uq_instagram_insights_shop_id'))
    )
    op.create_table('instagram_posts',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('ig_media_id', sa.String(length=64), nullable=False),
    sa.Column('permalink', sa.Text(), nullable=False),
    sa.Column('caption', sa.Text(), nullable=False),
    sa.Column('media_type', sa.String(length=32), nullable=False),
    sa.Column('preview_url', sa.Text(), nullable=True),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_instagram_posts_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_posts'))
    )
    op.create_index(op.f('ix_instagram_posts_shop_id'), 'instagram_posts', ['shop_id'], unique=False)
    op.create_table('knowledge_entries',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('section', sa.Enum('about', 'shipping', 'payment', 'returns', 'contact', 'faq', 'free_text', 'file', name='knowledgesection', native_enum=False, length=32), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('source_filename', sa.String(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_knowledge_entries_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_entries'))
    )
    op.create_index(op.f('ix_knowledge_entries_shop_id'), 'knowledge_entries', ['shop_id'], unique=False)
    op.create_table('payments',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('gateway', sa.String(length=32), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'paid', 'failed', name='paymentstatus', native_enum=False, length=32), nullable=False),
    sa.Column('session_id', sa.String(length=255), nullable=True),
    sa.Column('ref_id', sa.String(length=255), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_payments_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('session_id', name=op.f('uq_payments_session_id'))
    )
    op.create_index(op.f('ix_payments_shop_id'), 'payments', ['shop_id'], unique=False)
    op.create_table('product_sources',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('google_sheet', 'upload', name='productsourcekind', native_enum=False, length=32), nullable=False),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('column_mapping', sa.JSON(), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_product_sources_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_sources')),
    sa.UniqueConstraint('shop_id', name=op.f('uq_product_sources_shop_id'))
    )
    op.create_table('scheduled_stories',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('media_kind', sa.String(length=8), nullable=False),
    sa.Column('file_name', sa.String(length=96), nullable=False),
    sa.Column('content_type', sa.String(length=48), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=48), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('scheduled', 'processing', 'published', 'failed', name='storystatus', native_enum=False, length=32), nullable=False),
    sa.Column('container_id', sa.String(length=64), nullable=True),
    sa.Column('ig_media_id', sa.String(length=64), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.String(length=255), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_scheduled_stories_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scheduled_stories'))
    )
    op.create_index(op.f('ix_scheduled_stories_ig_media_id'), 'scheduled_stories', ['ig_media_id'], unique=False)
    op.create_index(op.f('ix_scheduled_stories_scheduled_at'), 'scheduled_stories', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_scheduled_stories_shop_id'), 'scheduled_stories', ['shop_id'], unique=False)
    op.create_index(op.f('ix_scheduled_stories_status'), 'scheduled_stories', ['status'], unique=False)
    op.create_table('teach_proposals',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('source_label', sa.String(length=500), nullable=False),
    sa.Column('status', sa.Enum('pending', 'applied', 'discarded', name='proposalstatus', native_enum=False, length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=False),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_teach_proposals_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teach_proposals'))
    )
    op.create_index(op.f('ix_teach_proposals_shop_id'), 'teach_proposals', ['shop_id'], unique=False)
    op.create_table('wallet_entries',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('topup', 'usage', 'bonus', 'adjustment', name='walletentrykind', native_enum=False, length=32), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('balance_after_cents', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_wallet_entries_shop_id_shops'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wallet_entries'))
    )
    op.create_index('ix_wallet_entries_shop_created', 'wallet_entries', ['shop_id', 'created_at'], unique=False)
    op.create_table('messages',
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('sender', sa.Enum('customer', 'bot', 'owner', name='messagesender', native_enum=False, length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=True),
    sa.Column('unanswered', sa.Boolean(), nullable=False),
    sa.Column('unanswered_resolved', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('off_topic', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('external_id', name=op.f('uq_messages_external_id'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_table('products',
    sa.Column('shop_id', sa.Uuid(), nullable=False),
    sa.Column('origin', sa.Enum('manual', 'sheet', 'file', 'teach', name='productorigin', native_enum=False, length=32), server_default='manual', nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=True),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('sku', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=120), nullable=True),
    sa.Column('color', sa.String(length=64), nullable=True),
    sa.Column('size', sa.String(length=64), nullable=True),
    sa.Column('price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('stock', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('extra', sa.JSON(), nullable=False),
    sa.Column('post_url', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name=op.f('fk_products_shop_id_shops'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_id'], ['product_sources.id'], name=op.f('fk_products_source_id_product_sources'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products'))
    )
    op.create_index(op.f('ix_products_shop_id'), 'products', ['shop_id'], unique=False)
    op.create_index('ix_products_shop_name', 'products', ['shop_id', 'name'], unique=False)
    op.create_index(op.f('ix_products_source_id'), 'products', ['source_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_products_source_id'), table_name='products')
    op.drop_index('ix_products_shop_name', table_name='products')
    op.drop_index(op.f('ix_products_shop_id'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_wallet_entries_shop_created', table_name='wallet_entries')
    op.drop_table('wallet_entries')
    op.drop_index(op.f('ix_teach_proposals_shop_id'), table_name='teach_proposals')
    op.drop_table('teach_proposals')
    op.drop_index(op.f('ix_scheduled_stories_status'), table_name='scheduled_stories')
    op.drop_index(op.f('ix_scheduled_stories_shop_id'), table_name='scheduled_stories')
    op.drop_index(op.f('ix_scheduled_stories_scheduled_at'), table_name='scheduled_stories')
    op.drop_index(op.f('ix_scheduled_stories_ig_media_id'), table_name='scheduled_stories')
    op.drop_table('scheduled_stories')
    op.drop_table('product_sources')
    op.drop_index(op.f('ix_payments_shop_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_knowledge_entries_shop_id'), table_name='knowledge_entries')
    op.drop_table('knowledge_entries')
    op.drop_index(op.f('ix_instagram_posts_shop_id'), table_name='instagram_posts')
    op.drop_table('instagram_posts')
    op.drop_table('instagram_insights')
    op.drop_index(op.f('ix_instagram_comments_status'), table_name='instagram_comments')
    op.drop_index(op.f('ix_instagram_comments_shop_id'), table_name='instagram_comments')
    op.drop_table('instagram_comments')
    op.drop_index(op.f('ix_instagram_accounts_ig_user_id'), table_name='instagram_accounts')
    op.drop_table('instagram_accounts')
    op.drop_index(op.f('ix_conversations_shop_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_handoff_at'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_content_reports_shop_id'), table_name='content_reports')
    op.drop_table('content_reports')
    op.drop_table('shops')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('site_chat_usage')
    op.drop_table('gift_claims')
