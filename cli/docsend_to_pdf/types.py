from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Union


# Matches /view/{id} and /v/{id} (with optional slug after)
# Does NOT match /view/s/{id} (Spaces/folders — different resource type)
_URL_RE = re.compile(
    r"^(https?://(?:[\w-]+\.)?docsend(?:\.dropbox)?\.com)/(?:view|v)/([a-zA-Z0-9]+)"
)

# Matches DocSend Space URLs: /view/s/{id}
_SPACE_RE = re.compile(
    r"^https?://(?:[\w-]+\.)?docsend(?:\.dropbox)?\.com/view/s/"
)


@dataclass(frozen=True)
class DocSendURL:
    original: str
    normalized: str  # always in /view/{id} form
    doc_id: str


def parse_url(url: str) -> DocSendURL:
    """Validate and normalize a DocSend share URL.

    Accepts /view/{id} and /v/{id}/{slug} formats.
    Always normalizes to /view/{id}.
    Rejects Space/folder URLs (/view/s/{id}).
    """
    if _SPACE_RE.match(url):
        raise ValueError(
            "This is a DocSend Space (folder), not a document. "
            "Please provide the URL of a specific document within the Space."
        )
    m = _URL_RE.match(url)
    if not m:
        raise ValueError(f"Not a valid DocSend URL: {url}")
    base = m.group(1)
    doc_id = m.group(2)
    normalized = f"{base}/view/{doc_id}"
    return DocSendURL(original=url, normalized=normalized, doc_id=doc_id)


def is_short_url(url: str) -> bool:
    """Check if this is a /v/ short URL that needs redirect resolution."""
    return bool(re.match(
        r"^https?://(?:[\w-]+\.)?docsend(?:\.dropbox)?\.com/v/", url
    ))


class GateKind(Enum):
    NONE = auto()
    EMAIL = auto()
    PASSCODE = auto()
    NDA = auto()
    VERIFICATION = auto()
    REJECTED = auto()


@dataclass(frozen=True)
class Gate:
    kind: GateKind
    text: str = ""


@dataclass(frozen=True)
class PageResponse:
    gate: Gate
    csrf_token: str
    title: str | None = None
    page_count: int | None = None


@dataclass(frozen=True)
class PageData:
    image_url: str
    page_num: int


@dataclass(frozen=True)
class Authenticated:
    csrf_token: str
    page_count: int


@dataclass(frozen=True)
class NeedsInput:
    gate: Gate


GateResult = Union[Authenticated, NeedsInput]
