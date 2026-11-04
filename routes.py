"""The 5 Google Images endpoints. Every path is served with and without the
`/google-images` prefix, so code generated against the hosted API on
RapidAPI (paths like /images/search) runs unchanged against this server.

Params are validated by the marshmallow schemas in google_images/schemas.py
(the same ones the hosted API uses); failures map to HTTP like this:
bad params -> 400, not found -> 404, Google blocked / upstream error -> 502,
anything else -> 500. Paged endpoints (search, related) answer the hosted
API's shape: count / per_page / current_page / total_pages / next / previous
plus the results.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from google_images import api, schemas
from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "google-images"
PREFIX = "/google-images"

# (public path, schema, function, paginated) — in the order of the docs
ENDPOINTS = [
    ("/images/search", schemas.ImagesSearchSchema, api.images_search, True),
    ("/images/autocomplete", schemas.AutocompleteSchema, api.autocomplete, False),
    ("/images/details", schemas.ImageSchema, api.image_details, False),
    ("/images/related", schemas.RelatedImagesSchema, api.related_images, True),
    ("/images/reverse-search", schemas.ReverseSearchSchema, api.reverse_search, False),
]


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Amélie" would arrive as "AmÃ©lie")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    host = request.headers.get("Host") or "localhost"
    return f"{request.urlparts.scheme}://{host}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the `pagination` block into count / per_page / current_page /
    total_pages / next / previous, like the hosted API. Google publishes no
    page count, so `has_next` drives the next link and total_pages is null."""
    result = dict(result)
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)   # per-page count; `count` is the total, like the hosted API
    page = _as_int(pagination.get("page")) or _as_int(params.get("page")) or 1
    if "has_next" in pagination:
        has_next = bool(pagination["has_next"])
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            total_pages = _as_int(total_pages, None)
    else:
        total_pages = max(_as_int(pagination.get("total_pages")), 0)
        has_next = page < total_pages
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if has_next else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def handle(path, schema_cls, impl, paginated):
    label = f"{SITE} {path.strip('/')}"
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"{SITE} rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"{SITE} blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"{label} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"{label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, raw)
    return json_response(result)


def mount(path, schema_cls, impl, paginated):
    """Serve one endpoint at /path and /google-images/path."""
    def handler():
        return handle(path, schema_cls, impl, paginated)

    handler.__name__ = "google_images_" + path.strip("/").replace("/", "_").replace("-", "_")
    for p in (path, PREFIX + path):
        route(p, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/")
@route("/health")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
