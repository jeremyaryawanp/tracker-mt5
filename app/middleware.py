"""Security headers and cross-site request protection for cookie-authenticated requests."""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSP = ("default-src 'self'; "
       "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com "
       "https://cdn.plot.ly https://cdn.jsdelivr.net https://unpkg.com; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class SecurityMiddleware(BaseHTTPMiddleware):
    """Rejects cross-site state-changing requests (Origin / Sec-Fetch-Site checks).

    Collector ingest uses bearer tokens (no cookies), so it is exempt.
    """

    async def dispatch(self, request: Request, call_next):
        if (request.method in UNSAFE and not request.url.path.startswith("/api/v1/ingest")
                and _cross_site(request)):
            msg = "Cross-site request blocked"
            return (JSONResponse({"detail": msg}, status_code=403)
                    if request.url.path.startswith("/api/") else
                    PlainTextResponse(msg, status_code=403))
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Content-Security-Policy", CSP)
        if request.url.scheme == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response


def _cross_site(request: Request) -> bool:
    if request.headers.get("sec-fetch-site") == "cross-site":
        return True
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin or origin == "null":
        return origin == "null"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlsplit(origin).netloc != host
