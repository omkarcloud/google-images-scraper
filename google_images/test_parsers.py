"""Offline tests for the Google Images parsers and reference resolvers.

    cd scrapers && python -m pytest google_images/test_parsers.py -q

Fixtures (google_images/fixtures/, captured 2026-11-03): results pages
from a real Chrome session (search_page1: 100 tiles with chips and related
searches; search_filtered; search_no_results: Google still finds 57 tiles
for gibberish) and from the relays pod's minted identity (pod_search_page1:
50 tiles), the pod's scroll fragments (start=0 / 10 / 20 full, start=30
empty), viewers (with a query, without one, a product tile, an unknown id,
no page id), related-images pages (page 1, the start=10 fragment with the
query, the empty fragment without it), the image-suggestion JSONP (full and
empty), the botguard wall and a /sorry fragment. Captured 2026-11-04 from
the pod: the image's own /imgres page (the AKC puppy photo) and the same
page for an unknown id. No network.
"""
import gzip
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_images import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
AKC = "jUS0xT_ulT-SUM"
AKC_PAGE = "DJEEXDk_P7gPSM"


def load(name):
    with gzip.open(os.path.join(FX, name + ".gz"), "rt", encoding="utf-8", errors="replace") as f:
        return f.read()


@pytest.fixture(scope="module")
def page1():
    return P.parse_search_page(load("search_page1.html"))


# ---- results page -------------------------------------------------------------------------------

def test_results_page_facts(page1):
    assert page1["search_information"] == {"query": "golden retriever puppy", "total_results": 114000000}
    assert len(page1["images"]) == 100
    assert [i["position"] for i in page1["images"]] == list(range(1, 101))
    assert len({i["id"] for i in page1["images"]}) == 100
    assert all(i["link"] and i["page_id"] and i["source"]["page_link"] for i in page1["images"])
    assert [c["text"] for c in page1["suggested_filters"]][:3] == ["Newborn", "Wallpaper", "Girl"]
    assert page1["suggested_filters"][0]["query"] == "newborn golden retriever puppy"
    assert page1["suggested_filters"][0]["link"].startswith("https://www.google.com/search?")
    assert len(page1["related_searches"]) == 12
    assert page1["related_searches"][0]["query"] == "newborn golden retriever puppy"


def test_first_tile_record(page1):
    rec = page1["images"][0]
    assert rec["id"] == AKC and rec["page_id"] == AKC_PAGE
    assert rec["title"] == "How to Train a Golden Retriever Puppy: Growth & Training Timeline"
    assert rec["link"].startswith("https://s3.amazonaws.com/cdn-origin-etr.akc.org/")
    # the data map lists [height, width]; the tile's aspect-ratio style is 678/452 (landscape)
    assert (rec["width"], rec["height"]) == (729, 486)
    assert rec["thumbnail"]["link"].startswith("https://encrypted-tbn0.gstatic.com/images?q=tbn:")
    assert (rec["thumbnail"]["width"], rec["thumbnail"]["height"]) == (678, 452)
    assert rec["file_size"] == "190KB" and rec["format"] == "jpg"
    assert rec["dominant_color"] == "rgb(176,160,106)"
    assert rec["source"] == {
        "name": "American Kennel Club", "domain": "www.akc.org",
        "page_link": "https://www.akc.org/expert-advice/dog-breeds/golden-retriever-puppy-training-timeline/",
        "favicon": rec["source"]["favicon"]}
    assert rec["source"]["favicon"].startswith("https://encrypted-tbn0.gstatic.com/")
    assert rec["credits"] == {"credit_line": "Getty Images/iStockphoto", "creators": ["Bigandt_Photography"],
                              "copyright": "Bigandt_Photography"}
    assert rec["type"] == "image" and not rec["is_product"] and not rec["is_video"] and not rec["is_licensable"]
    assert rec["license"] is None and rec["product"] is None and rec["video"] is None
    assert rec["about_this_image_link"].startswith("https://www.google.com/search/about-this-image?")
    assert rec["google_link"].startswith("https://www.google.com/imgres?imgurl=https%3A%2F%2Fs3.amazonaws.com")
    assert f"tbnid={AKC}&docid={AKC_PAGE}" in rec["google_link"]


def test_product_video_and_licence_tiles(page1):
    product = next(i for i in page1["images"] if i["id"] == "KJlRJJt_Dm_trM")
    assert product["type"] == "product" and product["is_product"]
    assert product["product"] == {
        "id": "1353743905369073464", "title": "Golden Retriever Puppy", "seller": "Photowall",
        "description": product["product"]["description"],
        "price": {"amount": 3.9, "currency": "USD"}, "original_price": None, "rating": None,
        "shopping_link": "https://www.google.com/search?q=golden+retriever+puppy&prds=headlineOfferDocid:"
                         "1353743905369073464,productDocid:1353743905369073464,pvo:4&ibp=oshop"}
    assert product["product"]["description"].startswith("Bring the joy of playful puppies")
    sale = next(i for i in page1["images"] if i["product"] and i["product"]["original_price"])
    assert sale["product"]["price"] == {"amount": 30, "currency": "USD"}
    assert sale["product"]["original_price"] == {"amount": 36, "currency": "USD"}
    assert sale["product"]["rating"] == 4.6
    video = next(i for i in page1["images"] if i["id"] == "R2WnZF2Av4IDAM")
    assert video["type"] == "video" and video["is_video"]
    assert video["video"]["duration"] == "0:45" and video["video"]["duration_seconds"] == 45
    assert video["video"]["views"] == 323223 and video["video"]["published_date"] == "2025-11-11"
    assert (video["width"], video["height"]) == (640, 1136)   # a portrait reel
    yt = next(i for i in page1["images"] if i["video"] and i["video"]["channel"])
    assert yt["video"]["channel"] == "Girl With The Dogs" and yt["video"]["duration_seconds"] == 857
    istock = next(i for i in page1["images"] if i["license"] and i["license"]["provider"] == "iStock")
    assert istock["type"] == "licensable" and istock["is_licensable"]
    assert istock["license"]["details_link"].startswith("https://www.istockphoto.com/photo/")
    assert istock["license"]["terms_link"] == "https://www.istockphoto.com/legal/license-agreement"
    assert istock["license"]["creators"] == ["K_Thalhofer"]
    assert istock["license"]["copyright"] == "©iStock, credit: K_Thalhofer"
    assert istock["credits"]["credit_line"] == "Getty Images"
    assert sum(1 for i in page1["images"] if i["is_licensable"]) == 7
    assert sum(1 for i in page1["images"] if i["is_product"]) == 5
    assert sum(1 for i in page1["images"] if i["is_video"]) == 3


def test_identity_results_page_is_shorter():
    out = P.parse_search_page(load("pod_search_page1.html"))
    assert len(out["images"]) == 50
    assert out["images"][0]["id"] == AKC
    assert out["search_information"]["total_results"] == 114000000
    assert len(out["suggested_filters"]) == 5 and len(out["related_searches"]) == 6


def test_filtered_page_keeps_chips():
    out = P.parse_search_page(load("search_filtered.html"))
    assert len(out["images"]) == 100 and len(out["suggested_filters"]) == 5


def test_gibberish_query_still_answers_tiles():
    out = P.parse_search_page(load("search_no_results.html"))
    assert out["search_information"]["query"] == "asdkjqwhekjqhwekjh zzqxvbn plkmjn"
    assert out["search_information"]["total_results"] == 96
    assert len(out["images"]) == 57
    assert out["suggested_filters"] == [] and out["related_searches"] == []


def test_wall_and_sorry_parse_to_nothing():
    out = P.parse_search_page(load("wall.html"))
    assert out["images"] == [] and out["suggested_filters"] == []
    assert P.parse_fragment(load("sorry_async.html"))["images"] == []


# ---- scroll fragments ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,count", [("pod_fragment_start0.html", 100), ("pod_fragment_start10.html", 100),
                                        ("pod_fragment_start20.html", 97), ("pod_fragment_start30_empty.html", 0)])
def test_fragments(name, count):
    out = P.parse_fragment(load(name))
    assert len(out["images"]) == count
    assert all(i["link"] and i["page_id"] and i["title"] for i in out["images"])
    assert [i["position"] for i in out["images"]] == list(range(1, count + 1))


def test_fragment_offset():
    out = P.parse_fragment(load("pod_fragment_start10.html"), offset=100)
    assert out["images"][0]["position"] == 101


def test_start0_fragment_starts_like_the_page():
    page = P.parse_search_page(load("pod_search_page1.html"))["images"]
    frag = P.parse_fragment(load("pod_fragment_start0.html"))["images"]
    # same hundred, ranked slightly differently: the page's tiles are inside it
    assert len({i["id"] for i in page} & {i["id"] for i in frag}) >= 40
    assert len(frag) == 100


# ---- viewer -------------------------------------------------------------------------------------

def test_viewer_without_query():
    out = P.parse_viewer(load("pod_viewer.html"), AKC)
    assert out["image"] is None            # the opened image's own record is never in the viewer
    assert out["is_licensable"] is True
    assert out["related_token"] == "rimg:CY1EtMU_17pU_1YQyRBFw5Pz-44AIA"
    assert len(out["related_images"]) == 12
    first = out["related_images"][0]
    assert first["position"] == 1 and first["id"] == "qoWvBeV8chKT7M" and first["page_id"] == "Fv28Z4s9X-N_RM"
    assert first["link"] == "https://pupify.ca/wp-content/uploads/2026/04/Untitled-design-3-2.jpg"
    assert (first["width"], first["height"]) == (1500, 1000)
    assert first["source"]["name"] == "Pupify" and first["source"]["domain"] == "pupify.ca"
    assert AKC not in {i["id"] for i in out["related_images"]}


def test_viewer_with_query_same_shape():
    out = P.parse_viewer(load("viewer_with_query.html"), AKC)
    assert out["image"] is None and len(out["related_images"]) == 12 and out["related_token"]


def test_viewer_product_tile():
    out = P.parse_viewer(load("pod_viewer_product.html"), "KJlRJJt_Dm_trM")
    assert out["related_token"] == "rimg:CSiZUSSbfw5vYegh0irS-7tT4AIA"
    assert len(out["related_images"]) == 11
    # this picture is among its own related tiles (another page carries it)
    assert out["image"] and out["image"]["id"] == "KJlRJJt_Dm_trM"
    assert out["image"]["link"].startswith("https://images.photowall.com/")
    assert "position" not in out["image"]


@pytest.mark.parametrize("name", ["pod_viewer_unknown_id.html", "pod_viewer_no_page_id.html"])
def test_empty_viewers(name):
    raw = load(name)
    assert P.is_empty_viewer(raw)
    out = P.parse_viewer(raw, "zzzzzzzzzzzzzz")
    assert out == {"image": None, "is_licensable": False, "related_images": [], "related_token": None}


def test_viewer_is_not_empty_when_it_has_tiles():
    assert not P.is_empty_viewer(load("pod_viewer.html"))


# ---- the image's own page (/imgres permalink) ------------------------------------------------------

def test_permalink_page_carries_the_record():
    out = P.parse_viewer(load("pod_permalink_page.html"), AKC)
    rec = out["image"]
    assert rec["id"] == AKC and rec["page_id"] == AKC_PAGE
    assert rec["title"] == "How to Train a Golden Retriever Puppy: Growth & Training Timeline"
    assert rec["link"].startswith("https://s3.amazonaws.com/cdn-origin-etr.akc.org/")
    assert (rec["width"], rec["height"]) == (729, 486) and rec["file_size"] == "190KB"
    assert rec["source"]["domain"] == "www.akc.org" and rec["source"]["name"] == "American Kennel Club"
    assert "position" not in rec
    assert len(out["related_images"]) == 12 and AKC not in {i["id"] for i in out["related_images"]}
    assert out["related_token"].startswith("rimg:")


def test_permalink_page_for_an_unknown_id_is_empty():
    out = P.parse_viewer(load("pod_permalink_unknown_id.html"), "zzzzzzzzzzzzzz")
    assert out["image"] is None and out["related_images"] == []


# ---- related images ------------------------------------------------------------------------------

def test_related_page_and_fragments():
    out = P.parse_search_page(load("pod_related_page1.html"))
    assert len(out["images"]) == 100
    assert out["search_information"] == {"query": None, "total_results": 0}
    assert out["suggested_filters"] == [] and out["related_searches"] == []
    assert sum(1 for i in out["images"] if i["is_licensable"]) == 20
    assert len(P.parse_fragment(load("pod_related_fragment_start10.html"))["images"]) == 100
    assert P.parse_fragment(load("pod_related_fragment_no_query_empty.html"))["images"] == []


# ---- suggestions ---------------------------------------------------------------------------------

def test_autocomplete():
    rows = P.parse_autocomplete(load("autocomplete_img.txt"))
    assert [r["text"] for r in rows][:3] == ["golden retriever", "golden retriever puppies", "golden retriever rescue"]
    assert rows[0] == {"position": 1, "text": "golden retriever", "subtypes": [512, 433]}
    assert P.parse_autocomplete(load("autocomplete_img_empty.txt")) == []
    assert P.parse_autocomplete("not json") == []


# ---- robustness ------------------------------------------------------------------------------------

def test_parse_tile_tolerates_sparse_entries():
    rec = P.parse_tile([0, "abcdefghijklmn"], 3)
    assert rec["id"] == "abcdefghijklmn" and rec["position"] == 3
    assert rec["link"] is None and rec["width"] is None and rec["thumbnail"] == {"link": None, "width": None, "height": None}
    assert rec["source"] == {"name": None, "domain": None, "page_link": None, "favicon": None}
    assert rec["google_link"] == "https://www.google.com/imgres?tbnid=abcdefghijklmn"
    assert P.parse_tile([0, "x", "junk", None, None, "no", 7, None, None, "not a dict"])["dominant_color"] is None
    assert P.parse_search_page("")["images"] == []
    assert P.parse_fragment(None)["images"] == []
    assert P.tile_entries("var m={broken") == {}


# ---- refs --------------------------------------------------------------------------------------------

def test_resolve_image_forms():
    assert refs.resolve_image(AKC) == {"id": AKC, "page_id": None, "link": None, "page_link": None}
    link = refs.google_link(AKC, AKC_PAGE, "https://x.test/a b.jpg", "https://x.test/page")
    assert refs.resolve_image(link) == {"id": AKC, "page_id": AKC_PAGE, "link": "https://x.test/a b.jpg",
                                        "page_link": "https://x.test/page"}
    assert refs.resolve_image("https://www.google.com/search?udm=2&q=x&tbnid=" + AKC)["id"] == AKC
    assert refs.resolve_image("https://www.google.com/async/imgv?tbnid=%s&imgdii=%s&docid=%s" % (AKC, AKC, AKC_PAGE))["page_id"] == AKC_PAGE
    assert refs.resolve_image("google.co.uk/imgres?tbnid=" + AKC)["id"] == AKC


@pytest.mark.parametrize("value", ["", "x", "https://example.com/a.jpg", "https://www.google.com/search?q=puppy",
                                   "https://www.google.com/imgres?tbnid=bad!id"])
def test_resolve_image_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_image(value)


def test_resolve_query_and_links():
    assert refs.resolve_query("https://www.google.com/search?q=red+fox&udm=2&hl=fr&gl=fr") == "red fox"
    assert refs.link_params("https://www.google.com/search?q=red+fox&udm=2&hl=fr&gl=fr&safe=active") == \
        {"gl": "fr", "hl": "fr", "safe": "active"}
    assert refs.link_params("red fox") == {}
    assert refs.images_link("red fox", "FR", "fr", start=10) == "https://www.google.com/search?q=red+fox&udm=2&hl=fr&gl=fr&start=10"
    assert refs.images_link_tbs("rimg:abc", "US", "en") == "https://www.google.com/search?udm=2&tbs=rimg%3Aabc&hl=en&gl=us"
    with pytest.raises(ValueError):
        refs.resolve_query("https://example.com/?q=x")
