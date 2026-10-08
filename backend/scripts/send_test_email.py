"""Send a test email with the server's SMTP settings, to check the setup.

    uv run python -m scripts.send_test_email you@example.com
    (on the server: docker compose exec api python -m scripts.send_test_email you@example.com)

Prints what went wrong if the provider refuses (wrong password, blocked port...).
"""

import asyncio
import sys

from app.core.config import get_settings
from app.services.email import action_email, send_email


async def main(to: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise SystemExit("SMTP_HOST is empty in the .env file")
    print(f"Sending through {settings.smtp_host}:{settings.smtp_port} as {settings.smtp_from}")
    text, page = action_email(
        title="Replisto test email",
        intro="If you can read this, the server's email settings work.",
        button="Open the panel",
        link=settings.frontend_url,
        note="This is a test email.",
    )
    await send_email(to, "Replisto test email", text, page)
    print("Sent. Check the inbox (and the spam folder).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.send_test_email you@example.com")
    asyncio.run(main(sys.argv[1]))
