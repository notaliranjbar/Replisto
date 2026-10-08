"""Error monitoring: Sentry (optional).

Off unless SENTRY_DSN is set: errors and their stack traces then go to Sentry (or a
Sentry-compatible service such as a self-hosted GlitchTip).
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_configured = False


def setup_monitoring(component: str) -> None:
    """Call once per process (API or worker)."""
    global _configured
    if _configured:
        return
    _configured = True
    settings = get_settings()
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                server_name=component,
                traces_sample_rate=0.0,
                send_default_pii=False,
            )
            logger.info("sentry enabled for %s", component)
        except Exception:  # monitoring must never stop the app from starting
            logger.exception("could not start sentry")
