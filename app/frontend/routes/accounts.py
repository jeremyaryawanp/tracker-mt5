from fasthtml.common import (
    H1,
    H2,
    Button,
    Code,
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
    Th,
    Thead,
    Tr,
)
from sqlalchemy import select
from starlette.responses import RedirectResponse

from app.db import get_database
from app.frontend import format as fmt
from app.frontend.components import card, page
from app.frontend.deps import current_user
from app.frontend.routes.dashboard import INPUT
from app.integrations.csv.adapter import CsvImportError, csv_to_batch
from app.models import SyncRun
from app.models.enums import Platform, ServerOffsetMode, SyncStatus
from app.services.accounts import create_account, get_account, issue_token, list_accounts
from app.services.synchronization.ingest import ingest_batch
from app.services.synchronization.positions import rebuild_account
from app.services.synchronization.reconcile import RetryNotPossible, reconcile, retry_sync_run

MAX_CSV = 5_000_000
BTN = "bg-slate-800 hover:bg-slate-700 rounded px-2 py-1 text-xs"


def _post(action, label, cls=BTN):
    return Form(Button(label, cls=cls), method="post", action=action, cls="inline")


def register(fh, settings):
    @fh.route("/accounts", methods=["get"])
    def get(req, sess):
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            flash = sess.pop("flash", None)
            token = sess.pop("new_token", None)
            parts = [H1("Accounts & sync", cls="text-2xl font-semibold")]
            if flash:
                parts.append(Div(flash, cls="rounded bg-slate-800 px-3 py-2 text-sm"))
            if token:
                parts.append(card(P("Collector token (shown once — copy it now):",
                                    cls="text-sm text-amber-300"),
                                  Code(token, cls="break-all text-xs")))
            for a in list_accounts(db, user):
                runs = list(db.scalars(select(SyncRun).where(SyncRun.account_id == a.id)
                                       .order_by(SyncRun.id.desc()).limit(8)))
                rec = reconcile(db, a)
                status = ("Reconciled" if rec["ok"] else "Mismatch — rebuild or re-sync")
                run_rows = [Tr(Td(r.id), Td(f"{r.started_at:%Y-%m-%d %H:%M} UTC"),
                               Td(str(r.source)), Td(str(r.status),
                                                     cls="text-rose-400" if r.status ==
                                                     SyncStatus.FAILED else ""),
                               Td(f"{r.deals_inserted}+ / {r.deals_duplicate}= / "
                                  f"{r.deals_updated}~"),
                               Td(r.error_message or ""),
                               Td(_post(f"/accounts/{a.id}/retry/{r.id}", "Retry")
                                  if r.status == SyncStatus.FAILED and r.failed_payload
                                  else ""), cls="border-t border-slate-800") for r in runs]
                csv_form = Form(
                    Input(type="file", name="file", accept=".csv,text/csv", cls="text-xs"),
                    Input(name="server_utc_offset_minutes", placeholder="offset min (e.g. 120)",
                          cls=INPUT + " w-36"),
                    Button("Import CSV", cls=BTN), method="post", enctype="multipart/form-data",
                    action=f"/accounts/{a.id}/csv", cls="flex gap-2 items-center"
                ) if a.platform != Platform.MOCK else ""
                parts.append(card(
                    Div(H2(a.account_name, cls="font-semibold"),
                        Span(f"{a.platform} · {a.account_currency} · id {a.id}",
                             cls="text-xs text-slate-400"),
                        Span("SIMULATED", cls="text-xs text-amber-300") if a.is_simulated else "",
                        Span(status, cls="text-xs " + ("text-emerald-400" if rec["ok"]
                                                       else "text-rose-400")),
                        Div(_post(f"/accounts/{a.id}/rebuild", "Rebuild positions"),
                            _post(f"/accounts/{a.id}/token", "New collector token"),
                            cls="ml-auto flex gap-2"), cls="flex items-center gap-3"),
                    P(f"Positions: {rec['closed_positions']} closed, "
                      f"{rec['open_positions']} open · "
                      f"deal net {fmt.money(rec['deal_net_total'])} vs position net "
                      f"{fmt.money(rec['position_net_total'])}", cls="text-xs text-slate-400"),
                    csv_form,
                    Table(Thead(Tr(*[Th(h, cls="text-left text-slate-400 font-normal") for h in
                                     ("Run", "Started", "Source", "Status",
                                      "Inserted/dup/updated", "Error", "")])),
                          Tbody(*run_rows), cls="w-full text-xs mt-2 [&_td]:py-1 [&_td]:px-1")
                    if runs else P("No sync runs yet.", cls="text-xs text-slate-500"),
                    cls="space-y-2"))
            parts.append(card(
                H2("Add account", cls="font-semibold mb-2"),
                Form(Label("Name", Input(name="account_name", required=True, cls=INPUT),
                           cls="text-xs grid"),
                     Label("Platform", Select(*[Option(p, value=p) for p in
                                                ("MT5", "MT4", "CSV")], name="platform",
                                              cls=INPUT), cls="text-xs grid"),
                     Label("Currency", Input(name="account_currency", value="USD", maxlength=3,
                                             cls=INPUT + " w-20"), cls="text-xs grid"),
                     Label("Broker UTC offset (minutes, blank = auto)",
                           Input(name="server_utc_offset_minutes", cls=INPUT + " w-28"),
                           cls="text-xs grid"),
                     Button("Create", cls="bg-indigo-600 rounded px-3 py-1 text-sm"),
                     method="post", action="/accounts", cls="flex flex-wrap gap-3 items-end"),
                P("The MT5 collector / MT4 EA uses the token shown after creation. Broker "
                  "passwords are never entered here.", cls="text-xs text-slate-500 mt-2"),
                Div(_post("/accounts/demo", "Load SIMULATED demo account"), cls="mt-3")))
            return page("Accounts", *parts, active="/accounts", user=user.username)

    def _owned(db, sess, account_id):
        user = current_user(db, settings, sess)
        return user, (get_account(db, user, account_id) if user else None)

    @fh.route("/accounts", methods=["post"])
    async def post(req, sess):
        form = await req.form()
        with get_database().session() as db:
            user = current_user(db, settings, sess)
            if user is None:
                return RedirectResponse("/login", status_code=303)
            name = str(form.get("account_name", "")).strip()[:120]
            platform = str(form.get("platform", "MT5"))
            cur = str(form.get("account_currency", "USD")).strip().upper()
            off = str(form.get("server_utc_offset_minutes", "")).strip()
            valid_off = off.lstrip("-").isdigit() and abs(int(off)) <= 14 * 60
            if not name or platform not in ("MT5", "MT4", "CSV") or len(cur) != 3 or (
                    off and not valid_off):
                sess["flash"] = "Invalid account details."
                return RedirectResponse("/accounts", status_code=303)
            _, token = create_account(
                db, user, account_name=name, platform=Platform(platform), account_currency=cur,
                server_utc_offset_mode=ServerOffsetMode.FIXED if off else ServerOffsetMode.AUTO,
                server_utc_offset_minutes=int(off) if off else None)
            db.commit()
        sess["new_token"] = token
        sess["flash"] = f"Account '{name}' created."
        return RedirectResponse("/accounts", status_code=303)

    @fh.route("/accounts/{account_id}/csv", methods=["post"])
    async def post_csv(account_id: int, req, sess):
        form = await req.form()
        with get_database().session() as db:
            user, account = _owned(db, sess, account_id)
            if account is None or account.platform == Platform.MOCK:
                return RedirectResponse("/accounts", status_code=303)
            upload = form.get("file")
            data = await upload.read(MAX_CSV + 1) if hasattr(upload, "read") else b""
            off = str(form.get("server_utc_offset_minutes", "")).strip()
            if len(data) > MAX_CSV or not data:
                sess["flash"] = "CSV missing or larger than 5 MB."
                return RedirectResponse("/accounts", status_code=303)
            try:
                batch = csv_to_batch(
                    data.decode("utf-8-sig", errors="replace"),
                    login_hash=account.login_hash if not account.login_hash.startswith("pending:")
                    else f"csv-{account.id:08d}", currency=account.account_currency,
                    server_utc_offset_minutes=int(off) if off.lstrip("-").isdigit() else None)
            except CsvImportError as exc:
                sess["flash"] = f"CSV rejected: {exc}"
                return RedirectResponse("/accounts", status_code=303)
            batch.account.platform = account.platform
            run = ingest_batch(db, account, batch)
            sess["flash"] = (f"Import {run.status}: {run.deals_inserted} new, "
                             f"{run.deals_duplicate} duplicate. {run.error_message or ''}")
        return RedirectResponse("/accounts", status_code=303)

    @fh.route("/accounts/{account_id}/rebuild", methods=["post"])
    def post_rebuild(account_id: int, sess):
        with get_database().session() as db:
            _, account = _owned(db, sess, account_id)
            if account is not None:
                n = rebuild_account(db, account)
                db.commit()
                sess["flash"] = f"Rebuilt {n} positions."
        return RedirectResponse("/accounts", status_code=303)

    @fh.route("/accounts/{account_id}/token", methods=["post"])
    def post_token(account_id: int, sess):
        with get_database().session() as db:
            _, account = _owned(db, sess, account_id)
            if account is not None:
                sess["new_token"] = issue_token(db, account)
                db.commit()
                sess["flash"] = "New collector token issued; previous tokens were revoked."
        return RedirectResponse("/accounts", status_code=303)

    @fh.route("/accounts/{account_id}/retry/{run_id}", methods=["post"])
    def post_retry(account_id: int, run_id: int, sess):
        with get_database().session() as db:
            _, account = _owned(db, sess, account_id)
            if account is not None:
                try:
                    run = retry_sync_run(db, account, run_id)
                    sess["flash"] = f"Retry {run.status}. {run.error_message or ''}"
                except (LookupError, RetryNotPossible) as exc:
                    sess["flash"] = f"Retry not possible: {exc}"
        return RedirectResponse("/accounts", status_code=303)
