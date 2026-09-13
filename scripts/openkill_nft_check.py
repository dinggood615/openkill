#!/usr/bin/env python3
"""Opt-in offline ``nft -c`` wrapper used by Phase 3B tests.

This module is intentionally separate from the renderer.  It writes only a
temporary file and invokes exactly ``nft -c -f <temporary-file>``; it never
uses ``nft -f`` or any mutating nft command.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from openkill_nft_syntax import validate_nft_syntax_text


class NftCheckUnavailable(RuntimeError):
    """The local host has no nft executable."""


def find_nft(path: Optional[str] = None) -> Optional[str]:
    if path:
        return path if Path(path).exists() else None
    return shutil.which("nft")


def run_nft_check(text: str, *, nft_path: Optional[str] = None) -> Dict[str, Any]:
    """Run the parser-only check and return stdout/stderr/return code.

    No shell is used and the argument vector is deliberately fixed.  A caller
    can inspect ``argv`` to assert that no mutation mode was attempted.
    """

    validate_nft_syntax_text(text, production_output=False)
    executable = find_nft(nft_path)
    if not executable:
        raise NftCheckUnavailable("nft executable is not available")
    with tempfile.TemporaryDirectory(prefix="openkill-nft-check-") as directory:
        source = Path(directory) / "candidate.nft"
        source.write_text(text, encoding="utf-8", newline="\n")
        argv = [executable, "-c", "-f", str(source)]
        completed = subprocess.run(argv, check=False, capture_output=True, text=True)
        return {
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "temporary_directory": directory,
        }


__all__ = ["NftCheckUnavailable", "find_nft", "run_nft_check"]
