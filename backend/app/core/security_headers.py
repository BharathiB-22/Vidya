from starlette.types import ASGIApp, Receive, Scope, Send

# Headers injected into every HTTP response from the API.
# HSTS and CSP are NOT set here:
#   - HSTS is set by the Ingress nginx (ssl-redirect forces HTTPS first).
#   - CSP is only meaningful on HTML responses; the API is JSON-only.
# Cross-Origin-Opener-Policy and Permissions-Policy are set by the frontend
# nginx.conf since they apply to browser page contexts, not API JSON responses.
_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-xss-protection", b"0"),
    (b"cross-origin-resource-policy", b"same-origin"),
]


class SecurityHeadersMiddleware:
    """Pure ASGI middleware that appends security headers to every response.

    Uses raw ASGI (not BaseHTTPMiddleware) to avoid double request-body
    buffering, which causes issues with large file uploads.
    Only adds a header if it is not already present in the response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                existing = {h[0].lower() for h in message.get("headers", [])}
                extra = [(k, v) for k, v in _SECURITY_HEADERS if k not in existing]
                message = {
                    **message,
                    "headers": list(message.get("headers", [])) + extra,
                }
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
