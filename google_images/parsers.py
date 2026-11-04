"""Raw Google Images pages / fragments -> clean dicts. Pure functions, no I/O.

Where the data lives (every fixture captured 2026-11-03, google_images/fixtures/):

  * RESULTS PAGE  /search?udm=2 — 100 tiles. The DOM carries the order
    (`[data-attrid="images universal"][data-docid]`, data-docid = the
    image id `tbnid`, data-ref-docid = the page id `docid`, data-lpage = the
    page link) plus the filter chips (a.nPDzT) and related searches
    (a.bqW4cb); everything else about a tile is in the page's own data map
    (`var m={…}` near the end of the page), one JSON entry per tile:

        [0, tbnid, [thumb, h, w], [original, h, w], null, kind, "rgb(…)",
         null, 0, {"2000": [null, domain, "190KB"],
                   "2001": [layout crop hints],
                   "2003": [null, docid, page_link, title, null, 0, null,
                            favicon, null, 0, null, null, site_name,
                            null ×4, domain, [credit_line, [creators], null,
                            copyright], …, about_this_image_link, null, 1],
                   "2006": [null, product, …, video(8), …, licence(11)]}]

    Dimensions come as [height, width] (the tile's own aspect-ratio style
    confirms it). `kind` 0 plain / 2 product / 3 video / 7 licensable.
    product = [rating, null, title, seller, description, null, 1,
               original_price, price, currency, …, product_id, null, ?,
               null, null, shopping_path]
    video   = [title, description, "0:45", views, published_ms, null,
               channel, null, ?, 0, seconds]
    licence = [details_link, terms_link, ?, provider, 0, [creators], credit,
               copyright]

  * PAGING FRAGMENT  the same tiles for start=10 / 20 (asearch=arc), an
    XSSI-prefixed chunk stream whose data map is a list of
    ["<key>", "<entry as an escaped JSON string>"] pairs. start=30 and past
    answer a 1 KB fragment with no tiles (Google's 300-image ceiling).

  * VIEWER  /async/imgv?tbnid&imgdii&docid — the side panel: 12 related
    tiles (pairs form again), the "Licensable" badge of the opened image,
    and the `rimg:` token of the visually related search ("See more
    related content"). The opened image's own entry is NOT in it (the
    page that opened the viewer already holds it) unless the image happens
    to be among its own related tiles. An unknown id, or no docid, answers
    a header-only fragment (263 B / 3 KB).

  * PERMALINK PAGE  /imgres?imgurl&imgrefurl&tbnid&docid ("Google Image
    Result", captured 2026-11-04) — the image's OWN entry plus the same 12
    related tiles, the rimg: token and the badge, so parse_viewer reads it
    too. Its entry is leaner than the search tile's (no credits, no
    dominant colour); api.py fills those from a remembered search record.
    An unknown id answers the same title with no entries.

  * RELATED PAGE  /search?udm=2&tbs=rimg:<token> — a results page again
    (no chips, no related searches, "About 0 results"); its scroll
    fragments need the original `q` (empty 1.5 KB without it).

  * SUGGESTIONS  /complete/search?client=img&ds=i — JSONP
    window.google.ac.h(["q", [["golden retr<b>iever</b>", 0, [subtypes]], …]]).
"""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from google_images.refs import SITE, google_link
from google_search.serp_parsers import absolute, first, page_query, parse_document, query_of, result_stats, text
from google_search.shared import clean_text

TILE_CSS = '[data-attrid="images universal"][data-docid]'
KINDS = {0: "image", 2: "product", 3: "video", 7: "licensable"}

_VAR_M_RE = re.compile(r"var m=(\{)")
_PAIR_RE = re.compile(r'\["([A-Za-z0-9_-]+)","(\[(?:[^"\\]|\\.)*)"\]')
_RIMG_RE = re.compile(r"rimg:[A-Za-z0-9_-]+")
_JSONP_RE = re.compile(r"^\s*window\.google\.ac\.h\((.*)\)\s*;?\s*$", re.S)
_FORMAT_RE = re.compile(r"\.(jpe?g|png|gif|webp|svg|bmp|avif|ico|tiff?)(?:$|[?#])", re.I)


# ---- the tile data map -------------------------------------------------------------------------------

def _decode_entries(values):
    """Tile entries out of a data map's values: `[0, tbnid, …]` or
    `[1, [0, tbnid, …]]` (the richer wrapped form wins per tbnid)."""
    out = {}
    for v in values:
        if not isinstance(v, list) or not v:
            continue
        e = None
        if v[0] == 0 and len(v) > 1 and isinstance(v[1], str):
            e = v
        elif v[0] == 1 and len(v) > 1 and isinstance(v[1], list) and v[1] and v[1][0] == 0 \
                and len(v[1]) > 1 and isinstance(v[1][1], str):
            e = v[1]
        if e is None or len(e) < 4:
            continue
        tbnid = e[1]
        rich = len(e) > 9 and isinstance(e[9], dict)
        if tbnid not in out or (rich and not (len(out[tbnid]) > 9 and isinstance(out[tbnid][9], dict))):
            out[tbnid] = e
    return out


def tile_entries(raw):
    """{tbnid: entry} from a results page (var m maps) or a fragment (the
    ["key", "escaped json"] pairs). Tolerant: a map that fails to decode is
    skipped, never raised."""
    raw = raw or ""
    values = []
    decoder = json.JSONDecoder()
    for m in _VAR_M_RE.finditer(raw):
        try:
            obj, _ = decoder.raw_decode(raw, m.start(1))
        except ValueError:
            continue
        if isinstance(obj, dict):
            values.extend(obj.values())
    for _key, escaped in _PAIR_RE.findall(raw):
        try:
            values.append(json.loads(json.loads('"' + escaped + '"')))
        except ValueError:
            continue
    return _decode_entries(values)


def _at(seq, i, default=None):
    return seq[i] if isinstance(seq, list) and len(seq) > i and seq[i] not in ("",) else default


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _str(v):
    return v if isinstance(v, str) and v.strip() else None


def _date(ms):
    ms = _num(ms)
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def _format(link):
    m = _FORMAT_RE.search(urlparse(link or "").path + "?" + urlparse(link or "").query)
    if not m:
        return None
    ext = m.group(1).lower()
    return {"jpeg": "jpg", "tif": "tiff"}.get(ext, ext)


def _credits(block):
    """2003[18]: [credit_line, [creators], null, copyright]."""
    if not isinstance(block, list):
        return None
    creators = [c for c in (_at(block, 1) or []) if isinstance(c, str) and c.strip()] if isinstance(_at(block, 1), list) else []
    out = {"credit_line": _str(_at(block, 0)), "creators": creators, "copyright": _str(_at(block, 3))}
    return out if any((out["credit_line"], creators, out["copyright"])) else None


def _licence(block):
    """2006[11]: [details_link, terms_link, ?, provider, 0, [creators], credit, copyright]."""
    if not isinstance(block, list):
        return None
    creators = [c for c in (_at(block, 5) or []) if isinstance(c, str) and c.strip()] if isinstance(_at(block, 5), list) else []
    out = {
        "provider": _str(_at(block, 3)),
        "details_link": _str(_at(block, 0)),
        "terms_link": _str(_at(block, 1)),
        "creators": creators,
        "credit": _str(_at(block, 6)),
        "copyright": _str(_at(block, 7)),
    }
    return out if any(out.values()) else None


def _product(block, query=None):
    """2006[1]: the Shopping offer behind a product tile."""
    if not isinstance(block, list) or not _str(_at(block, 2)):
        return None
    price, currency = _num(_at(block, 8)), _str(_at(block, 9))
    original = _num(_at(block, 7))
    path = _str(_at(block, 18))
    return {
        "id": _str(_at(block, 13)),
        "title": clean_text(_at(block, 2)),
        "seller": clean_text(_at(block, 3)),
        "description": clean_text(_at(block, 4)),
        "price": {"amount": price, "currency": currency} if price is not None else None,
        "original_price": {"amount": original, "currency": currency} if original is not None and original != price else None,
        "rating": _num(_at(block, 0)),
        "shopping_link": absolute(path) if path else None,
    }


def _video(block):
    """2006[8]: the video behind a video tile."""
    if not isinstance(block, list) or not _str(_at(block, 0)):
        return None
    return {
        "title": clean_text(_at(block, 0)),
        "description": clean_text(_at(block, 1)),
        "duration": _str(_at(block, 2)),
        "duration_seconds": _int(_at(block, 10)),
        "views": _int(_at(block, 3)),
        "channel": clean_text(_at(block, 6)),
        "published_date": _date(_at(block, 4)),
    }


def parse_tile(entry, position=None):
    """One data-map entry -> the public image record."""
    tbnid = _str(_at(entry, 1))
    thumb = _at(entry, 2) if isinstance(_at(entry, 2), list) else []
    orig = _at(entry, 3) if isinstance(_at(entry, 3), list) else []
    meta = _at(entry, 9) if isinstance(_at(entry, 9), dict) else {}
    g2000 = meta.get("2000") if isinstance(meta.get("2000"), list) else []
    g2003 = meta.get("2003") if isinstance(meta.get("2003"), list) else []
    g2006 = meta.get("2006") if isinstance(meta.get("2006"), list) else []
    link = _str(_at(orig, 0))
    page_link = _str(_at(g2003, 2))
    docid = _str(_at(g2003, 1))
    domain = _str(_at(g2003, 17)) or _str(_at(g2000, 1)) or (urlparse(page_link).netloc.lower() if page_link else None)
    product = _product(_at(g2006, 1))
    video = _video(_at(g2006, 8))
    licence = _licence(_at(g2006, 11))
    kind = KINDS.get(_int(_at(entry, 5)), "image")
    return {
        "position": position,
        "id": tbnid,
        "page_id": docid,
        "title": clean_text(_at(g2003, 3)),
        "link": link,
        "width": _int(_at(orig, 2)),
        "height": _int(_at(orig, 1)),
        "file_size": _str(_at(g2000, 2)),
        "format": _format(link),
        "dominant_color": _str(_at(entry, 6)),
        "thumbnail": {"link": _str(_at(thumb, 0)), "width": _int(_at(thumb, 2)), "height": _int(_at(thumb, 1))},
        "source": {
            "name": clean_text(_at(g2003, 12)),
            "domain": domain,
            "page_link": page_link,
            "favicon": _str(_at(g2003, 7)),
        },
        "type": kind,
        "is_product": product is not None,
        "is_video": video is not None,
        "is_licensable": licence is not None or kind == "licensable",
        "credits": _credits(_at(g2003, 18)),
        "license": licence,
        "product": product,
        "video": video,
        "about_this_image_link": _str(_at(g2003, 33)),
        "google_link": google_link(tbnid, docid, link, page_link) if tbnid else None,
    }


def _dom_tiles(doc):
    """[(tbnid, docid, page_link, title, site_name)] in page order."""
    out = []
    for el in doc.cssselect(TILE_CSS):
        out.append((el.get("data-docid"), el.get("data-ref-docid") or None, el.get("data-lpage") or None,
                    text(first(el, ".Q6A6Dc")), text(first(el, '[data-snf="F0zcsf"] span, .K8ZDdf span'))))
    return out


def _document(raw):
    """lxml refuses an empty body; an empty page has no tiles either way."""
    raw = raw or ""
    return parse_document(raw if raw.strip() else "<html></html>")


def _records(raw, doc, offset=0):
    """The page's tiles in DOM order as records, data-map entries filled
    in; a tile the map does not describe still yields its DOM facts."""
    entries = tile_entries(raw)
    seen = set()
    out = []
    dom = _dom_tiles(doc)
    for tbnid, docid, page_link, title, site in dom:
        if not tbnid or tbnid in seen:
            continue
        seen.add(tbnid)
        entry = entries.get(tbnid)
        rec = parse_tile(entry, offset + len(out) + 1) if entry else parse_tile([0, tbnid], offset + len(out) + 1)
        rec["page_id"] = rec["page_id"] or docid
        rec["title"] = rec["title"] or title
        rec["source"]["page_link"] = rec["source"]["page_link"] or page_link
        rec["source"]["name"] = rec["source"]["name"] or site
        if not rec["source"]["domain"] and rec["source"]["page_link"]:
            rec["source"]["domain"] = urlparse(rec["source"]["page_link"]).netloc.lower() or None
        if rec["google_link"] is None or docid and "docid=" not in rec["google_link"]:
            rec["google_link"] = google_link(tbnid, rec["page_id"], rec["link"], rec["source"]["page_link"])
        out.append(rec)
    if not dom:   # a fragment whose DOM lxml could not see: data order
        for tbnid, entry in entries.items():
            if tbnid not in seen:
                seen.add(tbnid)
                out.append(parse_tile(entry, offset + len(out) + 1))
    return out


def _chips(doc):
    out = []
    for a in doc.cssselect("a.nPDzT"):
        label = text(a)
        if label:
            out.append({"text": label, "query": query_of(a.get("href")), "link": absolute(a.get("href"))})
    return out


def _related_searches(doc):
    out = []
    for a in doc.cssselect("a.bqW4cb"):
        q = query_of(a.get("href")) or text(a)
        if q:
            out.append({"query": q, "link": absolute(a.get("href"))})
    return out


def parse_search_page(html, offset=0):
    """A results page (page 1 of a query, or a related-images page)."""
    doc = _document(html)
    total, _ = result_stats(html)
    return {
        "search_information": {"query": page_query(doc) or None, "total_results": total},
        "images": _records(html, doc, offset),
        "suggested_filters": _chips(doc),
        "related_searches": _related_searches(doc),
    }


def parse_fragment(raw, offset=0):
    """A paging fragment (asearch=arc): the next 100 tiles, or none past
    the ceiling."""
    doc = _document(raw)
    return {"images": _records(raw, doc, offset)}


def parse_viewer(raw, tbnid=None):
    """The viewer fragment of one image: its own record when the fragment
    carries it (no `q` sent), the 12 related tiles, the related-images
    token and the Licensable badge."""
    raw = raw or ""
    doc = _document(raw)
    entries = tile_entries(raw)
    related = _records(raw, doc)
    related = [r for r in related if r["id"] != tbnid]
    for i, r in enumerate(related, 1):
        r["position"] = i
    main = parse_tile(entries[tbnid]) if tbnid and tbnid in entries else None
    if main:
        main.pop("position", None)
    token = _RIMG_RE.search(raw)
    badge = any((text(el) or "").lower() == "licensable" for el in doc.cssselect(".KO6kAc"))
    return {
        "image": main,
        "is_licensable": badge or bool(main and main["is_licensable"]),
        "related_images": related,
        "related_token": token.group(0) if token else None,
    }


def is_empty_viewer(raw):
    """Google answers a bare / unknown id with a ~90-260 byte header-only
    fragment: no tiles, no token."""
    raw = raw or ""
    return "data-docid" not in raw and "rimg:" not in raw


# ---- suggestions ------------------------------------------------------------------------------------

def parse_autocomplete(raw):
    """window.google.ac.h(["q", [[html, 0, [subtypes]], …], {…}]) -> rows."""
    raw = (raw or "").strip()
    m = _JSONP_RE.match(raw)
    body = m.group(1) if m else raw
    try:
        data = json.loads(body)
    except ValueError:
        return []
    rows = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    out = []
    for row in rows:
        html_text = row[0] if isinstance(row, list) and row else row
        label = clean_text(html_text) if isinstance(html_text, str) else None
        if not label:
            continue
        out.append({"position": len(out) + 1, "text": label,
                    "subtypes": row[2] if isinstance(row, list) and len(row) > 2 and isinstance(row[2], list) else None})
    return out
