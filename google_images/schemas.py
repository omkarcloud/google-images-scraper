"""Marshmallow request schemas for every /google-images/* route.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair, google_images/refs.py):

    query    a search term OR a Google Images link (its q is the term; a
             pasted link also fills country / language / filters when the
             matching params are absent)
    image    a Google image id (jUS0xT_ulT-SUM) OR the image's Google
             Images link (the /imgres permalink every record carries as
             `google_link`, a results link with tbnid=, a viewer link)

The filter choices are Google's own Tools-menu values, shared with
/google-search/images (google_search/serp.py tables).
"""
from marshmallow import pre_load

from google_images import fetch, refs
from google_lens.schemas import ImageField as LensImageField
from google_search import serp
from google_search.schemas import CountryField, LanguageField, LocationField
from schema_fields import BaseSchema, ChoiceField, LimitField, PageField, QueryField, RefField, StrippedString


class ImagesQueryField(RefField):
    resolver = staticmethod(refs.resolve_query)


class ImageRefField(RefField):
    resolver = staticmethod(refs.resolve_image)


class _Localized(BaseSchema):
    country = CountryField(metadata={"description": "Google country (gl), ISO-2; default US"})
    language = LanguageField(metadata={"description": "interface language (hl), ISO 639-1; default en"})

    @pre_load
    def empty_is_absent(self, data, **kwargs):
        """An optional param sent empty (`location=`, `page=`, `country=`: a
        form that sends every field) is the absent param. Left in, the
        fields hand their validators None (`location=` and related's
        `query=` were a 500, len(None)), `page=` / `limit=` were refused as
        "not a valid integer", and `country=` / `language=` / `match=` lost
        their defaults. A required param sent empty is still refused."""
        required = {field.data_key or name for name, field in self.fields.items() if field.required}
        return {key: value for key, value in data.items()
                if key in required or not (isinstance(value, str) and not value.strip())}


class ImagesSearchSchema(_Localized):
    query = ImagesQueryField(metadata={"description": "search term, or a Google Images link (google.com/search?q=…&udm=2)"})
    location = LocationField(metadata={"description": "search from this place: a Google Ads canonical name like 'Austin,Texas,United States'"})
    page = PageField(max_page=fetch.MAX_PAGES, metadata={"description": f"results page, up to 100 images each; Google serves at most {fetch.MAX_PAGES} pages"})
    size = ChoiceField(list(serp.IMAGE_SIZES), metadata={"description": "image size: large, medium, icon"})
    color = ChoiceField(list(serp.IMAGE_COLORS), metadata={"description": "colour: color, grayscale, transparent, or a named colour (red, blue, …)"})
    image_type = ChoiceField(list(serp.IMAGE_TYPES), data_key="type", metadata={"description": "image type: face, photo, clipart, lineart, animated"})
    aspect_ratio = ChoiceField(list(serp.IMAGE_ASPECTS), metadata={"description": "aspect ratio: tall, square, wide, panoramic"})
    file_type = ChoiceField(list(serp.IMAGE_FORMATS), metadata={"description": "file type: jpg, gif, png, bmp, svg, webp, ico, raw"})
    usage_rights = ChoiceField(list(serp.IMAGE_RIGHTS), metadata={"description": "usage rights: creative_commons, commercial"})
    time_period = ChoiceField(list(serp.TIME_PERIODS), metadata={"description": "published within: hour, day, week, month, year"})
    safe = ChoiceField(list(serp.SAFE), metadata={"description": "SafeSearch: off, moderate, active"})
    site = StrippedString(required=False, load_default=None, metadata={"description": "only images from this site (a domain like nasa.gov)"})

    @pre_load
    def from_link(self, data, **kwargs):
        """A pasted Google Images link fills country / language / safe when
        the params are absent (its tbs filters are kept as given)."""
        params = refs.link_params(data.get("query") or "")
        if not params:
            return data
        data = dict(data)
        if params.get("gl") and not data.get("country"):
            data["country"] = params["gl"]
        if params.get("hl") and not data.get("language"):
            data["language"] = params["hl"].split("-")[0]
        if params.get("safe") and not data.get("safe"):
            data["safe"] = {"images": "moderate"}.get(params["safe"], params["safe"])
        return data


class ImageSchema(_Localized):
    image = ImageRefField(metadata={"description": "Google image id (jUS0xT_ulT-SUM) or the image's Google Images link (the record's google_link)"})


class RelatedImagesSchema(_Localized):
    image = ImageRefField(metadata={"description": "Google image id or the image's Google Images link (the record's google_link)"})
    page = PageField(max_page=fetch.MAX_PAGES, metadata={"description": f"page of related images, up to 100 each; at most {fetch.MAX_PAGES} pages (pages past the first need query)"})
    query = QueryField(required=False, load_default=None, metadata={"description": "the search the image was found in; Google needs it for pages past the first"})
    safe = ChoiceField(list(serp.SAFE), metadata={"description": "SafeSearch: off, moderate, active"})


class AutocompleteSchema(_Localized):
    query = QueryField(max_length=100, metadata={"description": "partial search term to complete"})
    limit = LimitField(default=10, max_size=20, metadata={"description": "suggestions to return, at most 20"})


class ReverseSearchSchema(_Localized):
    image = LensImageField(metadata={"description": "the picture: a direct image link, a web page link (its og:image is used), a Google Images link, or a data:image/…;base64 URI"})
    match = ChoiceField(["exact", "visual"], load_default="exact",
                        metadata={"description": "exact = pages carrying this exact picture (reverse image search); visual = visually similar images"})
