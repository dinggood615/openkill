#!/usr/bin/env python3
"""Normalize OpenWrt IPK archive ownership without changing package content."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import os
import sys
import tarfile
import tempfile


def normalized_inner(name: str, payload: bytes) -> bytes:
    mode = "w:gz" if name.endswith(".tar.gz") else "w:xz" if name.endswith(".tar.xz") else "w"
    output = BytesIO()
    with tarfile.open(fileobj=BytesIO(payload), mode="r:*") as source:
        with tarfile.open(fileobj=output, mode=mode, format=tarfile.GNU_FORMAT) as target:
            for member in source.getmembers():
                member.uid = 0
                member.gid = 0
                member.uname = "root"
                member.gname = "root"
                content = source.extractfile(member) if member.isfile() else None
                target.addfile(member, content)
                if content is not None:
                    content.close()
    return output.getvalue()


def normalize(path: Path) -> None:
    original = path.read_bytes()
    entries: dict[str, bytes] = {}
    with tarfile.open(fileobj=BytesIO(original), mode="r:*") as source:
        for member in source.getmembers():
            content = source.extractfile(member) if member.isfile() else None
            entries[member.name.lstrip("./")] = content.read() if content is not None else b""
            if content is not None:
                content.close()

    for name in ("control.tar.gz", "control.tar.xz", "data.tar.gz", "data.tar.xz"):
        if name in entries:
            entries[name] = normalized_inner(name, entries[name])

    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", format=tarfile.GNU_FORMAT) as target:
        for name in ("debian-binary", "control.tar.gz", "control.tar.xz", "data.tar.gz", "data.tar.xz"):
            if name not in entries:
                continue
            info = tarfile.TarInfo(name)
            info.size = len(entries[name])
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            target.addfile(info, BytesIO(entries[name]))

    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as temporary:
        temporary.write(output.getvalue())
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: normalize-ipk-ownership.py PACKAGE.ipk")
    normalize(Path(sys.argv[1]))
