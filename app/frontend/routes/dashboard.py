from fasthtml.common import H1, A, Button, Div, Form, Input, Label, Option, P, Select, Span

from app.db import get_database
from app.frontend import format as fmt
from app.frontend.charts import plot
from app.frontend.components import card, empty_state, page
from app.frontend.deps import current_user, filter_from_query
from app.services.accounts import list_accounts
from app.services.analytics import metrics
from app.services.analytics.service import Analytics

INPUT = "bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm"


def filter_bar(accounts, f, action="/", extra=()):
    acc_opts = [Option("All accounts", value="")] + [
        Option(f"{a.account_name}{' (SIMULATED)' if a.is_simulated else ''}", value=str(a.id),
               selected=bool(f.account_ids and a.id in f.account_ids)) for a in accounts]
    dir_val = f.directions[0] if f.directions else ""
    return Form(
        Label("Account", Select(*acc_opts, name="account_id", cls=INPUT), cls="text-xs grid"),
        Label("From", Input(type="date", name="date_from", value=f.date_from or "", cls=INPUT),
              cls="text-xs grid"),
        Label("To", Input(type="date", name="date_to", value=f.date_to or "", cls=INPUT),
              cls="text-xs grid"),
        Label("Symbol", Input(name="symbol", value=f.symbols[0] if f.symbols else "",
                              placeholder="e.g. XAUUSD", cls=INPUT), cls="text-xs grid"),
        Label("Direction", Select(Option("Both", value=""),
                                  *[Option(d, value=d, selected=d == dir_val)
                                    for d in ("BUY", "SELL")], name="direction", cls=INPUT),
              cls="text-xs grid"),
        *extra,
        Button("Apply", cls="bg-indigo-600 hover:bg-indigo-500 rounded px-3 py-1 text-sm"),
        A("Reset", href=action, cls="text-sm text-slate-400 self-center"),
        method="get", action=action, cls="flex flex-wrap gap-3 items-end",
    )


def kpi(label, value, cls="text-slate-100", hint=None):
    return card(Div(label, cls="text-xs uppercase tracking-wide text-slate-500"),
                Div(value, cls=f"text-xl font-semibold mt-1 {cls}"),
                Div(hint, cls="text-xs text-slate-500 mt-1") if hint else "", cls="p-3")


def kpi_grid(s, cur):
    return Div(
        kpi("Net profit", fmt.money(s["net_profit"], cur), fmt.tone(s["net_profit"])),
        kpi("Win rate", fmt.pct(s["win_rate"]),
            hint=f'{s["wins"]}W / {s["losses"]}L / {s["breakevens"]}BE'),
        kpi("Profit factor", fmt.pf(s["profit_factor"], s["profit_factor_infinite"])),
        kpi("Expectancy", fmt.money(s["expectancy"], cur), fmt.tone(s["expectancy"])),
        kpi("Trades", str(s["trade_count"]), hint=f'{s["long_count"]} long / '
                                                  f'{s["short_count"]} short'),
        kpi("Max drawdown", fmt.money(s["max_drawdown"], cur), "text-rose-300",
            hint=fmt.pct(s["max_drawdown_pct"]) + " of peak" if s["max_drawdown_pct"]
            is not None else "realized"),
        kpi("Avg win / loss", f'{fmt.money(s["avg_win"])} / {fmt.money(s["avg_loss"])}'),
        kpi("Gross profit / loss",
            f'{fmt.money(s["gross_profit"])} / {fmt.money(s["gross_loss"])}'),
        kpi("Avg holding", fmt.duration(s["avg_holding_seconds"])),
        kpi("Streaks", f'{s["max_consecutive_wins"]}W / {s["max_consecutive_losses"]}L',
            hint="max consecutive"),
        kpi("Avg planned R:R", fmt.num(s["avg_planned_rr"]),
            hint=f'{s["planned_rr_count"]} trades with SL+TP'),
        kpi("Avg R-multiple", fmt.num(s["avg_r_multiple"]),
            hint=f'{s["r_multiple_count"]} trades with initial SL'),
        kpi("Best day", f'{s["best_day"]["date"]} · {fmt.money(s["best_day"]["net"])}'
            if s["best_day"] else "—", "text-emerald-400 text-base"),
        kpi("Worst day", f'{s["worst_day"]["date"]} · {fmt.money(s["worst_day"]["net"])}'
            if s["worst_day"] else "—", "text-rose-400 text-base"),
        kpi("Best / worst session", f'{s["best_session"]} / {s["worst_session"]}',
            "text-base"),
        kpi("Costs", fmt.money(s["total_commission"] + s["total_swap"] + s["total_fees"], cur),
            hint=f'comm {fmt.money(s["total_commission"])} · swap {fmt.money(s["total_swap"])}'),
        cls="grid grid-cols-2 md:grid-cols-4 gap-3",
    )


def charts(svc, rows, f, cur):
    curve = svc.equity(f).get(cur, [])
    x = [p["time"] for p in curve]
    traces = [{"x": x, "y": [p["cumulative"] for p in curve], "name": "Realized P/L",
               "type": "scatter", "line": {"color": "#818cf8"}}]
    if curve and curve[0]["balance"] is not None:
        traces.append({"x": x, "y": [p["balance"] for p in curve], "name": "Balance",
                       "type": "scatter", "yaxis": "y2", "line": {"color": "#34d399"}})
    days = metrics.daily_pnl(rows, svc.tz)
    by_sym = metrics.breakdown(rows, lambda p: p.symbol)
    by_ses = metrics.breakdown(rows, lambda p: p.session)
    hist = metrics.histogram([r.net for r in rows], 20)
    weekday = metrics.hour_weekday_breakdowns(rows, svc.tz)["weekday"]
    bar = lambda items, k="key": {  # noqa: E731
        "x": [i[k] for i in items], "y": [i["net_profit"] for i in items], "type": "bar",
        "marker": {"color": ["#34d399" if i["net_profit"] >= 0 else "#f87171" for i in items]}}
    return Div(
        card(plot(traces, f"Equity curve ({cur}) — realized, by close time",
                  {"yaxis2": {"overlaying": "y", "side": "right", "showgrid": False},
                   "legend": {"orientation": "h"}})),
        card(plot([{"x": x, "y": [p["drawdown"] for p in curve], "type": "scatter",
                    "fill": "tozeroy", "line": {"color": "#f87171"}}], "Drawdown (realized)")),
        card(plot([{"x": [d["date"] for d in days], "y": [d["net"] for d in days],
                    "type": "bar", "marker": {"color": ["#34d399" if d["net"] >= 0
                                                        else "#f87171" for d in days]}}],
                  f"Daily P/L ({svc.tz})")),
        card(plot([{"x": [(h["from"] + h["to"]) / 2 for h in hist],
                    "y": [h["count"] for h in hist], "type": "bar",
                    "marker": {"color": "#818cf8"}}], "Trade P/L distribution")),
        card(plot([bar(by_sym)], "Net P/L by symbol")),
        card(plot([bar(by_ses)], "Net P/L by session (entry time)")),
        card(plot([bar(weekday)], "Net P/L by weekday (close time)")),
        card(plot([{"labels": ["Wins", "Losses", "Breakeven"],
                    "values": [sum(1 for r in rows if metrics.outcome(r) == o)
                               for o in ("WIN", "LOSS", "BREAKEVEN")],
                    "type": "pie", "hole": 0.5,
                    "marker": {"colors": ["#34d399", "#f87171", "#94a3b8"]}}], "Outcomes")),
        cls="grid md:grid-cols-2 gap-4",
    )


def register(fh, settings):
    @fh.route("/")
    def get(req, sess):
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                from starlette.responses import RedirectResponse
                return RedirectResponse("/login", status_code=303)
            accounts = list_accounts(db, user)
            f = filter_from_query(req.query_params)
            header = Div(H1("Dashboard", cls="text-2xl font-semibold"),
                         Span(f"Times in {user.display_timezone}",
                              cls="text-xs text-slate-500"), cls="flex items-baseline gap-3")
            if not accounts:
                return page("Dashboard", header, empty_state(
                    "No trading accounts yet.",
                    "Connect MT5/MT4 on Accounts & Sync, import a CSV, or load simulated "
                    "demo data."), Form(Button("Load SIMULATED demo data",
                                               cls="bg-indigo-600 rounded px-3 py-2 text-sm"),
                                        method="post", action="/accounts/demo",
                                        cls="text-center"), active="/", user=user.username)
            svc = Analytics(db, user)
            rows = svc.rows(f)
            groups = svc.by_currency(rows)
            simulated = any(a.is_simulated for a in svc.accounts(f))
            body = [header, card(filter_bar(accounts, f))]
            if simulated:
                body.append(Div("Includes SIMULATED demo data — not real trading results.",
                                cls="rounded bg-amber-900/40 border border-amber-700 "
                                    "text-amber-200 text-sm px-3 py-2"))
            if not rows:
                body.append(empty_state("No closed trades match these filters.",
                                        "Widen the date range or clear filters."))
            summaries = svc.summary(f)
            for cur, items in groups.items():
                if len(groups) > 1:
                    body.append(P(f"Account currency {cur}", cls="text-lg font-semibold"))
                body += [kpi_grid(summaries[cur], cur), charts(svc, items, f, cur)]
            return page("Dashboard", *body, active="/", user=user.username)

    @fh.route("/accounts/demo", methods=["post"])
    def post_demo(sess):
        from starlette.responses import RedirectResponse

        from app.services.demo import load_demo_account
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            load_demo_account(db, user)
        return RedirectResponse("/", status_code=303)
