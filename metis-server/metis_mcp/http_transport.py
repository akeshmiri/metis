"""
Phase 6: OAuth2 enforcement middleware for the Streamable HTTP transport
(§11.2, REQ-METIS-CPT-03). Every request's Bearer token is re-validated
against Neo4j (metis_mcp/oauth2.py's validate_access_token) -- not decoded
and trusted, not cached from a prior request -- matching CONST-064's
"re-validated every request" requirement at the actual transport boundary,
not just in a unit-testable function nobody calls.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from metis_mcp.oauth2 import validate_access_token


class OAuth2Middleware(BaseHTTPMiddleware):
    # Paths that bypass auth entirely -- health checks (kubelet's
    # livenessProbe has no way to present a Bearer token) must not be
    # gated, or a healthy MCP server gets reported unhealthy and killed.
    # A real bug caught before this ever ran, not after: registering the
    # /healthz route BEFORE add_middleware() doesn't exempt it -- Starlette
    # middleware wraps the whole ASGI call chain ahead of routing,
    # regardless of route registration order. Verified directly with a
    # TestClient probe, not assumed.
    EXEMPT_PATHS = {"/healthz"}

    def __init__(self, app, driver, secret: str, database: str = "neo4j"):
        super().__init__(app)
        self._driver = driver
        self._secret = secret
        self._database = database

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "Missing Bearer token."}, status_code=401)
        token = auth[len("Bearer "):]

        with self._driver.session(database=self._database) as session:
            result = validate_access_token(session, self._secret, token)

        if not result.valid:
            return JSONResponse({"error": result.reason}, status_code=401)

        request.state.token = result
        return await call_next(request)
