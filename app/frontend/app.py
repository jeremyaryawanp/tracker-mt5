from fasthtml.common import FastHTML, Link, Script

from app.config import Settings

TAILWIND_CDN = "https://cdn.tailwindcss.com"
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def create_frontend(settings: Settings) -> FastHTML:
    hdrs = (
        Script(src=TAILWIND_CDN),
        Script(src=PLOTLY_CDN, defer=True),
        Link(rel="icon", href="data:,"),
    )
    fh = FastHTML(
        hdrs=hdrs,
        pico=False,
        secret_key=settings.app_secret_key,
        session_cookie="tj_session",
        sess_https_only=settings.app_env == "production",
        max_age=14 * 24 * 3600,
        key_fname=None,
        canonical=False,
        htmlkw={"class": "dark"},
    )
    fh.state.settings = settings

    from app.frontend.routes import accounts, auth, calendar, dashboard, journal, review

    auth.register(fh, settings)
    dashboard.register(fh, settings)
    accounts.register(fh, settings)
    calendar.register(fh, settings)
    journal.register(fh, settings)
    review.register(fh, settings)
    return fh
