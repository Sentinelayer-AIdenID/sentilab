"""Run exact v0.6 vectors against HTTP: python -m app.check_view_paging [contract-dir]."""
from pathlib import Path
import subprocess
import sys
from unittest import mock

from fastapi import HTTPException

from app.test_view import ViewTests
from app import view
from app.main import app


def main():
    root = Path(__file__).resolve().parent.parent
    reference = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "contracts/view-envelope-v0.6"
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/view/events")
    endpoint = route.dependant.call
    replay = view.replay
    comparisons = 0

    def call(query):
        try:
            response = endpoint(**query)
            return response, (response.status_code, response.raw_headers, response.body)
        except HTTPException as error:
            return error, (error.status_code, error.headers, error.detail)

    def compare(**query):
        nonlocal comparisons
        response, first = call(query)
        _, warm = call(query)
        with mock.patch.object(view, "replay", side_effect=lambda *a, **kw: replay(*a, **{**kw, "cache": None})):
            _, cold = call(query)
        assert first == warm == cold, "cached and uncached route responses differ"
        comparisons += 1
        if isinstance(response, HTTPException):
            raise response
        return response

    route.dependant.call = compare
    fixture = ViewTests()
    try:
        fixture.setUp()
        try:
            subprocess.run(["node", str(Path(__file__).with_suffix(".mjs")), str(reference.resolve()),
                            f"http://127.0.0.1:{fixture.port}", str(fixture.root)], check=True, timeout=120)
            print(f"PASS cached/uncached byte-identical responses: {comparisons}", flush=True)
        finally:
            fixture.tearDown()
    finally:
        route.dependant.call = endpoint


if __name__ == "__main__":
    main()
