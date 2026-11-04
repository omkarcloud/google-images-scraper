"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does (minus the next/previous
page links); results are written to output/*.json. See README.md for every
endpoint.
"""
import json
import os

from google_images import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # 100 images: full-size link, size, source page, licence and product prices
    results = api.images_search(**schemas.ImagesSearchSchema().load({"query": "golden retriever puppy"}))
    save("search_golden_retriever_puppy.json", results)

    # everything about the first image, plus 12 related images (its google_link works everywhere)
    first = results["images"][0]["google_link"]
    save("details_first_image.json", api.image_details(**schemas.ImageSchema().load({"image": first})))

    # suggestions, exactly as the search box shows them (plain HTTP, no browser)
    save("autocomplete_golden_retr.json", api.autocomplete(**schemas.AutocompleteSchema().load({"query": "golden retr"})))
