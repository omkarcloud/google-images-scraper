"""Reference resolvers for /google-images/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a
sibling `url`/`id` pair):

    query   a search term OR a Google Images link (google.com/search?q=…
            with udm=2 / tbm=isch) — the link's q is the term
    image   a Google image id (the `tbnid`, 14 URL-safe chars, e.g.
            jUS0xT_ulT-SUM) OR a Google Images link that names one: the
            /imgres permalink every record carries as `google_link`
            (imgurl / imgrefurl / tbnid / docid), a results link with
            tbnid=, or a viewer (/async/imgv) link

Google's viewer call needs the image id AND the page id (`docid`, the
`page_id` of every record): an image id alone answers an empty body. The
/imgres permalink carries both, so a record's own `google_link` is the
round-trip form; a bare id works when its page id is known from an earlier
search in this process (api.py remembers them) and errors clearly otherwise.
"""
import re
from urllib.parse import parse_qs, urlencode, urlparse

from google_search.refs import is_google_link, params_of, resolve_query as _resolve_search_query

SITE = "https://www.google.com"

# tbnid / docid: Google's URL-safe base64 ids (14 chars seen since 2024;
# accept a little slack either way)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,24}$")


def resolve_query(value):
    """A search term or a Google Images link -> the term."""
    return _resolve_search_query(value)


def resolve_image(value):
    """Bare image id or a Google Images link naming one -> {"id", "page_id",
    "link", "page_link"} (the last three None when the input does not say)."""
    value = (value or "").strip()
    if not value:
        raise ValueError("image is required: a Google image id or a Google Images link")
    if _ID_RE.match(value):
        return {"id": value, "page_id": None, "link": None, "page_link": None}
    if is_google_link(value):
        params = params_of(value)
        tbnid = params.get("tbnid") or params.get("imgdii")
        if not tbnid or not _ID_RE.match(tbnid):
            raise ValueError("a Google Images link must carry tbnid= (the /imgres permalink or a results link with tbnid=)")
        docid = params.get("docid")
        return {
            "id": tbnid,
            "page_id": docid if docid and _ID_RE.match(docid) else None,
            "link": params.get("imgurl") or None,
            "page_link": params.get("imgrefurl") or None,
        }
    if value.lower().startswith(("http://", "https://", "//")):
        raise ValueError("image must be a Google image id or a google.com link with tbnid= (the /imgres permalink)")
    raise ValueError("image must be a Google image id (14 URL-safe characters, e.g. jUS0xT_ulT-SUM) "
                     "or the image's Google Images link")


def google_link(tbnid, docid=None, link=None, page_link=None):
    """The /imgres permalink of a record — Google's own viewer page for the
    image, and the round-trip form every endpoint accepts as `image`."""
    params = {}
    if link:
        params["imgurl"] = link
    if page_link:
        params["imgrefurl"] = page_link
    params["tbnid"] = tbnid
    if docid:
        params["docid"] = docid
    return f"{SITE}/imgres?{urlencode(params)}"


def images_link(query, country=None, language=None, tbs=None, start=None):
    """A results link for `query` on the Images tab."""
    params = {"q": query, "udm": 2}
    if language:
        params["hl"] = language
    if country:
        params["gl"] = country.lower()
    if tbs:
        params["tbs"] = tbs
    if start:
        params["start"] = start
    return f"{SITE}/search?{urlencode(params)}"


def images_link_tbs(token, country=None, language=None, start=None):
    """A related-images results link (tbs=rimg:<token>)."""
    params = {"udm": 2, "tbs": token}
    if language:
        params["hl"] = language
    if country:
        params["gl"] = country.lower()
    if start:
        params["start"] = start
    return f"{SITE}/search?{urlencode(params)}"


def link_params(value):
    """gl / hl / tbs / safe of a pasted Google Images link (empty for a term)."""
    if not is_google_link(value or ""):
        return {}
    params = params_of(value)
    return {k: params[k] for k in ("gl", "hl", "tbs", "safe") if params.get(k)}


def parse_qs_flat(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items() if v}
