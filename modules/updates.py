#!/usr/bin/env python3
"""System update checks and apply helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REBOOT_FLAG = Path("/var/run/reboot-required")
REBOOT_PKGS = Path("/var/run/reboot-required.pkgs")
_SUMMARY_RE = re.compile(
    r"^\d+ upgraded, \d+ newly installed, \d+ to remove and \d+ not upgraded\.?$"
)
# Real boot images only. Skips unsigned twins and metapackages such as
# linux-image-generic-hwe-* and linux-image-fb-generic-*.
_KERNEL_IMAGE = re.compile(r"^linux-image-(\d+\.\d+\.\d+-\d+)-generic$")


@dataclass
class UpdateReport:
    packages: list[str]
    flatpaks: list[str]
    reboot_required: bool
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.packages) + len(self.flatpaks)

    @property
    def lines(self) -> list[str]:
        out: list[str] = []
        out.extend(self.packages)
        out.extend(f"flatpak: {n}" for n in self.flatpaks)
        return out


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def refresh_apt_cache() -> str | None:
    if not shutil.which("pkexec"):
        return "pkexec not found"
    proc = _run(["pkexec", "apt-get", "update", "-qq"], timeout=300)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "apt-get update failed").strip()
        return err[:400]
    return None


def list_upgradable_apt() -> list[str]:
    proc = _run(["apt", "list", "--upgradable"], timeout=60)
    pkgs: list[str] = []
    for line in (proc.stdout or "").splitlines():
        if not line or line.startswith("Listing"):
            continue
        name = line.split("/", 1)[0].strip()
        if name:
            pkgs.append(name)
    return pkgs


def list_upgradable_flatpak() -> list[str]:
    if not shutil.which("flatpak"):
        return []
    proc = _run(
        ["flatpak", "remote-ls", "--updates", "--columns=application"],
        timeout=60,
    )
    if proc.returncode != 0:
        return []
    return [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]


def reboot_required() -> bool:
    return REBOOT_FLAG.exists()


def _installed(pattern: str) -> list[str]:
    proc = _run(["dpkg-query", "-W", "-f", "${Package}\n", pattern], timeout=20)
    return [
        ln.strip()
        for ln in (proc.stdout or "").splitlines()
        if ln.strip() and not ln.startswith("dpkg-query:")
    ]


def _kernel_abis() -> list[tuple[tuple[int, ...], str]]:
    found: list[tuple[tuple[int, ...], str]] = []
    for image in _installed("linux-image-*"):
        match = _KERNEL_IMAGE.match(image)
        if not match:
            continue
        abi = f"{match.group(1)}-generic"
        nums = tuple(int(part) for part in re.split(r"[.-]", match.group(1)))
        found.append((nums, abi))
    found.sort()
    return found


def kernels_missing_nvidia() -> list[str]:
    """Running kernel, and the newest installed one, if either has no NVIDIA module.

    Unattended kernel updates install a new linux-image on their own. The
    matching linux-modules-nvidia package is new, so a plain `apt upgrade`
    leaves it behind. The next reboot then has no display driver.
    Older leftover images are ignored. GRUB boots the newest one.
    """
    if not _installed("nvidia-driver-*"):
        return []
    modules = _installed("linux-modules-nvidia-*")
    found = _kernel_abis()
    if not found:
        return []
    check: list[str] = []
    running = os.uname().release
    newest = found[-1][1]
    for abi in (running, newest):
        if abi not in check:
            check.append(abi)
    missing: list[str] = []
    for abi in check:
        if not any(abi in name for name in modules):
            missing.append(abi)
    return missing


def gather(refresh: bool = False) -> UpdateReport:
    err = None
    if refresh:
        err = refresh_apt_cache()
    try:
        pkgs = list_upgradable_apt()
    except Exception as e:
        pkgs = []
        err = err or str(e)
    try:
        flats = list_upgradable_flatpak()
    except Exception:
        flats = []
    warnings = [
        f"Kernel {ver} has no NVIDIA module. Rebooting onto it drops the displays. Update now installs the module."
        for ver in kernels_missing_nvidia()
    ]
    return UpdateReport(
        packages=pkgs,
        flatpaks=flats,
        reboot_required=reboot_required(),
        error=err,
        warnings=warnings,
    )


def apt_apply_script() -> str:
    """Root script for Update now.

    `upgrade` refuses to install new packages. A new kernel's NVIDIA module
    is a new package (`linux-modules-nvidia-…-<kernel>`), so upgrade can
    boot a kernel with no matching driver and the displays go dead.
    `full-upgrade` installs those, and the phased-updates flag means an
    explicit click is not stuck behind Ubuntu's rollout delay.
    """
    lines = [
        "set -e",
        "export DEBIAN_FRONTEND=noninteractive",
        "export APT_LISTCHANGES_FRONTEND=none",
        "apt-get update -qq",
        "apt-get -y full-upgrade "
        "-o APT::Get::Always-Include-Phased-Updates=true "
        "-o Dpkg::Options::=--force-confdef "
        "-o Dpkg::Options::=--force-confold",
    ]
    if shutil.which("flatpak"):
        lines.append("flatpak update -y || true")
    return "\n".join(lines) + "\n"


def summarize_apt_output(output: str) -> str:
    """Turn apt's transcript into the bit a person needs to see."""
    lines = [ln.rstrip() for ln in output.splitlines()]
    summary = ""
    for ln in lines:
        if _SUMMARY_RE.match(ln.strip()):
            summary = ln.strip().rstrip(".")
    blocks: list[str] = []
    capture = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("The following ") and any(
            key in stripped
            for key in ("NEW packages", "will be upgraded", "will be REMOVED", "kept back", "deferred")
        ):
            capture = True
            blocks.append(stripped)
            continue
        if capture:
            if not stripped or _SUMMARY_RE.match(stripped) or stripped.startswith(
                ("Need to get ", "After this operation", "Reading ", "Building ")
            ):
                capture = False
                continue
            blocks.append(stripped)
    parts: list[str] = []
    if summary:
        upgraded = newly = 0
        m = re.match(
            r"(\d+) upgraded, (\d+) newly installed",
            summary,
        )
        if m:
            upgraded, newly = int(m.group(1)), int(m.group(2))
        if upgraded == 0 and newly == 0:
            parts.append("Already up to date.")
        else:
            parts.append(summary + ".")
    if blocks:
        shown = "\n".join(blocks)
        if len(shown) > 900:
            shown = shown[:900].rstrip() + "…"
        parts.append(shown)
    reboot = _reboot_note()
    if reboot:
        parts.append(reboot)
    if not parts:
        tail = "\n".join(ln.strip() for ln in lines if ln.strip())[-600:]
        return tail or "Updates finished."
    return "\n\n".join(parts)


def _reboot_note() -> str:
    if not reboot_required():
        return ""
    detail = ""
    try:
        names = [ln.strip() for ln in REBOOT_PKGS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        names = []
    if names:
        detail = " (" + ", ".join(names[:6]) + ")"
    return f"A reboot is needed for this to take effect{detail}. None was forced."


def apply_updates() -> tuple[bool, str]:
    if not shutil.which("pkexec"):
        return False, "pkexec not found"

    proc = _run(["pkexec", "bash", "-c", apt_apply_script()], timeout=3600)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        tail = out[-800:] or "Update failed"
        return False, tail
    return True, summarize_apt_output(out)
