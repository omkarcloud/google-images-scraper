"""The /google-images/* endpoint functions (route_glue's route_table calls
them with the schema's loaded kwargs). Caching lives here
(cache.cached_call keyed on the validated params):

  * images/search    one row per (query, filters, page)
  * images/details   one row per image: Google's own page for it (/imgres,
                     the record's google_link) carries its record, 12
                     related tiles, the related-images token and the badge
                     (_permalink_record)
  * images/related   the viewer (/async/imgv, _viewer_record) for the
                     related-images token — it needs only the two ids — then
                     one row per related page
  * images/autocomplete, images/reverse-search cache their own responses

Google needs the image id AND its page id (`docid`) for both, and the
permalink page also needs the image's page link (`imgrefurl`). Every record
this API returns carries all three (`page_id`, `source.page_link` and the
`google_link` permalink that holds them), and records seen in searches are
remembered in this process (cache hits included): a bare id works right
after a search; the google_link works always; an id this process never saw
and no page id for is a 404 that says to pass the google_link. The
permalink page's own entry is leaner than a search tile (no credits, no
dominant colour), so details fills those from a remembered tile.

Page sizes (relays pod, 2026-11-03): the results page serves 50-100 tiles,
its scroll fragments 100 each. Page 1 is the results page (filter chips,
related searches, total) topped up from the start=0 fragment when it came
short; pages 2 and 3 are the start=10 / 20 fragments; start=30 is empty.
"""
import copy
import threading
from collections import OrderedDict

from cache import cached_call
from google_images import cache_config as ttl
from google_images import fetch, parsers, refs
from google_images.fetch import GoogleImagesBadRequest, GoogleImagesNotFound
from google_search import serp

RECORDS_REMEMBERED = 20_000      # image records kept from searches (~2 KB each)
_records = OrderedDict()
_records_lock = threading.Lock()


def _remember(images):
    with _records_lock:
        for img in images:
            if img.get("id") and img.get("page_id"):
                _records[img["id"]] = img
                _records.move_to_end(img["id"])
        while len(_records) > RECORDS_REMEMBERED:
            _records.popitem(last=False)


def _known(tbnid):
    with _records_lock:
        rec = _records.get(tbnid)
    return copy.deepcopy(rec) if rec else None


def _page_id_of(ref):
    if ref.get("page_id"):
        return ref["page_id"]
    rec = _known(ref["id"])
    return rec["page_id"] if rec else None


def _merge(first, more):
    """`more` (the fuller list) in its own order, then anything only the
    page had; positions renumbered."""
    seen = set()
    out = []
    for img in list(more) + list(first):
        if img["id"] in seen:
            continue
        seen.add(img["id"])
        img["position"] = len(out) + 1
        out.append(img)
    return out


def _pagination(page, images, total=None):
    """Google publishes no page count: `has_next` drives the next link,
    `total_count` is its "About N results" when the page showed one."""
    return {"page": page, "items_per_page": fetch.PAGE_SIZE, "total_pages": None, "total_count": total,
            "has_next": page < fetch.MAX_PAGES and bool(images)}


# ---- images/search --------------------------------------------------------------------------------

def _filters_tbs(size, color, image_type, aspect_ratio, file_type, usage_rights, time_period):
    return serp._tbs(serp.IMAGE_SIZES.get(size), serp.IMAGE_COLORS.get(color), serp.IMAGE_TYPES.get(image_type),
                     serp.IMAGE_ASPECTS.get(aspect_ratio), serp.IMAGE_FORMATS.get(file_type),
                     serp.IMAGE_RIGHTS.get(usage_rights), serp.TIME_PERIODS.get(time_period or "any"))


def _search(query, country, language, location, page, size, color, image_type, aspect_ratio, file_type,
            usage_rights, time_period, safe, site):
    q = f"{query} site:{site}" if site else query
    tbs = _filters_tbs(size, color, image_type, aspect_ratio, file_type, usage_rights, time_period)
    params = fetch.base_params(q, country, language, tbs=tbs, safe=serp.SAFE.get(safe) if safe else None,
                               location=location)
    if page == 1:
        out = parsers.parse_search_page(fetch.results_page(params))
        if len(out["images"]) < fetch.PAGE_SIZE:
            # the page itself serves 50-100 tiles; the page's own first
            # scroll fragment (start=0) serves the full hundred
            more = parsers.parse_fragment(fetch.results_fragment(params, 0))["images"]
            out["images"] = _merge(out["images"], more)
    else:
        # positions run on across pages (page 2 starts at 101), as the
        # fragment parser's offset is meant to be used
        out = parsers.parse_fragment(fetch.results_fragment(params, (page - 1) * 10),
                                     offset=(page - 1) * fetch.PAGE_SIZE)
        out = {"search_information": {"query": q, "total_results": None}, **out,
               "suggested_filters": [], "related_searches": []}
    out["search_information"]["query"] = out["search_information"].get("query") or q
    _remember(out["images"])
    out["pagination"] = _pagination(page, out["images"], out["search_information"].get("total_results"))
    out["count"] = len(out["images"])
    return out


def images_search(**data):
    out = cached_call("google-images.search", data, _search, ttl.SEARCH_CACHE)
    _remember(out.get("images") or [])     # a cache hit skips _search: remember its records too
    return out


# ---- the shared viewer record ------------------------------------------------------------------

def _viewer(tbnid, docid, country, language):
    raw = fetch.viewer(tbnid, docid, country, language)
    if parsers.is_empty_viewer(raw):
        raise GoogleImagesNotFound(f"Google has no viewer for image {tbnid} with page id {docid}: "
                                   "check the id, or pass the record's google_link")
    record = parsers.parse_viewer(raw, tbnid)
    _remember(record["related_images"])
    return record


def _viewer_ttl(data, record):
    """Some viewer answers carry the tiles but no related-images token (the
    AKC puppy photo, relays pod 2026-11-04); caching one would empty
    images/related for a day, so only a viewer with its token is kept."""
    return ttl.VIEWER_CACHE if record and record.get("related_token") else None


def _viewer_record(tbnid, docid, country, language):
    return cached_call("google-images.viewer", {"tbnid": tbnid, "docid": docid, "country": country,
                                                "language": language}, _viewer, _viewer_ttl)


def _resolve(ref):
    docid = _page_id_of(ref)
    if not docid:
        raise GoogleImagesNotFound(
            f"image {ref['id']}: its page id is not known. Pass the record's google_link "
            "(https://www.google.com/imgres?…&tbnid=…&docid=…) or search for the image first.")
    return ref["id"], docid


def _related_link(token, country, language, page=None):
    return refs.images_link_tbs(token, country, language, start=(page - 1) * 10 if page and page > 1 else None)


# ---- images/details -------------------------------------------------------------------------------

def _permalink(tbnid, docid, page_link, link, country, language):
    raw = fetch.permalink_page(tbnid, docid, page_link, link, country, language)
    record = parsers.parse_viewer(raw, tbnid)
    if record["image"] is None:
        raise GoogleImagesNotFound(f"Google has no image {tbnid} on page id {docid}: "
                                   "check the id, or pass the record's google_link")
    _remember(record["related_images"])
    return record


def _permalink_record(tbnid, docid, page_link, link, country, language):
    return cached_call("google-images.permalink", {"tbnid": tbnid, "docid": docid, "page_link": page_link, "link": link,
                                                   "country": country, "language": language},
                       _permalink, ttl.PERMALINK_CACHE)


def _fill(target, extra):
    """Fill target's None values from extra, nested dicts included."""
    for key, value in (extra or {}).items():
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _fill(target[key], value)
        elif target.get(key) is None and value is not None:
            target[key] = value
    return target


def image_details(image, country, language):
    tbnid, docid = _resolve(image)
    known = _known(tbnid)
    page_link = image.get("page_link") or (known or {}).get("source", {}).get("page_link")
    link = image.get("link") or (known or {}).get("link")
    if not page_link:
        raise GoogleImagesBadRequest(
            f"image: Google's page for image {tbnid} needs its page link. Pass the record's full google_link "
            "(https://www.google.com/imgres?imgurl=…&imgrefurl=…&tbnid=…&docid=…).")
    record = _permalink_record(tbnid, docid, page_link, link, country, language)
    main = copy.deepcopy(record["image"])
    main.pop("position", None)
    if known:   # a search tile is richer (credits, dominant colour) than the permalink page's entry
        known.pop("position", None)
        _fill(main, known)
    main["page_id"] = main["page_id"] or docid
    main["link"] = main["link"] or link
    main["source"]["page_link"] = main["source"]["page_link"] or page_link
    main["google_link"] = refs.google_link(tbnid, main["page_id"], main["link"], main["source"]["page_link"])
    main["is_licensable"] = bool(main["is_licensable"] or record["is_licensable"])
    _remember([main])    # a bare id (and the related fallback's page link) now works after details too
    token = record["related_token"]
    return {
        **main,
        "related_images": record["related_images"],
        "related_images_count": len(record["related_images"]),
        "related_images_link": _related_link(token, country, language) if token else None,
    }


# ---- images/related ---------------------------------------------------------------------------------

def _related_token(image, tbnid, docid, country, language):
    """The rimg: token of the image's related-images search: the viewer's
    (it needs only the two ids), else the image's own page's when its page
    link is known (it carries one too)."""
    token = _viewer_record(tbnid, docid, country, language)["related_token"]
    if token:
        return token
    known = _known(tbnid)
    page_link = image.get("page_link") or (known or {}).get("source", {}).get("page_link")
    if not page_link:
        return None
    link = image.get("link") or (known or {}).get("link")
    return _permalink_record(tbnid, docid, page_link, link, country, language)["related_token"]


def _related(image, page, query, country, language, safe):
    tbnid, docid = _resolve(image)
    if page > 1 and not query:
        # the related page's scroll fragments answer empty without the
        # search the image was found in (relays pod 2026-11-03)
        raise GoogleImagesBadRequest("query: pages past the first need the search the image was found in "
                                     "(query=…); page 1 works without it")
    token = _related_token(image, tbnid, docid, country, language)
    if not token:
        return {"image": {"id": tbnid, "page_id": docid, "google_link": refs.google_link(tbnid, docid)},
                "images": [], "pagination": _pagination(page, []), "count": 0}
    params = {"udm": 2, "hl": language or "en", "gl": (country or "us").lower(), "tbs": token, "tbnid": tbnid}
    if query:
        params["q"] = query
    if safe:
        params["safe"] = serp.SAFE.get(safe)
    if page == 1:
        images = parsers.parse_search_page(fetch.results_page(params, label="images-related"))["images"]
    else:
        images = parsers.parse_fragment(fetch.results_fragment(params, (page - 1) * 10, label="images-related-page"),
                                        offset=(page - 1) * fetch.PAGE_SIZE)["images"]
    _remember(images)
    return {
        "image": {"id": tbnid, "page_id": docid, "google_link": refs.google_link(tbnid, docid),
                  "related_images_link": _related_link(token, country, language, page)},
        "images": images,
        "pagination": _pagination(page, images),
        "count": len(images),
    }


def _related_ttl(data, result):
    """An empty related page is kept only past the first page (Google's
    real end); an empty first page means no token was found this time."""
    return ttl.RELATED_CACHE if result and (result.get("images") or data.get("page", 1) > 1) else None


def related_images(**data):
    out = cached_call("google-images.related", data, _related, _related_ttl)
    _remember(out.get("images") or [])
    return out


# ---- images/autocomplete --------------------------------------------------------------------------

def _autocomplete(query, country, language, limit):
    items = parsers.parse_autocomplete(fetch.suggestions(query, country, language))[:limit]
    return {"query": query, "country": (country or "US").upper(), "language": language or "en",
            "count": len(items), "suggestions": items}


def autocomplete(**data):
    return cached_call("google-images.autocomplete", data, _autocomplete, ttl.AUTOCOMPLETE_CACHE)


# ---- images/reverse-search (Google Lens) --------------------------------------------------------

def _reverse_search(image, match, country, language):
    from google_lens import search as lens_search
    if match == "visual":
        out = lens_search.visual_matches(image, country=country or "US", language=language or "en")
        matches = out.get("visual_matches") or []
    else:
        out = lens_search.exact_matches(image, country=country or "US", language=language or "en")
        matches = out.get("exact_matches") or []
    return {"match": match, "count": len(matches), "matches": matches, "image": out.get("image")}


def reverse_search(**data):
    return cached_call("google-images.reverse", data, _reverse_search, ttl.REVERSE_SEARCH_CACHE)
