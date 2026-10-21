from datetime import date, datetime, timedelta

from fasthtml.common import (
    H1,
    H2,
    A,
    Button,
    Div,
    Form,
    Input,
    Label,
    Li,
    Option,
    P,
    Select,
    Table,
    Tbody,
    Td,
    Textarea,
    Th,
    Thead,
    Tr,
    Ul,
)
from starlette.responses import RedirectResponse

from app.db import get_database
from app.frontend import format as fmt
from app.frontend.components import card, page
from app.frontend.deps import current_user
from app.frontend.routes.dashboard import INPUT
from app.services.accounts import get_account, list_accounts
from app.services.analytics.service import Analytics
from app.services.reporting import llm
from app.services.reporting.review import REFLECTION_FIELDS, build_review, get_review, save_review

LABELS = {"net_profit": "Net profit", "trade_count": "Trades", "win_rate": "Win rate %",
          "profit_factor": "Profit factor", "expectancy": "Expectancy", "avg_win": "Avg win",
          "avg_loss": "Avg loss", "max_drawdown": "Max drawdown", "avg_r_multiple": "Avg R"}


def _week(q, tz) -> date:
    try:
        return date.fromisoformat(q.get("week", ""))
    except ValueError:
        return datetime.now(tz).date()


def _account(q, db, user) -> int | None:
    a = q.get("account_id", "")
    return int(a) if a.isdigit() and get_account(db, user, int(a)) else None


def register(fh, settings):
    @fh.route("/review", methods=["get"])
    def get(req, sess):
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            q = req.query_params
            tz = Analytics(db, user).tz
            acc = _account(q, db, user)
            data = build_review(db, user, _week(q, tz), [acc] if acc else None)
            start = data["week_start"]
            saved = get_review(db, user, start, acc)
            aq = f"&account_id={acc}" if acc else ""
            nav = Div(
                A("← Previous week", href=f"/review?week={start - timedelta(days=7)}{aq}",
                  cls="text-indigo-400"),
                H2(f"{start:%d %b} – {data['week_end']:%d %b %Y}", cls="text-xl font-semibold"),
                A("Next week →", href=f"/review?week={start + timedelta(days=7)}{aq}",
                  cls="text-indigo-400"),
                Form(Select(Option("All accounts", value=""), *[
                    Option(a.account_name, value=str(a.id), selected=a.id == acc)
                    for a in list_accounts(db, user)], name="account_id", cls=INPUT,
                    onchange="this.form.submit()"),
                    Input(type="hidden", name="week", value=str(start)),
                    method="get", action="/review", cls="ml-auto"),
                cls="flex items-center gap-4")
            parts = [H1("Weekly review", cls="text-2xl font-semibold"), nav]
            for cur, d in data["by_currency"].items():
                s, p, disc = d["current"], d["previous"], d["discipline"]
                rows = []
                for k, label in LABELS.items():
                    delta = d["delta"][k]
                    rows.append(Tr(Td(label), Td(fmt.num(s[k], na="—")),
                                   Td(fmt.num(p[k], na="—")),
                                   Td(fmt.num(delta, na="—"),
                                      cls=fmt.tone(-delta if delta is not None and
                                                   k in ("avg_loss", "max_drawdown")
                                                   else delta)),
                                   cls="border-t border-slate-800"))
                parts.append(Div(
                    card(H2(f"This week vs previous ({cur})", cls="font-semibold mb-2"),
                         Table(Thead(Tr(*[Th(h, cls="text-left text-slate-400 font-normal")
                                          for h in ("Metric", "This week", "Previous", "Δ")])),
                               Tbody(*rows), cls="w-full text-sm [&_td]:py-1")),
                    card(H2("Discipline", cls="font-semibold mb-2"),
                         P(f"Rule adherence: {fmt.pct(disc['adherence_pct'])}"),
                         P(f"Followed: {disc['followed']['trades']} trades, "
                           f"{fmt.money(disc['followed']['net'])}"),
                         P(f"Broken: {disc['broken']['trades']} trades, "
                           f"{fmt.money(disc['broken']['net'])}"),
                         P(f"Not rated: {disc['unknown']['trades']} trades",
                           cls="text-slate-500"),
                         H2("Mistakes", cls="font-semibold mt-3"),
                         Ul(*[Li(f"{m['name']} ×{m['count']} ({fmt.money(m['net'])})"
                                 + (" — repeated" if m in d["repeated_mistakes"] else ""))
                              for m in disc["mistakes"]] or [Li("None tagged")],
                            cls="text-sm list-disc ml-5")),
                    cls="grid md:grid-cols-2 gap-4"))
            parts.append(card(H2("Automatic summary (rule-based)", cls="font-semibold mb-2"),
                              *[P(line, cls="text-sm") for line in
                                data["auto_summary"].splitlines()]))
            llm_on = settings.llm_reviews_enabled and bool(settings.llm_api_key)
            parts.append(card(
                H2("AI narrative (optional)", cls="font-semibold mb-2"),
                P(saved.llm_summary, cls="text-sm whitespace-pre-line")
                if saved and saved.llm_summary else "",
                Form(Button("Generate AI summary", cls="bg-slate-800 rounded px-3 py-1 text-sm"),
                     method="post", action=f"/review/llm?week={start}{aq}")
                if llm_on else P("Disabled. Set LLM_REVIEWS_ENABLED and LLM_API_KEY to enable; "
                                 "only aggregated metrics are sent.",
                                 cls="text-xs text-slate-500")))
            fields = [Label(f.replace("_", " ").capitalize(),
                            Textarea(getattr(saved, f) or "" if saved else "", name=f, rows=3,
                                     cls=INPUT + " w-full"), cls="text-xs grid gap-1")
                      for f in REFLECTION_FIELDS]
            parts.append(card(H2("Reflection", cls="font-semibold mb-2"),
                              Form(Div(*fields, cls="grid md:grid-cols-3 gap-3"),
                                   Button("Save review", cls="bg-indigo-600 rounded px-3 py-2 "
                                          "text-sm mt-3"),
                                   method="post", action=f"/review?week={start}{aq}")))
            return page("Weekly review", *parts, active="/review", user=user.username)

    @fh.route("/review", methods=["post"])
    async def post(req, sess):
        form = await req.form()
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            q = req.query_params
            acc = _account(q, db, user)
            data = build_review(db, user, _week(q, Analytics(db, user).tz),
                                [acc] if acc else None)
            save_review(db, user, data, {f: str(form.get(f, "")) for f in REFLECTION_FIELDS},
                        acc)
            db.commit()
        aq = f"&account_id={acc}" if acc else ""
        return RedirectResponse(f"/review?week={data['week_start']}{aq}", status_code=303)

    @fh.route("/review/llm", methods=["post"])
    def post_llm(req, sess):
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            q = req.query_params
            acc = _account(q, db, user)
            data = build_review(db, user, _week(q, Analytics(db, user).tz),
                                [acc] if acc else None)
            try:
                text = llm.generate_summary(settings, data)
            except Exception as exc:  # noqa: BLE001 - surface any provider failure in UI
                text = f"AI summary unavailable: {type(exc).__name__}"
            save_review(db, user, data, {"llm_summary": text}, acc)
            db.commit()
        aq = f"&account_id={acc}" if acc else ""
        return RedirectResponse(f"/review?week={data['week_start']}{aq}", status_code=303)
