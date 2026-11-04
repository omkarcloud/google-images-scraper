# 🖼️ Google Images Scraper

Google Images Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Google Images data for free.

## ✨ What Can I Get?

- 🖼️ **300 images per search** — full-size links, width & height, file size, source page & site
- 🎛️ **Every Google Images filter** — size, colour, type, aspect ratio, file type, usage rights, time & site
- 🏷️ **Licences, credits & product prices** — stock-photo licences, photographer credits, shop prices & sellers
- 🔁 **Related & reverse image search** — 300 look-alike images per image, plus every page carrying a picture

## 🎥 Example: A Full Google Images Search

```json
{
  "search_information": { "query": "golden retriever puppy", "total_results": 114000000 },
  "images": [
    {
      "position": 1,
      "id": "eYoKU9jW-eRT6M",
      "title": "Golden Retriever: Pros, Cons & Diet Guide | Ollie",
      "link": "https://blog.ollie.com/wp-content/uploads/250506_Livingroom_SHOT-10_0173_FR-scaled.jpg",
      "width": 2560,
      "height": 1707,
      "file_size": "522KB",
      "format": "jpg",
      "source": { "name": "Ollie Blog", "domain": "blog.ollie.com", "page_link": "https://blog.ollie.com/breed-deets-golden-retriever/" }
    },
    {
      "position": 22,
      "id": "32eplErtBrE7rM",
      "title": "Cuddly Golden Retriever Puppies Are the Cutest Thing You'll See Today - A-Z Animals",
      "link": "https://a-z-animals.com/media/2025/10/shutterstock-2300276251-medium-licensed.jpg",
      "width": 1000,
      "height": 667,
      "is_licensable": true,
      "credits": { "credit_line": "Shutterstock", "creators": ["ConstanzaMartinez"] },
      "license": { "provider": "shutterstock.com", "details_link": "https://www.shutterstock.com/image-photo/2300276251?utm_source=iptc&utm_medium=googleimages&utm_campaign=image" }
    }
  ],
  "suggested_filters": [{ "text": "Newborn", "query": "newborn golden retriever puppy" }],
  "related_searches": [{ "query": "chocolate golden retriever puppy" }]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Google Images Data — Get It in 60 Seconds

1️⃣ Clone and install (the last command downloads Camoufox, the hardened Firefox that opens Google for you):
```bash
git clone https://github.com/omkarcloud/google-images-scraper
cd google-images-scraper
python -m pip install -r requirements.txt
python -m camoufox fetch
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/images/search?query=golden+retriever+puppy"
```

```json
{
  "count": 114000000,
  "per_page": 100,
  "current_page": 1,
  "next": "http://localhost:8000/images/search?query=golden+retriever+puppy&page=2",
  "search_information": { "query": "golden retriever puppy", "total_results": 114000000 },
  "images": [
    {
      "position": 1,
      "id": "jUS0xT_ulT-SUM",
      "title": "How to Train a Golden Retriever Puppy: Growth & Training Timeline",
      "link": "https://s3.amazonaws.com/cdn-origin-etr.akc.org/wp-content/uploads/2020/07/09151754/Golden-Retriever-puppy-standing-outdoors.jpg",
      "width": 729,
      "height": 486,
      "file_size": "190KB",
      "format": "jpg",
      "source": { "name": "American Kennel Club", "domain": "www.akc.org", "page_link": "https://www.akc.org/expert-advice/dog-breeds/golden-retriever-puppy-training-timeline/" }
    }
  ]
}
```

All 5 endpoints are now live at `http://localhost:8000`.

The first search can take a minute while a browser opens Google and clears its checks; after that, each call takes a few seconds. Autocomplete needs no browser and answers in a blink.

### 🔓 Google Showing a Captcha?

Google often answers a fresh browser with an "unusual traffic" captcha. The scraper first tries on its own — no key, no cost — and when Google insists, it tells you so. Then:

1. Get a [CapSolver](https://dashboard.capsolver.com/passport/register?inviteCode=lvdYBC4sYKRm) API key (one captcha is solved per ~30 calls).
2. Start the API with it:
   ```bash
   CAPSOLVER_API_KEY=CAP-... python run.py
   ```

Google pauses one IP after a few dozen searches, so for real volume add a sticky proxy too (`{session}` gets a fresh id for every browser session):

```bash
GOOGLE_IMAGES_PROXY="http://user-session-{session}:pass@host:port" CAPSOLVER_API_KEY=CAP-... python run.py
```

## 📚 Endpoints

5 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Search Images | `/images/search` | 100 images per page with full-size links, sources, licences & prices |
| Autocomplete | `/images/autocomplete` | Search suggestions, exactly as Google's search box shows them |
| Image Details | `/images/details` | Everything about one image, plus 12 related images |
| Related Images | `/images/related` | 100 visually similar images per page |
| Reverse Image Search | `/images/reverse-search` | Every page carrying a picture, or look-alike images |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-google-images-scraper-free-200-calls/pricing) — 200 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-google-images-scraper-free-200-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-google-images-scraper-free-200-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/images/search",
    params={"query": "golden retriever puppy", "size": "large", "usage_rights": "creative_commons"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Google Images Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/google-images-scraper-github-whatsapp)

[![Ask Us by Email about Google Images Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Google%20Images%20Scraper%20API&body=I%20need%20help%20using%20the%20Google%20Images%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/google-images-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/google-images-scraper)
