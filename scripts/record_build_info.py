"""Print and retain the resolved image runtime; refuse unpinned build inputs."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


def record(base_image, expected_package):
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", base_image):
        raise ValueError("base image must include its resolved SHA-256 digest")
    node = shutil.which("node")
    if node is None or Path(node).resolve() != Path("/usr/bin/node").resolve():
        raise ValueError("Node must be the installed Debian executable")
    package = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Version}", "nodejs"], text=True).strip()
    if package != expected_package:
        raise ValueError("installed Node package differs from the build pin")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("unexpected Node version output")
    return {"schema": "sentilab-build-info/1", "base_image": base_image,
            "base_image_digest": base_image.split("@", 1)[1],
            "node_version": version, "debian_nodejs_version": package}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--node-package-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = json.dumps(record(args.base_image, args.node_package_version), indent=2) + "\n"
    args.output.write_text(result, encoding="utf-8")
    print(result, end="")


if __name__ == "__main__":
    main()
