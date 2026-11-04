"""Offline tests for google_images/api.py's details flow (no network: the
fetch layer and the cache are stubbed).

    cd scrapers && python -m pytest google_images/test_api.py -q
"""
import gzip
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_images import api, fetch, parsers, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
AKC, AKC_PAGE = "jUS0xT_ulT-SUM", "DJEEXDk_P7gPSM"
AKC_LINK = "https://s3.amazonaws.com/cdn-origin-etr.akc.org/wp-content/uploads/2020/07/09151754/Golden-Retriever-puppy-standing-outdoors.jpg"
AKC_PAGE_LINK = "https://www.akc.org/expert-advice/dog-breeds/golden-retriever-puppy-training-timeline/"


def load(name):
    with gzip.open(os.path.join(FX, name + ".gz"), "rt", encoding="utf-8", errors="replace") as f:
        return f.read()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "cached_call", lambda ns, data, fn, ttl: fn(**data))
    monkeypatch.setattr(api, "_records", api.OrderedDict())

    def permalink_page(tbnid, docid, page_link, link, country, language):
        calls.append((tbnid, docid, page_link, link))
        return load("pod_permalink_page.html" if tbnid == AKC else "pod_permalink_unknown_id.html")
    monkeypatch.setattr(fetch, "permalink_page", permalink_page)
    return calls


def test_details_from_the_google_link_alone(offline):
    ref = refs.resolve_image(refs.google_link(AKC, AKC_PAGE, AKC_LINK, AKC_PAGE_LINK))
    out = api.image_details(ref, "US", "en")
    assert offline == [(AKC, AKC_PAGE, AKC_PAGE_LINK, AKC_LINK)]
    assert out["title"] == "How to Train a Golden Retriever Puppy: Growth & Training Timeline"
    assert (out["width"], out["height"], out["file_size"]) == (729, 486, "190KB")
    assert out["related_images_count"] == 12 and out["related_images_link"].startswith("https://www.google.com/search?udm=2&tbs=rimg")
    assert out["google_link"] == refs.google_link(AKC, AKC_PAGE, AKC_LINK, AKC_PAGE_LINK)
    assert "position" not in out


def test_details_fills_from_a_remembered_search_tile(offline):
    tile = next(i for i in parsers.parse_search_page(load("search_page1.html"))["images"] if i["id"] == AKC)
    api._remember([tile])
    out = api.image_details({"id": AKC, "page_id": None, "link": None, "page_link": None}, "US", "en")
    assert offline[0][:3] == (AKC, AKC_PAGE, AKC_PAGE_LINK)
    assert out["credits"]["credit_line"] == "Getty Images/iStockphoto"     # only the search tile has it
    assert out["dominant_color"] == "rgb(176,160,106)"


def test_details_unknown_bare_id_is_404(offline):
    with pytest.raises(fetch.GoogleImagesNotFound, match="page id is not known"):
        api.image_details({"id": "zzzzzzzzzzzzzz", "page_id": None, "link": None, "page_link": None}, "US", "en")
    assert offline == []


def test_details_needs_the_page_link(offline):
    with pytest.raises(fetch.GoogleImagesBadRequest, match="full google_link"):
        api.image_details(refs.resolve_image(f"https://www.google.com/imgres?tbnid={AKC}&docid={AKC_PAGE}"), "US", "en")


def test_details_unknown_permalink_is_404(offline):
    ref = refs.resolve_image(refs.google_link("zzzzzzzzzzzzzz", "yyyyyyyyyyyyyy", None, "https://example.com/p"))
    with pytest.raises(fetch.GoogleImagesNotFound, match="has no image"):
        api.image_details(ref, "US", "en")


def test_wall_verdict_is_the_wall_marker_only():
    class R:
        def __init__(self, text, status=200, url="https://www.google.com/x"):
            self.text, self.status_code, self.url = text, status, url
    assert fetch._fragment_verdict(R(load("wall.html"))) == "wall"
    assert fetch._fragment_verdict(R(load("pod_permalink_unknown_id.html"))) == "ok"
    assert fetch._fragment_verdict(R(load("pod_fragment_start30_empty.html"))) == "ok"
    assert fetch._fragment_verdict(R(load("pod_permalink_page.html"))) == "ok"
    assert fetch._fragment_verdict(R("", 429)) == "sorry"
    assert fetch._fragment_verdict(R("", 200, "https://www.google.com/sorry/index?x")) == "sorry"


def test_related_falls_back_to_the_permalink_token(offline, monkeypatch):
    viewer = parsers.parse_viewer(load("pod_viewer.html"), AKC)
    viewer["related_token"] = None                       # a viewer answer without the token
    monkeypatch.setattr(api, "_viewer", lambda **kw: viewer)
    seen = {}

    def results_page(params, label=None):
        seen["tbs"] = params["tbs"]
        return load("pod_related_page1.html")
    monkeypatch.setattr(fetch, "results_page", results_page)
    ref = refs.resolve_image(refs.google_link(AKC, AKC_PAGE, AKC_LINK, AKC_PAGE_LINK))
    out = api._related(ref, 1, None, "US", "en", None)
    assert seen["tbs"].startswith("rimg:") and len(out["images"]) == 100


def test_a_viewer_without_its_token_is_not_cached():
    assert api._viewer_ttl({}, {"related_token": None}) is None
    assert api._viewer_ttl({}, {"related_token": "rimg:x"}) == api.ttl.VIEWER_CACHE


def test_an_empty_first_related_page_is_not_cached():
    assert api._related_ttl({"page": 1}, {"images": []}) is None
    assert api._related_ttl({"page": 3}, {"images": []}) == api.ttl.RELATED_CACHE
    assert api._related_ttl({"page": 1}, {"images": [{"id": "x"}]}) == api.ttl.RELATED_CACHE
