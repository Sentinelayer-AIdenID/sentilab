"""Run exact v0.6 vectors against HTTP: python -m app.check_view_paging [contract-dir]."""
from pathlib import Path
import subprocess
import sys

from app.test_view import ViewTests


def main():
    root = Path(__file__).resolve().parent.parent
    reference = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "contracts/view-envelope-v0.6"
    fixture = ViewTests()
    fixture.setUp()
    try:
        subprocess.run(["node", str(Path(__file__).with_suffix(".mjs")), str(reference.resolve()),
                        f"http://127.0.0.1:{fixture.port}", str(fixture.root)], check=True, timeout=120)
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
