import os
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET = "change-me"


class Settings(BaseSettings):
    # APP_ENV_FILE="" disables the .env file; the test suite uses this so a developer's local
    # settings (dry run, real API keys) never leak into tests.
    model_config = SettingsConfigDict(
        env_file=os.environ.get("APP_ENV_FILE", ".env") or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Replisto"
    environment: str = "development"  # development | production | test
    public_base_url: str = "http://localhost:8000"
    # The panel; users are sent back here after connecting Instagram.
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    # "arq" (Redis, production) or "inline" (in-process; local dev without Redis, jobs are
    # lost on restart).
    queue_backend: Literal["arq", "inline"] = "arq"

    # Wait this long after a customer's message before replying, so bursts of short
    # messages ("salam" / "in mantoo" / "size 44 dari?") get one combined answer.
    reply_debounce_seconds: float = 5.0

    # JWT signing key and Fernet key for encrypting third-party tokens at rest.
    secret_key: str = _INSECURE_SECRET
    encryption_key: str = ""
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Meta / Instagram API with Instagram Login. These are the *Instagram* app ID and secret
    # shown under Instagram > API setup with Instagram login (not the Facebook app ID).
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_webhook_verify_token: str = ""
    meta_graph_api_version: str = "v23.0"
    # Log outgoing DMs instead of sending them (local testing with the webhook simulator).
    instagram_dry_run: bool = False

    # Any OpenAI-compatible provider (direct or an Iranian gateway).
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    # Optional separate model for reading uploaded images (menus, price lists); must accept
    # image input. Falls back to llm_model.
    llm_vision_model: str = ""
    llm_timeout_seconds: float = 45.0
    llm_max_output_tokens: int = 700
    llm_temperature: float = 0.3

    # Per-shop limits.
    knowledge_char_limit: int = 40_000
    product_row_limit: int = 2_000
    upload_max_bytes: int = 5 * 1024 * 1024
    # How often Google Sheets product sources are re-read.
    product_sync_interval_minutes: int = 5
    # Longest text (a Google Doc, a pasted price list) read in one "teach the bot" request.
    teach_max_chars: int = 60_000

    # Channels. Instagram is the messaging channel; switch it off to pause it server-wide
    # (e.g. while the Meta app is in review).
    instagram_enabled: bool = True

    # A safety net against one chatty customer (or a spammer) draining a shop's wallet.
    max_bot_replies_per_customer_hour: int = 30

    # Billing: shops top up a wallet and every AI answer is paid from it. Amounts in rial.
    billing_enabled: bool = True
    # The sign-up gift (500,000 rial = 50,000 toman). Given once per person, after the owner
    # verifies their mobile number.
    signup_credit_rial: int = 500_000
    usage_rial_per_1k_prompt_tokens: int = 300
    usage_rial_per_1k_completion_tokens: int = 1_200
    usage_min_rial_per_reply: int = 500
    # The owner is told once the balance drops below this.
    low_balance_rial: int = 100_000
    topup_min_rial: int = 500_000
    topup_max_rial: int = 500_000_000

    # Wallet top-ups: "aban" (Aban Gateway, card-to-card confirmed automatically from the bank
    # SMS; no e-Namad needed) or "zarinpal".
    payment_gateway: str = "aban"
    # Aban Gateway: API token (ag_live_… or ag_test_… for testing without money) and the
    # webhook secret, both from its panel (Settings → API tokens / Webhook).
    aban_api_token: str = ""
    aban_webhook_secret: str = ""
    aban_api_base: str = "https://api.abangateway.ir"
    # How long an Aban invoice stays payable.
    aban_invoice_minutes: int = 30

    # Zarinpal payment gateway (alternative).
    zarinpal_merchant_id: str = ""
    zarinpal_sandbox: bool = False

    # Outgoing email (password reset). Without SMTP_HOST the link is only logged.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Replisto <no-reply@replisto.app>"
    smtp_starttls: bool = True
    password_reset_minutes: int = 30
    email_verify_days: int = 7
    # The panel stays closed until the owner clicks the emailed link (only /me, resending
    # the link and deleting the account work before that).
    require_verified_email: bool = True

    # SMS for verifying mobile numbers: "kavenegar" or "smsir" (both send a code with a
    # template approved in their panel). Empty: codes are only logged (development).
    sms_provider: str = ""
    sms_api_key: str = ""
    # Kavenegar: the template name; SMS.ir: the template id. The template has one
    # parameter, the code (Kavenegar: %token, SMS.ir: CODE).
    sms_template: str = ""
    phone_code_minutes: int = 10

    # Wrong passwords: after this many failures for one email (or 4x for one IP) within the
    # window, logging in is refused until the window passes.
    login_max_failures: int = 5
    login_failure_window_minutes: int = 15

    # Error monitoring: Sentry (or a Sentry-compatible service such as GlitchTip).
    sentry_dsn: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.is_production:
            if self.secret_key == _INSECURE_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of 32+ chars")
            if not self.encryption_key:
                raise ValueError("ENCRYPTION_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
