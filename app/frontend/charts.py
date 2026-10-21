import json
import secrets
from decimal import Decimal

from fasthtml.common import Div, NotStr, Script

LAYOUT = {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
          "font": {"color": "#cbd5e1"}, "margin": {"l": 50, "r": 10, "t": 30, "b": 40},
          "xaxis": {"gridcolor": "#1e293b"}, "yaxis": {"gridcolor": "#1e293b"}, "height": 300}


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def plot(traces: list[dict], title: str, layout: dict | None = None):
    cid = f"chart-{secrets.token_hex(4)}"
    lay = {**LAYOUT, "title": {"text": title, "font": {"size": 14}}, **(layout or {})}
    payload = json.dumps({"t": traces, "l": lay}, default=_default)
    js = (f"(function(){{var d={payload};function draw(){{if(window.Plotly)"
          f"{{Plotly.newPlot('{cid}',d.t,d.l,{{displayModeBar:false,responsive:true}})}}"
          f"else setTimeout(draw,100)}};draw();}})();")
    return Div(Div(id=cid), Script(NotStr(js)))
