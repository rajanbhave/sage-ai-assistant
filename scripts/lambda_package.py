#!/usr/bin/env python3
"""Deterministic Lambda deployment packaging for the Sage Python functions.

Dependencies are installed for the target Lambda architecture rather than the
build machine, because ``cryptography`` ships native wheels and a macOS wheel
will not load on Lambda.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from collections.abc import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# uv's platform tag for AWS Lambda arm64 (Graviton).
ARM64_PLATFORM = "aarch64-manylinux2014"
_EXCLUDED = {"__pycache__", ".pytest_cache", ".mypy_cache"}


def _install_requirements(
    requirements: Sequence[str], target: Path, python_platform: str
) -> None:
    if not requirements:
        return
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(target),
            "--python-platform",
            python_platform,
            "--only-binary",
            ":all:",
            *requirements,
        ],
        check=True,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def _write_tree(archive: zipfile.ZipFile, root: Path, base: Path) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED for part in path.relative_to(base).parts):
            continue
        archive.write(path, path.relative_to(base).as_posix())


def build_zip(
    packages: Sequence[str],
    requirements: Sequence[str],
    *,
    python_platform: str = ARM64_PLATFORM,
) -> bytes:
    """Build a Lambda zip containing local packages and pinned dependencies.

    Args:
        packages: Project-relative package directories to include, such as
            ``sage_api``.
        requirements: Pinned requirement specifiers to install for the target.
        python_platform: uv platform tag matching the function architecture.

    Returns:
        The zip archive bytes.

    Raises:
        FileNotFoundError: If a named package directory does not exist.
        subprocess.CalledProcessError: If dependency installation fails.
    """
    for name in packages:
        if not (PROJECT_ROOT / name).is_dir():
            raise FileNotFoundError(f"package {name} does not exist")

    buffer = BytesIO()
    with tempfile.TemporaryDirectory() as raw_staging:
        staging = Path(raw_staging)
        _install_requirements(requirements, staging, python_platform)

        with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            _write_tree(archive, staging, staging)
            for name in packages:
                source = PROJECT_ROOT / name
                _write_tree(archive, source, PROJECT_ROOT)

    return buffer.getvalue()


def main() -> None:
    """Build the Sage API package locally to verify packaging without AWS."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if shutil.which("uv") is None:
        raise SystemExit("uv is required to build Lambda packages")

    payload = build_zip(
        ("sage_api", "sage_identity"), ("pyjwt[crypto]==2.13.0",)
    )
    if args.output is None:
        print(f"Built Sage API package: {len(payload):,} bytes")
        return
    args.output.write_bytes(payload)
    print(f"Wrote {args.output} ({len(payload):,} bytes)")


if __name__ == "__main__":
    main()
