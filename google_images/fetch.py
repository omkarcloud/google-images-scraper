"""Google Images transport. Two kinds of surface:

  * IDENTITY-BACKED — the results page (/search?udm=2), its paging
    fragments (asearch=arc, start=10 / 20), the viewer (/async/imgv) and
    the related-images page (/search?udm=2&tbs=rimg:…). Every one of them
    answers a bare HTTP client with the botguard "enable JavaScript" wall
    or the /sorry reCAPTCHA whatever the exit (direct, datacenter proxy,
    residential proxy; chrome / safari / edge TLS; iPhone,
    Android, Googlebot, Nokia and Lynx user agents; a home-page-first
    cookie flow; a headed Chrome and a headed Camoufox without a solver —
    60 + 120 trials 2026-11-03, and the pod probe table in config.py's
    "--- google images ---" block). What passes is the SERP IDENTITY of
    google_search/identity.py: minted on the Windows browser box (Camoufox
    + the CapSolver extension on a fresh sticky residential proxy exit),
    replayed here over curl_cffi through the same exit. This module
    only chooses the path, params, headers and the verdict; the pool, its
    TTL / re-mint / /sorry revive and the exit all stay in identity.py,
    shared with /google-search/* in the same process. Identity-backed
    calls proven from the relays pod 2026-11-03 (fixtures in
    google_images/fixtures/pod_*): page 1, start=10 (100 tiles), start=20
    (97), start=30 (empty = the 300 ceiling), viewer, related page; the
    /imgres permalink page 2026-11-04.

  * OPEN — image suggestions (/complete/search?client=img&ds=i): plain
    curl_cffi, no cookies, one session per thread on
    config.google_images_proxy() (direct by default; the pod's own IP
    passed the probe), dropped on every retryable failure so the retry
    rides a fresh exit.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  GoogleImagesUpstreamError  transport failure / 5xx / unparseable body  — retryable
  GoogleImagesBlocked        wall / captcha on every identity, 403 / 429  — retryable
  GoogleImagesBadRequest     Google rejected the params (HTTP 400)       — never retried
  GoogleImagesNotFound       unknown image id / missing page id          — never retried
"""
import os
import sys
import threading
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from google_search import fetch as gfetch, identity
from google_images.refs import SITE

IMPERSONATE = "chrome"
AUTOCOMPLETE_TIMEOUT = 15
PAGE_SIZE = 100            # tiles per results page / paging fragment at most
MAX_PAGES = 3              # start=30 and past answer an empty fragment (Google's 300-image ceiling)
ARC_ASYNC = "arc_id:srp_110,ffilt:all,ve_name:MoreResultsContainer,inf:1,_id:arc-srp_110,_pms:s,_fmt:pc"

# The identity's page headers (identity.SERP_HEADERS) describe a document
# navigation; the fragments are the page's own XHRs.
XHR_HEADERS = {
    "accept": "*/*",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}
SUGGEST_HEADERS = {
    "accept": "*/*",
    "accept-language": egress.site_accept_language("google-images"),
    "referer": SITE + "/",
}


class GoogleImagesUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unparseable body — retryable."""


class GoogleImagesBlocked(GoogleImagesUpstreamError, Blocked):
    """The wall / captcha on every identity, or 403 / 429 — retryable."""


class GoogleImagesBadRequest(BadRequest):
    """Google rejected the params — never retried."""


class GoogleImagesNotFound(NotFound):
    """Unknown image id, or an id whose page id is not known — never retried."""


# ---- identity-backed surfaces ---------------------------------------------------------------------

# HTTP 403 is Google turning the IDENTITY away (its exit / cookies), not the
# request: prod 2026-11-19 07:54-08:11 UTC, every images search was a 502
# "images-search: HTTP 403" for 17 minutes, 15 in a row, while two identities
# minted after it sat unused. The SERP classifier reads a 403 page as "ok"
# (it carries neither the /sorry nor the wall markers), so the response came
# back here, the identity went back to the pool and, being the most used,
# was handed to the next call. As a verdict of its own ("refused") the
# identity is retired and the call moves on to the next one.

def _page_verdict(resp):
    """The identity verdict for a results page: the SERP classifier's
    ('sorry' revives, 'wall' retires), plus 'refused' for an HTTP 403."""
    if resp.status_code == 403:
        return "refused"
    return identity.classify(resp.text, str(resp.url))


def _fragment_verdict(resp):
    """The identity verdict for a fragment: 'sorry' re-mints / revives,
    'wall' and 'refused' (HTTP 403) retire the identity, anything else (an
    empty fragment, an HTTP 400 for bad params) comes back to the caller as
    the response."""
    url = str(resp.url)
    if resp.status_code == 403:
        return "refused"
    if "/sorry/" in url or resp.status_code == 429:
        return "sorry"
    text = resp.text or ""
    # the botguard wall's own markers (google_images/fixtures/wall.html: the
    # SG_REL error code and the big "enable JavaScript" shell); an empty
    # fragment or an unknown id's permalink page carries none of them
    wall = "emsg=SG_REL" in text or ("enablejs" in text and len(text) > 50_000)
    if resp.status_code == 200 and wall and "data-docid" not in text:
        return "wall"
    return "ok"


def _replay(path, params, label, fragment=False):
    try:
        if fragment:
            resp = identity.replay(path, params, label=label, verdict=_fragment_verdict, headers=XHR_HEADERS)
        else:
            resp = identity.replay(path, params, label=label, verdict=_page_verdict)
    except gfetch.GoogleBlocked as e:
        raise GoogleImagesBlocked(str(e))
    except gfetch.GoogleUpstreamError as e:
        raise GoogleImagesUpstreamError(str(e))
    if resp.status_code == 400:
        gfetch.dump_debug(f"images_{label}_400", resp.text)
        raise GoogleImagesBadRequest(f"{label}: Google rejected the request (HTTP 400)")
    if resp.status_code in (403, 429):
        raise GoogleImagesBlocked(f"{label}: HTTP {resp.status_code}")
    if resp.status_code >= 500:
        raise GoogleImagesUpstreamError(f"{label}: HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise GoogleImagesUpstreamError(f"{label}: unexpected HTTP {resp.status_code}")
    return resp.text or ""


def base_params(query, country, language, tbs=None, safe=None, location=None):
    params = {"q": query, "udm": 2, "hl": language or "en", "gl": (country or "us").lower()}
    if tbs:
        params["tbs"] = tbs
    if safe:
        params["safe"] = safe
    if location:
        params["uule"] = location
    return params


def results_page(params, label="images-search"):
    """Page 1 of a results page (/search?udm=2&…) through an identity."""
    return _replay("/search", params, label)


def results_fragment(params, start, label="images-page"):
    """The paging fragment Google's page itself requests on scroll: the
    tiles from `start` (10 = the second hundred, 20 = the third)."""
    return _replay("/search", {**params, "start": start, "sa": "N", "asearch": "arc", "cs": 1, "async": ARC_ASYNC},
                   label, fragment=True)


def permalink_page(tbnid, docid, page_link, link, country, language, label="images-permalink"):
    """Google's own page for one image (/imgres, the record's google_link):
    the image's record, its 12 related tiles, the related-images token and
    the Licensable badge — everything images/details needs in one fetch
    (relays pod 2026-11-04). It needs the page link (`imgrefurl`): with only
    tbnid + docid Google answers a blank "Google Images" page. An unknown id
    answers a "Google Image Result" page with no tiles."""
    params = {"tbnid": tbnid, "docid": docid, "imgrefurl": page_link, "hl": language or "en",
              "gl": (country or "us").lower()}
    if link:
        params["imgurl"] = link
    return _replay("/imgres", params, label, fragment=True)


def viewer(tbnid, docid, country, language, query=None, label="images-viewer"):
    """The side-panel fragment of one image: its 12 related tiles, the
    Licensable badge and the related-images token (never the image's own
    record — the page that opened the viewer already has it; with or
    without `q`, relays pod 2026-11-03). An unknown id or a missing docid
    answers a header-only fragment (parsers.is_empty_viewer)."""
    params = {"hl": language or "en", "gl": (country or "us").lower(), "udm": 2, "yv": 3,
              "tbnid": tbnid, "imgdii": tbnid, "cs": 1, "async": "_fmt:pc"}
    if docid:
        params["docid"] = docid
    if query:
        params["q"] = query
    return _replay("/async/imgv", params, label, fragment=True)


# ---- the open suggestions surface ---------------------------------------------------------------------

_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        proxy = config.google_images_proxy()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers.update({"accept-language": egress.accept_language(proxy)})
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def suggestions(query, country, language):
    """Raw JSONP of /complete/search?client=img&ds=i (image suggestions)."""
    url = f"{SITE}/complete/search?" + urlencode({"q": query, "client": "img", "ds": "i",
                                                  "hl": language or "en", "gl": (country or "us").lower()})
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _session().get(url, headers=SUGGEST_HEADERS, timeout=AUTOCOMPLETE_TIMEOUT)
        except Exception as e:
            last = GoogleImagesUpstreamError(f"suggestions: request failed: {type(e).__name__}: {e}")
        else:
            if resp.status_code == 200:
                return resp.text or ""
            if resp.status_code in (403, 429):
                last = GoogleImagesBlocked(f"suggestions: HTTP {resp.status_code}")
            elif resp.status_code == 400:
                raise GoogleImagesBadRequest("suggestions: Google rejected the query (HTTP 400)")
            else:
                last = GoogleImagesUpstreamError(f"suggestions: HTTP {resp.status_code}")
        _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last
