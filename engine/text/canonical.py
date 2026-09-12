"""URL canonicalization — tier 0, pure, no network.

One URL that reaches one document should produce one key, so the corpus
never fetches or stores the same page twice. Everything here is
deterministic; redirect and shortener resolution needs the network and
lives in fetch, not here.
"""
from __future__ import annotations

from urllib.parse import (
    parse_qsl, quote, unquote, urlsplit, urlunsplit, urlencode,
)
import hashlib
import re

# Params that never change which document you land on. Prefixes end in '_'.
_TRACKING_EXACT = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "twclid", "igshid",
    "mc_cid", "mc_eid", "ref", "ref_src", "referrer", "source",
    "s_kwcid", "spm", "scm", "_ga", "_gl", "wbraid", "gbraid", "vero_id",
    "mkt_tok", "trk", "trkCampaign", "sc_channel", "sc_campaign",
}
_TRACKING_PREFIX = ("utm_", "pk_", "piwik_", "matomo_", "hsa_", "at_")

_DEFAULT_PORTS = {"http": "80", "https": "443"}
_MULTI_SLASH = re.compile(r"/{2,}")


def _strip_dot_segments(path: str) -> str:
    out: list[str] = []
    for seg in path.split("/"):
        if seg == ".":
            continue
        if seg == "..":
            if out and out[-1] != "":
                out.pop()
            continue
        out.append(seg)
    return "/".join(out)


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    # Re-encode: decode what is safely decodable, then quote consistently.
    path = quote(unquote(path), safe="/:@!$&'()*+,;=~-._")
    path = _MULTI_SLASH.sub("/", path)
    path = _strip_dot_segments(path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return path or "/"


def _keep_param(key: str) -> bool:
    k = key.lower()
    if k in _TRACKING_EXACT:
        return False
    return not k.startswith(_TRACKING_PREFIX)


def canonicalize(url: str, *, collapse_scheme: bool = True) -> str:
    """Return the canonical form of `url`.

    collapse_scheme folds http into https. Correct for dedup — the same
    host on both schemes serves the same document far more often than not
    — and wrong for fetching, so fetch the URL as given and key on this.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if "//" not in url.split("?", 1)[0][:10]:
        url = "//" + url  # bare host, let urlsplit find it
    parts = urlsplit(url, scheme="https")

    raw_scheme = (parts.scheme or "https").lower()
    scheme = "https" if (collapse_scheme and raw_scheme in ("http", "https")) \
        else raw_scheme

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        pass  # leave non-IDNA-encodable hosts as-is rather than lose them

    netloc = host
    port = parts.port
    # Compare against the port that was default for the scheme as given —
    # after collapsing http→https, :80 would otherwise look non-default.
    if port is not None and str(port) != _DEFAULT_PORTS.get(raw_scheme):
        netloc = f"{host}:{port}"

    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
               if _keep_param(k)),
        doseq=False,
    )
    return urlunsplit((scheme, netloc, _normalize_path(parts.path), query, ""))


def url_hash(url: str) -> str:
    """Stable 16-hex key for a canonical URL. Use as the corpus dedup key."""
    return hashlib.blake2b(canonicalize(url).encode("utf-8"),
                           digest_size=8).hexdigest()


def same_document(a: str, b: str) -> bool:
    return canonicalize(a) == canonicalize(b)
