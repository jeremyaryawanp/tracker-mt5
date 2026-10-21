from fasthtml.common import H1, FastHTML, Link, P, Script

from app.config import Settings
from app.frontend.components import card, page

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

    @fh.route("/")
    def get():
        return page(
            "Dashboard",
            H1("TradeJournal AI", cls="text-2xl font-semibold"),
            card(P("Backend foundation is running.", cls="text-slate-400")),
        )

    return fh
