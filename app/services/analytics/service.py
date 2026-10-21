"""Load filtered positions for a user and compute metrics per account currency."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import SymbolSpec, TradeDeal, TradePosition, TradingAccount, User
from app.models.enums import DealType, PositionStatus, TagKind
from app.services.analytics import metrics
from app.services.analytics.types import AnalyticsFilter, CashFlow, PositionRow


def _utc_bounds(f: AnalyticsFilter, tz: ZoneInfo) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(f.date_from, time.min, tzinfo=tz) if f.date_from else None
    end = (datetime.combine(f.date_to + timedelta(days=1), time.min, tzinfo=tz)
           if f.date_to else None)
    return start, end


class Analytics:
    def __init__(self, session: Session, user: User):
        self.session = session
        self.user = user
        self.tz = ZoneInfo(user.display_timezone)
        self.week_start = user.week_start

    def accounts(self, f: AnalyticsFilter) -> list[TradingAccount]:
        q = select(TradingAccount).where(TradingAccount.user_id == self.user.id)
        if f.account_ids:
            q = q.where(TradingAccount.id.in_(f.account_ids))
        return list(self.session.scalars(q.order_by(TradingAccount.id)))

    def rows(self, f: AnalyticsFilter) -> list[PositionRow]:
        accounts = {a.id: a for a in self.accounts(f)}
        if not accounts:
            return []
        start, end = _utc_bounds(f, self.tz)
        q = (select(TradePosition)
             .options(selectinload(TradePosition.annotation))
             .where(TradePosition.account_id.in_(accounts),
                    TradePosition.status == PositionStatus.CLOSED))
        if start:
            q = q.where(TradePosition.close_time >= start)
        if end:
            q = q.where(TradePosition.close_time < end)
        if f.symbols:
            q = q.where(TradePosition.symbol.in_(f.symbols))
        if f.directions:
            q = q.where(TradePosition.direction.in_(f.directions))
        specs = {(s.account_id, s.symbol): s for s in self.session.scalars(
            select(SymbolSpec).where(SymbolSpec.account_id.in_(accounts)))}
        out = []
        for p in self.session.scalars(q.order_by(TradePosition.close_time, TradePosition.id)):
            row = _row(p, specs.get((p.account_id, p.symbol)), accounts[p.account_id])
            if _matches(row, f):
                out.append(row)
        return out

    def cash_flows(self, f: AnalyticsFilter) -> list[CashFlow]:
        accounts = self.accounts(f)
        q = select(TradeDeal).where(
            TradeDeal.account_id.in_([a.id for a in accounts]),
            TradeDeal.deal_type.in_([DealType.BALANCE, DealType.CREDIT]))
        currency = {a.id: a.account_currency for a in accounts}
        return [CashFlow(d.time_utc, d.profit, currency[d.account_id])
                for d in self.session.scalars(q.order_by(TradeDeal.time_utc))]

    def by_currency(self, rows: list[PositionRow]) -> dict[str, list[PositionRow]]:
        groups: dict[str, list[PositionRow]] = defaultdict(list)
        for r in rows:
            groups[r.currency].append(r)
        return dict(groups)

    def summary(self, f: AnalyticsFilter) -> dict[str, dict]:
        rows = self.rows(f)
        flows = self.cash_flows(f)
        out = {}
        for currency, items in self.by_currency(rows).items():
            start_balance = self._starting_balance(f, currency, flows, items)
            out[currency] = metrics.summary(items, self.tz, self.week_start, start_balance)
        return out

    def equity(self, f: AnalyticsFilter) -> dict[str, list[dict]]:
        rows = self.rows(f)
        flows = self.cash_flows(f)
        out = {}
        for currency, items in self.by_currency(rows).items():
            first = items[0].close_time if items else None
            prior = sum((c.amount for c in flows if c.currency == currency and first
                         and c.time <= first), Decimal("0"))
            later = [c for c in flows if c.currency == currency and first and c.time > first]
            has_balance = any(c.currency == currency for c in flows)
            out[currency] = metrics.equity_curve(items, later,
                                                 prior if has_balance else None)
        return out

    def _starting_balance(self, f, currency, flows, items) -> Decimal | None:
        relevant = [c for c in flows if c.currency == currency]
        if not relevant or not items:
            return None
        first = items[0].close_time
        total = sum((c.amount for c in relevant if c.time <= first), Decimal("0"))
        prior = sum((r.net for r in self.rows(AnalyticsFilter(account_ids=f.account_ids))
                     if r.currency == currency and r.close_time < first), Decimal("0"))
        value = total + prior
        return value if value > 0 else None


def _row(p: TradePosition, spec: SymbolSpec | None, account: TradingAccount) -> PositionRow:
    a = p.annotation
    tags = tuple(t.name for t in a.tags if t.kind != TagKind.MISTAKE) if a else ()
    mistakes = tuple(t.name for t in a.tags if t.kind == TagKind.MISTAKE) if a else ()
    return PositionRow(
        id=p.id, account_id=p.account_id, external_position_id=p.external_position_id,
        symbol=p.symbol, direction=str(p.direction), volume=p.volume_lots,
        open_time=p.open_time, close_time=p.close_time, open_price=p.open_price,
        close_price=p.close_price, gross=p.realized_gross_profit, commission=p.commission,
        swap=p.swap, fees=p.fees, net=p.realized_net_profit, currency=p.account_currency,
        sl=p.initial_sl_price, tp=p.initial_tp_price, sl_tp_source=str(p.sl_tp_source),
        exit_count=p.exit_count,
        session=(a.trading_session_override if a and a.trading_session_override
                 else p.trading_session or "OFF_SESSION"),
        pip_size=spec.pip_size if spec else None,
        pip_label=spec.pip_unit_label if spec else None,
        tick_size=spec.tick_size if spec else None,
        tick_value=spec.tick_value if spec else None,
        contract_size=spec.contract_size if spec else None,
        profit_currency=spec.profit_currency if spec else None,
        setup=a.setup_name if a else None,
        rule_followed=a.rule_followed if a else None,
        emotional_state=a.emotional_state if a else None,
        tags=tags, mistakes=mistakes, is_simulated=account.is_simulated,
    )


def _matches(r: PositionRow, f: AnalyticsFilter) -> bool:
    if f.sessions and r.session not in f.sessions:
        return False
    if f.setups and (r.setup or "Unspecified") not in f.setups:
        return False
    if f.tags and not set(f.tags) & (set(r.tags) | set(r.mistakes)):
        return False
    return not (f.outcome and metrics.outcome(r) != f.outcome)
