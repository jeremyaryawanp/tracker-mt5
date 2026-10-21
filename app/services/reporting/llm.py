"""Optional LLM narrative for weekly reviews.

Privacy: only aggregated, anonymous metrics are sent (no account ids, logins, broker names,
ticket numbers or free-text notes). Disabled unless LLM_REVIEWS_ENABLED and LLM_API_KEY are set.
"""

import json

import httpx
from fastapi.encoders import jsonable_encoder

from app.config import Settings

SAFE_SUMMARY_KEYS = ("trade_count", "wins", "losses", "breakevens", "net_profit", "win_rate",
                     "profit_factor", "profit_factor_infinite", "expectancy", "avg_win",
                     "avg_loss", "max_drawdown", "max_consecutive_wins",
                     "max_consecutive_losses", "avg_r_multiple", "best_session",
                     "worst_session")


class LlmUnavailable(RuntimeError):
    pass


def privacy_safe_payload(data: dict) -> dict:
    out = {}
    for cur, d in data["by_currency"].items():
        disc = d["discipline"]
        out[cur] = {
            "this_week": {k: d["current"][k] for k in SAFE_SUMMARY_KEYS},
            "previous_week": {k: d["previous"][k] for k in SAFE_SUMMARY_KEYS},
            "symbols": [{"symbol": b["key"], "trades": b["trades"], "net": b["net_profit"]}
                        for b in d["by_symbol"]],
            "setups": [{"setup": b["key"], "trades": b["trades"], "net": b["net_profit"]}
                       for b in d["by_setup"]],
            "rule_adherence_pct": disc["adherence_pct"],
            "mistakes": [{"name": m["name"], "count": m["count"]} for m in disc["mistakes"]],
        }
    return jsonable_encoder(out)


def generate_summary(settings: Settings, data: dict,
                     transport: httpx.BaseTransport | None = None) -> str:
    if not (settings.llm_reviews_enabled and settings.llm_api_key):
        raise LlmUnavailable("LLM summaries are disabled")
    prompt = ("You are a trading coach. Using only these aggregated weekly metrics, write a "
              "concise review (max 150 words): what went well, what went wrong, and three "
              "concrete actions for next week. Do not invent numbers.\n\n"
              + json.dumps(privacy_safe_payload(data)))
    with httpx.Client(transport=transport, timeout=30) as client:
        r = client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                        json={"model": settings.llm_model, "temperature": 0.2,
                              "messages": [{"role": "user", "content": prompt}]})
    if r.status_code != 200:
        raise LlmUnavailable(f"LLM request failed ({r.status_code})")
    return r.json()["choices"][0]["message"]["content"].strip()
