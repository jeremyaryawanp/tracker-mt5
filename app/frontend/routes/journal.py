from urllib.parse import urlencode

from fasthtml.common import (
    H1,
    H2,
    A,
    Button,
    Div,
    Form,
    Input,
    Label,
    Option,
    P,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Textarea,
    Th,
    Thead,
    Tr,
)
from starlette.responses import RedirectResponse

from app.db import get_database
from app.frontend import format as fmt
from app.frontend.components import card, empty_state, page
from app.frontend.deps import current_user, filter_from_query
from app.frontend.routes.dashboard import INPUT, filter_bar
from app.services import journal
from app.services.accounts import list_accounts
from app.services.analytics import metrics, pips
from app.services.analytics.service import Analytics

PAGE_SIZE = 25
BREAKDOWNS = [("Symbol", lambda p: p.symbol), ("Session (entry)", lambda p: p.session),
              ("Direction", lambda p: p.direction), ("Setup", lambda p: p.setup),
              ("Emotional state", lambda p: p.emotional_state),
              ("Rules", lambda p: {True: "Followed", False: "Broken"}.get(p.rule_followed))]


def _qs(params, **override):
    items = [(k, v) for k, v in params.multi_items() if k not in override and v]
    items += [(k, v) for k, v in override.items() if v not in (None, "")]
    return urlencode(items)


def breakdown_table(title, items, cur):
    head = Tr(*[Th(h, cls="text-left px-2 py-1 text-slate-400 font-normal") for h in
                (title, "Trades", "Win rate", "Net", "PF", "Expectancy", "Avg R", "Avg hold")])
    body = [Tr(Td(b["key"]), Td(b["trades"]), Td(fmt.pct(b["win_rate"])),
               Td(fmt.money(b["net_profit"], cur), cls=fmt.tone(b["net_profit"])),
               Td(fmt.pf(b["profit_factor"], b["profit_factor_infinite"])),
               Td(fmt.money(b["expectancy"])), Td(fmt.num(b["avg_r_multiple"], na="—")),
               Td(fmt.duration(b["avg_holding_seconds"])), cls="border-t border-slate-800")
            for b in items]
    return card(H2(title, cls="font-semibold mb-2"),
                Table(Thead(head), Tbody(*body), cls="w-full text-sm [&_td]:px-2 [&_td]:py-1"))


def register(fh, settings):
    def _user(db, sess):
        return current_user(db, settings, sess)

    @fh.route("/analytics", methods=["get"])
    def get_analytics(req, sess):
        with get_database().session() as db:
            user = _user(db, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            svc = Analytics(db, user)
            f = filter_from_query(req.query_params)
            parts = [H1("Pairs & strategy", cls="text-2xl font-semibold"),
                     card(filter_bar(list_accounts(db, user), f, "/analytics"))]
            groups = svc.by_currency(svc.rows(f))
            if not groups:
                parts.append(empty_state("No closed trades match these filters."))
            for cur, rows in groups.items():
                parts += [breakdown_table(t, metrics.breakdown(rows, k), cur)
                          for t, k in BREAKDOWNS]
                mistakes: dict[str, list] = {}
                for r in rows:
                    for m in r.mistakes:
                        mistakes.setdefault(m, []).append(r)
                parts.append(breakdown_table(
                    "Mistake", metrics.breakdown(
                        [r for v in mistakes.values() for r in v],
                        lambda p, names=list(mistakes): next(
                            (m for m in names if m in p.mistakes), None)), cur)
                    if mistakes else card(P("No mistakes tagged yet.", cls="text-slate-400")))
            return page("Pairs & strategy", *parts, active="/analytics", user=user.username)

    @fh.route("/trades", methods=["get"])
    def get_trades(req, sess):
        with get_database().session() as db:
            user = _user(db, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            qp = req.query_params
            f = filter_from_query(qp)
            pg = int(qp.get("page", "1")) if qp.get("page", "1").isdigit() else 1
            sort = qp.get("sort", "close_time")
            rows, total = journal.list_trades(db, user, f, q=qp.get("q"), page=pg,
                                              page_size=PAGE_SIZE, sort=sort,
                                              desc=qp.get("order", "desc") == "desc")
            tz = Analytics(db, user).tz
            extra = (Label("Search", Input(name="q", value=qp.get("q", ""),
                                           placeholder="symbol, id, setup, tag", cls=INPUT),
                           cls="text-xs grid"),
                     Label("Outcome", Select(Option("Any", value=""), *[
                         Option(o, value=o, selected=qp.get("outcome") == o)
                         for o in ("WIN", "LOSS", "BREAKEVEN")], name="outcome", cls=INPUT),
                         cls="text-xs grid"))
            head = Tr(*[Th(A(h, href=f"/trades?{_qs(qp, sort=s, page=None)}") if s else h,
                           cls="text-left px-2 py-1 text-slate-400 font-normal")
                        for h, s in (("Closed", "close_time"), ("Symbol", "symbol"),
                                     ("Dir", None), ("Lots", "volume"), ("Pips", None),
                                     ("R", None), ("Net", "net"), ("Setup", None),
                                     ("Tags", None))])
            body = [Tr(Td(A(r.close_time.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                            href=f"/trades/{r.id}", cls="text-indigo-400")),
                       Td(r.symbol), Td(r.direction), Td(fmt.num(r.volume)),
                       Td(fmt.num(pips.actual_exit_pips(r), 1, "—")),
                       Td(fmt.num(pips.r_multiple(r), 2, "—")),
                       Td(fmt.money(r.net, r.currency), cls=fmt.tone(r.net)),
                       Td(r.setup or "—"), Td(", ".join(r.tags + r.mistakes) or "—",
                                              cls="text-xs text-slate-400"),
                       cls="border-t border-slate-800") for r in rows]
            pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
            pager = Div(
                A("← Prev", href=f"/trades?{_qs(qp, page=pg - 1)}", cls="text-indigo-400")
                if pg > 1 else Span(""),
                Span(f"Page {pg} of {pages} · {total} trades", cls="text-sm text-slate-400"),
                A("Next →", href=f"/trades?{_qs(qp, page=pg + 1)}", cls="text-indigo-400")
                if pg < pages else Span(""),
                A("Export CSV", href=f"/api/v1/trades/export.csv?{_qs(qp, page=None)}",
                  cls="ml-auto text-sm bg-slate-800 rounded px-3 py-1"),
                cls="flex items-center gap-4")
            content = (card(Table(Thead(head), Tbody(*body),
                                  cls="w-full text-sm [&_td]:px-2 [&_td]:py-1"), pager)
                       if rows else empty_state("No trades match.", "Clear search or filters."))
            return page("Journal", H1("Trade journal", cls="text-2xl font-semibold"),
                        card(filter_bar(list_accounts(db, user), f, "/trades", extra)),
                        content, active="/trades", user=user.username)

    @fh.route("/trades/{pid}", methods=["get"])
    def get_trade(pid: int, sess):
        with get_database().session() as db:
            user = _user(db, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            p = journal.get_position(db, user, pid)
            if p is None:
                return page("Not found", empty_state("Trade not found."), user=user.username)
            tz = Analytics(db, user).tz
            a = p.annotation
            tags = {k: ", ".join(t.name for t in (a.tags if a else []) if t.kind == kind)
                    for k, kind in journal.TAG_FIELDS.items()}
            sl_ok = p.sl_tp_source in ("OPEN_ORDER", "OPEN_DEAL")

            def val(f):
                return (getattr(a, f) or "") if a else ""

            def fact(label, value):
                return Div(Div(label, cls="text-xs text-slate-500"), Div(value))

            facts = Div(
                fact("Symbol / direction", f"{p.symbol} {p.direction}"),
                fact("Volume", fmt.num(p.volume_lots)),
                fact("Open", f"{p.open_time.astimezone(tz):%Y-%m-%d %H:%M} @ {p.open_price}"),
                fact("Close", f"{p.close_time.astimezone(tz):%Y-%m-%d %H:%M} @ {p.close_price}"
                     if p.close_time else "Open position"),
                fact("Initial SL", str(p.initial_sl_price) if sl_ok and p.initial_sl_price
                     else fmt.NA),
                fact("Initial TP", str(p.initial_tp_price) if sl_ok and p.initial_tp_price
                     else fmt.NA),
                fact("Gross / commission / swap", f"{fmt.money(p.realized_gross_profit)} / "
                     f"{fmt.money(p.commission)} / {fmt.money(p.swap)}"),
                fact("Net", Span(fmt.money(p.realized_net_profit, p.account_currency),
                                 cls=fmt.tone(p.realized_net_profit))),
                fact("Session (entry)", p.trading_session or "—"),
                fact("Exits", str(p.exit_count)),
                cls="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm")

            def field(label, name, area=False):
                el = (Textarea(val(name), name=name, rows=3, cls=INPUT + " w-full") if area
                      else Input(name=name, value=val(name), cls=INPUT + " w-full"))
                return Label(label, el, cls="text-xs grid gap-1")

            rule = a.rule_followed if a else None
            form = Form(
                Div(field("Setup", "setup_name"), field("Market condition", "market_condition"),
                    field("Entry timeframe", "entry_timeframe"),
                    field("Higher-timeframe context", "higher_timeframe_context"),
                    field("Session override", "trading_session_override"),
                    field("Emotional state", "emotional_state"),
                    Label("Rules followed?", Select(*[
                        Option(lbl, value=v, selected=rule is s) for lbl, v, s in
                        (("Unknown", "", None), ("Yes", "yes", True), ("No", "no", False))],
                        name="rule_followed", cls=INPUT), cls="text-xs grid gap-1"),
                    field("Screenshot link", "screenshot_ref"),
                    cls="grid md:grid-cols-4 gap-3"),
                Div(*[Label(lbl + " (comma-separated)", Input(name=k, value=tags[k],
                                                              cls=INPUT + " w-full"),
                            cls="text-xs grid gap-1") for k, lbl in
                      (("mistakes", "Mistakes"), ("ict_tags", "ICT concepts"),
                       ("setup_tags", "Setup tags"), ("custom_tags", "Custom tags"))],
                    cls="grid md:grid-cols-4 gap-3"),
                Div(field("Entry reason", "entry_reason", True),
                    field("Exit reason", "exit_reason", True),
                    field("Notes", "personal_notes", True), cls="grid md:grid-cols-3 gap-3"),
                Button("Save journal entry", cls="bg-indigo-600 rounded px-3 py-2 text-sm"),
                method="post", action=f"/trades/{p.id}", cls="space-y-3")
            return page(f"{p.symbol} trade", A("← Journal", href="/trades",
                                               cls="text-indigo-400 text-sm"),
                        H1(f"{p.symbol} {p.direction} · #{p.external_position_id}",
                           cls="text-2xl font-semibold"),
                        card(facts), card(H2("Journal", cls="font-semibold mb-2"), form),
                        active="/trades", user=user.username)

    @fh.route("/trades/{pid}", methods=["post"])
    async def post_trade(pid: int, req, sess):
        form = await req.form()
        with get_database().session() as db:
            user = _user(db, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            p = journal.get_position(db, user, pid)
            if p is None:
                return RedirectResponse("/trades", status_code=303)
            data = {f: str(form.get(f, ""))[:5000] for f in journal.TEXT_FIELDS}
            data["rule_followed"] = {"yes": True, "no": False}.get(form.get("rule_followed"))
            for k in journal.TAG_FIELDS:
                data[k] = [t for t in str(form.get(k, "")).split(",") if t.strip()][:50]
            journal.upsert_annotation(db, user, p, data)
            db.commit()
        return RedirectResponse(f"/trades/{pid}", status_code=303)
