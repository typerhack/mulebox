"""Names used by runner management: GitHub repositories, runner names, labels, units.

Shared by the node side (manage.py) and the dev machine side (github.py), so both
refuse the same input before anything runs.
"""

from __future__ import annotations

import re

from mulebox.common.config_reader import NAME_RE
from mulebox.common.errors import MuleboxError

UNIT_PREFIX = "mulebox-runner@"
MAX_NAME = 64
DEFAULT_LABELS = ("mulebox",)
# GitHub owners: letters, digits and single hyphens, not starting with one; repositories:
# letters, digits, '.', '_' and '-'.
_OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
_REPO_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")
_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class RunnerUsageError(MuleboxError):
    """A repository, runner name or label is not acceptable."""


def check_repo(repo: str) -> str:
    """Return repo if it is `owner/name`; RunnerUsageError otherwise."""
    if not isinstance(repo, str) or repo.count("/") != 1:
        raise RunnerUsageError(f"repository must look like owner/name, got {repo!r}")
    owner, name = repo.split("/")
    if not _OWNER_RE.fullmatch(owner) or not _REPO_RE.fullmatch(name) or name in (".", ".."):
        raise RunnerUsageError(f"repository must look like owner/name, got {repo!r}")
    return repo


def check_name(name: str) -> str:
    """A runner name: also a folder name and a systemd instance name."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > MAX_NAME:
        raise RunnerUsageError(
            f"runner name {name!r} may only contain letters, digits, '.', '_' and '-', "
            f"start with a letter or digit, and be at most {MAX_NAME} characters")
    return name


def default_name(node: str, repo: str) -> str:
    """`<node>-<repo name>`, cut to the name limit."""
    name = f"{node}-{check_repo(repo).split('/')[1]}"[:MAX_NAME].rstrip(".-_")
    return check_name(name)


def parse_labels(text: str | None) -> tuple[str, ...]:
    """`a,b` -> ("a", "b"); None -> the default labels."""
    if text is None:
        return DEFAULT_LABELS
    labels = tuple(part.strip() for part in text.split(","))
    for label in labels:
        if not _LABEL_RE.fullmatch(label):
            raise RunnerUsageError(
                f"label {label!r} may only contain letters, digits, '.', '_' and '-'")
    return labels


def unit_name(name: str) -> str:
    return f"{UNIT_PREFIX}{check_name(name)}.service"


def repo_url(repo: str) -> str:
    return f"https://github.com/{check_repo(repo)}"
