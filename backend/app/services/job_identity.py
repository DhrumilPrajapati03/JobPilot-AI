"""Conservative cross-board identity; same title alone never merges openings."""
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def norm(value):
    return " ".join(re.sub(r"[^\w+#]+", " ", (value or "").lower()).split())


def canonical_url(value):
    try:
        url = urlsplit(value or "")
        if url.scheme not in {"http", "https"} or not url.hostname:
            return ""
        # Keep requisition-identifying query parameters. Remove tracking only.
        query = sorted((k, v) for k, v in parse_qsl(url.query) if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "src", "trackingid", "gh_src"})
        host = url.hostname.lower()
        if host.startswith("www."): host = host[4:]
        host = {"boards.greenhouse.io": "job-boards.greenhouse.io"}.get(host, host)
        path = re.sub(r"/+$", "", url.path)
        return urlunsplit(("https", host, path, urlencode(query), ""))
    except (ValueError, AttributeError):
        return ""


def identity_keys(posting: dict) -> list[str]:
    company, title = norm(posting.get("company")), norm(posting.get("title"))
    keys = []
    url = canonical_url(posting.get("url"))
    # Generic board/company homepages do not identify an opening.
    parts = urlsplit(url)
    opening_url = url and (len(parts.path.strip("/").split("/")) >= 2 or parts.query)
    if opening_url:
        keys.append(f"url:{company}:{url}")
        # Distinct first-party requisition URLs remain distinct even when an
        # employer reuses the same title and job description for both.
        if parts.hostname not in {"himalayas.app", "remotive.com", "remotive.io"}:
            return [hashlib.sha256(k.encode()).hexdigest() for k in keys]
    description = norm(posting.get("description"))
    if company and title and len(description) >= 80:
        keys.append(f"content:{company}:{title}:{norm(posting.get('location'))}:{description}")
    if not keys:
        keys.append(f"source:{posting.get('ats')}:{posting.get('external_id')}")
    return [hashlib.sha256(k.encode()).hexdigest() for k in keys]
