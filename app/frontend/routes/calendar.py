from dataclasses import replace
from datetime import date, datetime, timedelta

from fasthtml.common import H1, H2, A, Div, Span, Table, Tbody, Td, Th, Thead, Tr
from starlette.responses import RedirectResponse

from app.db import get_database
from app.frontend import format as fmt
from app.frontend.components import card, empty_state, page
from app.frontend.deps import current_user, filter_from_query
from app.frontend.routes.dashboard import filter_bar
from app.services.accounts import list_accounts
from app.services.analytics import metrics
from app.services.analytics.service import Analytics
from app.services.reporting.calendar import month_grid, parse_month, rows_on_day, shift_month


def _bg(net):
    if net is None:
        return "bg-slate-900/40"
    return "bg-emerald-900/50 border-emerald-700" if net > 0 else (
        "bg-rose-900/50 border-rose-700" if net < 0 else "bg-slate-800")


def trade_table(rows, tz):
    head = Thead(Tr(*[Th(h, cls="text-left px-2 py-1 text-slate-400 font-normal") for h in
                      ("Symbol", "Dir", "Lots", "Open", "Close", "Session", "Net", "")]))
    body = [Tr(Td(r.symbol), Td(r.direction), Td(fmt.num(r.volume)),
               Td(r.open_time.astimezone(tz).strftime("%m-%d %H:%M")),
               Td(r.close_time.astimezone(tz).strftime("%m-%d %H:%M")), Td(r.session),
               Td(fmt.money(r.net), cls=fmt.tone(r.net)),
               Td(A("Details", href=f"/trades/{r.id}", cls="text-indigo-400")),
               cls="border-t border-slate-800") for r in rows]
    return Table(head, Tbody(*body), cls="w-full text-sm [&_td]:px-2 [&_td]:py-1")


def register(fh, settings):
    @fh.route("/calendar")
    def get(req, sess):
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            svc = Analytics(db, user)
            f = filter_from_query(req.query_params)
            first = parse_month(req.query_params.get("month"), datetime.now(svc.tz).date())
            f_month = replace(f, date_from=first,
                              date_to=shift_month(first, 1) - timedelta(days=1))
            rows = svc.rows(f_month)
            qs = "&".join(f"{k}={v}" for k, v in req.query_params.multi_items()
                          if k != "month" and v)
            nav = Div(
                A("← Prev", href=f"/calendar?month={shift_month(first, -1):%Y-%m}&{qs}",
                  cls="text-indigo-400"),
                H2(first.strftime("%B %Y"), cls="text-xl font-semibold"),
                A("Next →", href=f"/calendar?month={shift_month(first, 1):%Y-%m}&{qs}",
                  cls="text-indigo-400"),
                A("Today", href=f"/calendar?{qs}", cls="text-sm text-slate-400 ml-4"),
                cls="flex items-center gap-4")
            parts = [Div(H1("Trading calendar", cls="text-2xl font-semibold"),
                         Span(f"Days by close time in {user.display_timezone}",
                              cls="text-xs text-slate-500"), cls="flex items-baseline gap-3"),
                     card(filter_bar(list_accounts(db, user), f, "/calendar")), nav]
            groups = svc.by_currency(rows)
            if not groups:
                parts.append(empty_state("No closed trades in this month.",
                                         "Use the arrows to navigate or change filters."))
            for cur, items in groups.items():
                g = month_grid(items, svc.tz, first, user.week_start)
                hdr = Tr(*[Th(n, cls="py-1 text-slate-400 font-normal")
                           for n in g["weekday_names"]], Th("Week", cls="text-slate-400"))
                body = []
                for w in g["weeks"]:
                    cells = []
                    for c in w["days"]:
                        content = [Div(str(c["date"].day), cls="text-xs text-slate-400")]
                        if c["trades"]:
                            content += [Div(fmt.money(c["net"]),
                                            cls=f"font-semibold {fmt.tone(c['net'])}"),
                                        Div(f"{c['trades']} trades · {c['wins']}W/{c['losses']}L",
                                            cls="text-[11px] text-slate-400")]
                        attrs = {}
                        if c["trades"]:
                            attrs = {"hx_get": f"/calendar/day/{c['date']}?{qs}",
                                     "hx_target": "#day-detail", "role": "button"}
                        cells.append(Td(Div(*content, cls=f"h-20 p-1 rounded border "
                                            f"border-slate-800 {_bg(c['net'])} "
                                            f"{'cursor-pointer' if c['trades'] else ''} "
                                            f"{'' if c['in_month'] else 'opacity-30'}",
                                            **attrs), cls="p-0.5 align-top w-[13%]"))
                    cells.append(Td(Div(fmt.money(w["net"]) if w["trades"] else "—",
                                        cls=f"text-sm {fmt.tone(w['net'])}"),
                                    Div(f"{w['trades']} trades", cls="text-[11px] text-slate-500"),
                                    cls="px-2 align-middle"))
                    body.append(Tr(*cells))
                parts.append(card(
                    Div(Span(f"Month net ({cur}): ", cls="text-slate-400"),
                        Span(fmt.money(g["net"], cur), cls=f"font-semibold {fmt.tone(g['net'])}"),
                        Span(f" · {g['trades']} trades · {g['green_days']} green / "
                             f"{g['red_days']} red days", cls="text-slate-400 text-sm"),
                        cls="mb-3"),
                    Table(Thead(hdr), Tbody(*body), cls="w-full table-fixed")))
            parts.append(Div(id="day-detail"))
            return page("Calendar", *parts, active="/calendar", user=user.username)

    @fh.route("/calendar/day/{day}")
    def get_day(day: str, req, sess):
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            try:
                d = date.fromisoformat(day)
            except ValueError:
                return empty_state("Invalid date.")
            svc = Analytics(db, user)
            f = replace(filter_from_query(req.query_params), date_from=d, date_to=d)
            rows = rows_on_day(svc.rows(f), svc.tz, d)
            if not rows:
                return empty_state(f"No closed trades on {d}.")
            s = metrics.summary(rows, svc.tz)
            return card(H2(f"{d:%A, %d %B %Y}", cls="text-lg font-semibold"),
                        Div(f"Net {fmt.money(s['net_profit'])} · {s['trade_count']} trades · "
                            f"win rate {fmt.pct(s['win_rate'])}",
                            cls=f"text-sm mb-2 {fmt.tone(s['net_profit'])}"),
                        trade_table(rows, svc.tz))
