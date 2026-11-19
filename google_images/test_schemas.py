"""Offline tests for the /google-images/* request schemas.

    cd scrapers && python -m pytest google_images/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_images import refs, schemas  # noqa: E402

AKC = "jUS0xT_ulT-SUM"
AKC_PAGE = "DJEEXDk_P7gPSM"


def _errors(schema, data):
    with pytest.raises(ValidationError) as e:
        schema().load(data)
    return e.value.normalized_messages()


def test_search_defaults_and_filters():
    loaded = schemas.ImagesSearchSchema().load({"query": " red fox ", "type": "Photo", "color": "RED", "page": "2",
                                                "size": "large", "aspect_ratio": "wide", "file_type": "png",
                                                "usage_rights": "creative_commons", "time_period": "month",
                                                "safe": "active", "site": "nasa.gov"})
    assert loaded == {"query": "red fox", "country": "US", "language": "en", "location": None, "page": 2,
                      "size": "large", "color": "red", "image_type": "photo", "aspect_ratio": "wide",
                      "file_type": "png", "usage_rights": "creative_commons", "time_period": "month",
                      "safe": "active", "site": "nasa.gov"}
    minimal = schemas.ImagesSearchSchema().load({"query": "x"})
    assert minimal["page"] == 1 and minimal["country"] == "US" and minimal["size"] is None


def test_search_accepts_a_google_images_link():
    loaded = schemas.ImagesSearchSchema().load(
        {"query": "https://www.google.com/search?q=golden+retriever+puppy&udm=2&hl=de&gl=de&safe=active"})
    assert loaded["query"] == "golden retriever puppy"
    assert loaded["country"] == "DE" and loaded["language"] == "de" and loaded["safe"] == "active"
    explicit = schemas.ImagesSearchSchema().load(
        {"query": "https://www.google.com/search?q=x&udm=2&hl=de&gl=de", "country": "fr", "language": "en"})
    assert explicit["country"] == "FR" and explicit["language"] == "en"


@pytest.mark.parametrize("data,field", [
    ({}, "query"),
    ({"query": ""}, "query"),
    ({"query": "https://example.com/?q=x"}, "query"),
    ({"query": "x", "page": 4}, "page"),
    ({"query": "x", "page": 0}, "page"),
    ({"query": "x", "size": "huge"}, "size"),
    ({"query": "x", "type": "meme"}, "type"),
    ({"query": "x", "country": "usa"}, "country"),
    ({"query": "x", "language": "english"}, "language"),
    ({"query": "x", "url": "y"}, "url"),
    ({"query": "x", "q": "y"}, "q"),
])
def test_search_rejects(data, field):
    assert field in _errors(schemas.ImagesSearchSchema, data)


def test_search_rejection_messages_name_the_choices():
    errors = _errors(schemas.ImagesSearchSchema, {"query": "x", "size": "huge"})
    assert errors["size"] == ["Must be one of: any, large, medium, icon."]
    assert _errors(schemas.ImagesSearchSchema, {"query": "x", "page": 9})["page"] == \
        ["Must be greater than or equal to 1 and less than or equal to 3."]


def test_image_schema_accepts_id_and_links():
    assert schemas.ImageSchema().load({"image": AKC}) == \
        {"country": "US", "language": "en", "image": {"id": AKC, "page_id": None, "link": None, "page_link": None}}
    link = refs.google_link(AKC, AKC_PAGE, "https://x.test/a.jpg", "https://x.test/p")
    loaded = schemas.ImageSchema().load({"image": link, "country": "uk", "language": "fr"})
    assert loaded["image"] == {"id": AKC, "page_id": AKC_PAGE, "link": "https://x.test/a.jpg", "page_link": "https://x.test/p"}
    assert loaded["country"] == "GB" and loaded["language"] == "fr"


@pytest.mark.parametrize("value,fragment", [
    ("", "empty"),
    ("x", "Google image id"),
    ("https://example.com/a.jpg", "tbnid="),
    ("https://www.google.com/search?q=puppy&udm=2", "tbnid="),
])
def test_image_schema_rejects(value, fragment):
    errors = _errors(schemas.ImageSchema, {"image": value})
    assert fragment in errors["image"][0]


def test_image_schema_rejects_sibling_params():
    assert "id" in _errors(schemas.ImageSchema, {"image": AKC, "id": AKC})
    assert "url" in _errors(schemas.ImageSchema, {"image": AKC, "url": "https://x"})


def test_related_schema():
    loaded = schemas.RelatedImagesSchema().load({"image": AKC, "page": "3", "query": "golden retriever", "safe": "off"})
    assert loaded["page"] == 3 and loaded["query"] == "golden retriever" and loaded["safe"] == "off"
    assert schemas.RelatedImagesSchema().load({"image": AKC})["query"] is None
    assert "page" in _errors(schemas.RelatedImagesSchema, {"image": AKC, "page": 4})


def test_autocomplete_schema():
    assert schemas.AutocompleteSchema().load({"query": "golden retr"}) == \
        {"query": "golden retr", "country": "US", "language": "en", "limit": 10}
    assert "limit" in _errors(schemas.AutocompleteSchema, {"query": "x", "limit": 21})
    assert "query" in _errors(schemas.AutocompleteSchema, {})


def test_reverse_search_schema():
    loaded = schemas.ReverseSearchSchema().load({"image": "https://example.com/a.jpg", "match": "Visual"})
    assert loaded["image"] == {"link": "https://example.com/a.jpg"} and loaded["match"] == "visual"
    assert schemas.ReverseSearchSchema().load({"image": "https://example.com/a.jpg"})["match"] == "exact"
    assert "match" in _errors(schemas.ReverseSearchSchema, {"image": "https://example.com/a.jpg", "match": "fuzzy"})
    assert "image" in _errors(schemas.ReverseSearchSchema, {"image": "not a link"})


def test_every_field_has_a_description():
    for name, schema in (("search", schemas.ImagesSearchSchema), ("image", schemas.ImageSchema),
                         ("related", schemas.RelatedImagesSchema), ("autocomplete", schemas.AutocompleteSchema),
                         ("reverse", schemas.ReverseSearchSchema)):
        missing = [f for f, field in schema().fields.items() if not field.metadata.get("description")]
        assert not missing, f"{name}: fields without a description: {missing}"


# ---- empty params (a form that sends every field) --------------------------------------------------

from schema_fields import load_query  # noqa: E402

VALID = {"query": "red fox", "image": AKC}
ALL = [schemas.ImagesSearchSchema, schemas.ImageSchema, schemas.RelatedImagesSchema, schemas.AutocompleteSchema,
       schemas.ReverseSearchSchema]


@pytest.mark.parametrize("schema_cls", ALL, ids=lambda c: c.__name__)
def test_an_empty_optional_param_is_the_absent_param(schema_cls):
    fields = {field.data_key or name: field for name, field in schema_cls().fields.items()}
    base = {key: ("https://example.com/a.jpg" if schema_cls is schemas.ReverseSearchSchema else VALID[key])
            for key, field in fields.items() if field.required}
    expected, error = load_query(schema_cls, base)
    assert error is None
    for key, field in fields.items():
        data, error = load_query(schema_cls, dict(base, **{key: ""}))      # raises (= bottle 500) on a crash
        if field.required:
            assert data is None and key in error["errors"]
        else:
            assert error is None and data == expected, key
    everything = {key: "  " for key in fields if key not in base}
    assert load_query(schema_cls, dict(base, **everything)) == (expected, None)


def test_the_requests_that_were_a_500():
    # 2026-11-19 08:0x UTC, a support test of /images/search with every field sent
    data, error = load_query(schemas.ImagesSearchSchema, {"query": "red fox", "location": "", "country": "", "page": ""})
    assert error is None and (data["location"], data["country"], data["page"]) == (None, "US", 1)
    data, error = load_query(schemas.RelatedImagesSchema, {"image": AKC, "query": "", "page": ""})
    assert error is None and data["query"] is None and data["page"] == 1
    assert load_query(schemas.ReverseSearchSchema, {"image": "https://example.com/a.jpg", "match": ""})[0]["match"] == "exact"
    # a filled value is still checked
    assert "location" in load_query(schemas.ImagesSearchSchema, {"query": "x", "location": "y" * 64})[1]["errors"]
    assert "page" in load_query(schemas.ImagesSearchSchema, {"query": "x", "page": "abc"})[1]["errors"]

