from fasthtml.common import H1, Button, Div, Form, Input, Label, P
from sqlalchemy import select
from starlette.responses import RedirectResponse

from app.db import get_database
from app.frontend.components import card, page
from app.models import User
from app.security import RateLimiter, verify_password

INPUT = "bg-slate-900 border border-slate-700 rounded px-2 py-1 w-full"


def register(fh, settings):
    limiter = RateLimiter(settings.login_attempts_per_window, 300)
    fh.state.login_limiter = limiter

    def login_page(error: str | None = None):
        return page("Sign in", Div(card(
            H1("Sign in", cls="text-xl font-semibold mb-3"),
            P(error, cls="text-rose-400 text-sm mb-2") if error else "",
            Form(Label("Username", Input(name="username", autocomplete="username", cls=INPUT),
                       cls="grid gap-1 text-sm"),
                 Label("Password", Input(name="password", type="password",
                                         autocomplete="current-password", cls=INPUT),
                       cls="grid gap-1 text-sm"),
                 Button("Sign in", cls="bg-indigo-600 rounded px-3 py-2 text-sm w-full"),
                 method="post", action="/login", cls="space-y-3")), cls="max-w-sm mx-auto"))

    @fh.route("/login", methods=["get"])
    def get(sess):
        if not settings.auth_enabled:
            return RedirectResponse("/", status_code=303)
        return login_page()

    @fh.route("/login", methods=["post"])
    async def post(req, sess):
        if not settings.auth_enabled:
            return RedirectResponse("/", status_code=303)
        ip = req.client.host if req.client else "unknown"
        if not limiter.hit(ip):
            r = login_page("Too many attempts. Try again in a few minutes.")
            return r
        form = await req.form()
        username, password = str(form.get("username", "")), str(form.get("password", ""))
        ok = (username == settings.admin_username
              and verify_password(password, settings.admin_password_hash))
        if not ok:
            return login_page("Invalid username or password.")
        with get_database().session() as db:
            user = db.scalar(select(User).where(User.username == username))
        limiter.reset(ip)
        sess.clear()
        sess["user_id"] = user.id
        return RedirectResponse("/", status_code=303)

    @fh.route("/logout", methods=["get", "post"])
    def logout(sess):
        sess.clear()
        return RedirectResponse("/login" if settings.auth_enabled else "/", status_code=303)
