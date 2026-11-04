"""Cache TTL per /google-images/* endpoint (cache.py, keyed on the
validated params). Every identity-backed page costs a slice of a minted
identity (~40 requests each, a 1-3 minute Camoufox mint on the box), so
results pages cache for hours; image rankings move slowly."""
from datetime import timedelta

# One results page (100 images): the ranking of an image query moves over
# days, not hours — same as /google-search/images.
SEARCH_CACHE = timedelta(hours=12)
# The viewer of one image (its record, licence, product, 12 related, the
# related-images token): the image itself does not change; shared by
# images/details and images/related (api._viewer_record).
VIEWER_CACHE = timedelta(hours=24)
# The image's own Google page (images/details: record + 12 related + token):
# the image itself does not change.
PERMALINK_CACHE = timedelta(hours=24)
# A page of visually related images: as stable as the viewer.
RELATED_CACHE = timedelta(hours=24)
# Suggestions are open-surface and cheap, but they also barely move.
AUTOCOMPLETE_CACHE = timedelta(hours=12)
# A Lens reverse search costs an upload + an identity use; the set of
# pages carrying a picture moves slowly.
REVERSE_SEARCH_CACHE = timedelta(hours=12)
