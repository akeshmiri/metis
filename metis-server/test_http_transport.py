"""
Phase 9 test: OAuth2Middleware exempts /healthz -- a real bug caught before
shipping (verified with Starlette's TestClient that registering a route
before add_middleware() does NOT exempt it from a BaseHTTPMiddleware; the
middleware itself must exempt the path).
"""
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from metis_mcp.http_transport import OAuth2Middleware


class _FakeDriver:
    def session(self, database="neo4j"):
        raise AssertionError("must not be called for an exempt path")


def _make_app():
    async def healthz(request):
        return PlainTextResponse("ok")

    async def protected(request):
        return PlainTextResponse("secret")

    app = Starlette()
    app.add_route("/healthz", healthz, methods=["GET"])
    app.add_route("/mcp", protected, methods=["GET"])
    app.add_middleware(OAuth2Middleware, driver=_FakeDriver(), secret="test-secret")
    return app


def test_healthz_bypasses_auth_entirely():
    client = TestClient(_make_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"


def test_other_paths_still_require_a_bearer_token():
    client = TestClient(_make_app())
    r = client.get("/mcp")
    assert r.status_code == 401


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
