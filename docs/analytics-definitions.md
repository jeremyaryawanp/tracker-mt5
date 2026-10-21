# Analytics Definitions (draft — implemented and tested in TASK-005)

All metrics are computed by `app/services/analytics` from **closed positions** (position level) unless
deal-level mode is explicitly selected. Amounts are in the account currency; multi-account views
with different currencies show per-currency results and never sum across currencies.

Notation: `n` = eligible closed positions in the filter; `net_i` = realized net P/L of position i
= gross profit + commission + swap + fees (each signed as reported, counted once).

| Metric | Definition | Edge cases |
| --- | --- | --- |
| Net Profit | Σ net_i | 0 when n = 0 (shown as empty state) |
| Gross Profit | Σ net_i for net_i > 0 | |
| Gross Loss | \|Σ net_i for net_i < 0\| (positive magnitude) | |
| Win / Loss / Breakeven | net_i > 0 / < 0 / = 0 after rounding to currency precision | |
| Win Rate | wins / n × 100 (breakevens stay in n) | undefined when n = 0 |
| Average Win | Gross Profit / wins | "—" when wins = 0 |
| Average Loss | Gross Loss / losses (positive magnitude) | "—" when losses = 0 |
| Profit Factor | Gross Profit / Gross Loss | Gross Loss = 0 and Gross Profit > 0 → "∞"; both 0 → "—" |
| Expectancy | Net Profit / n | also shown: WR × AvgWin − LR × AvgLoss (equal by construction) |
| Largest Win / Loss | max / min net_i | |
| Max Drawdown | max over t of (peak cumulative net − cumulative net), absolute and % of peak equity when balance known | realized-only; ordered by close_time |
| Avg Holding Duration | mean(close_time − open_time) | |
| Best / Worst Day | day (display TZ, by close_time) with max / min Σ net | |
| Best / Worst Session | session with max / min Σ net | |
| Max Consecutive Wins / Losses | longest streak by close_time; breakeven breaks both streaks | |
| Avg Risk:Reward (planned) | mean(\|TP − entry\| / \|entry − SL\|) over positions with valid initial SL and TP | "Data unavailable" if none |
| Avg R-multiple | mean(net_i / initial_risk_i), initial_risk = \|entry − SL\| × volume × value per price unit | only positions with initial SL; excluded otherwise, count shown |
| Planned TP distance (pips) | BUY: (TP − entry)/pip; SELL: (entry − TP)/pip | only with valid initial TP |
| Planned SL distance (pips) | BUY: (entry − SL)/pip; SELL: (SL − entry)/pip | only with valid initial SL |
| Actual win/loss exit distance (pips) | BUY: (exit − entry)/pip; SELL: (entry − exit)/pip; averaged for wins and losses separately | never labelled as planned TP/SL |
| Daily / Weekly consistency | % of trading days (weeks) with net > 0; plus std-dev of daily net | |

## Rules

- **Attribution date**: a position belongs to the day/week of its `close_time` in the display
  timezone. A trade opened 23:30 and closed 00:30 Jakarta time counts on the second day.
- **Partial closes**: all exit deals of one position aggregate into one result; win rate counts the
  position once. Deal-level view lists each exit separately.
- **Costs**: commission charged on entry deals is included in the position's net. Values already
  embedded in `profit` by a broker (rare; flagged per account) are not deducted again.
- **Pip size**: from `symbol_spec.pip_size`; FX with 3/5 digits → 10 × point, 2/4 digits → point;
  metals, indices, CFDs, crypto require a configured value (defaults shown with "derived" label).
  The unit definition is displayed next to every pip metric.
- **Missing SL/TP**: shown as "Data unavailable", never imputed. MT4 last-known SL/TP is not used
  as initial risk.
- **Equity curve**: "Realized P/L curve" = cumulative Σ net by close_time. "Balance" series only
  when balance deals/initial balance are available. Labels distinguish the two; no estimates.
- **Sessions** (default, configurable): Asia 00:00–09:00 Asia/Tokyo, London 08:00–17:00
  Europe/London, New York 08:00–17:00 America/New_York; assigned by open time; overlaps assigned
  to the later-opening session (e.g. London/NY overlap → New York); outside all → "Off-session".
  A manual annotation override takes precedence.
