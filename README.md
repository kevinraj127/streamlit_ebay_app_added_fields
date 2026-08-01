# eBay Deal Check

**Price intel for eBay resellers and power buyers.**

A Streamlit app that answers one question before you buy anything on eBay:
**"What's the most I should pay for this?"**

Search live listings, analyze a single item or an entire lot, and get a data-driven
read on whether it's a good deal — backed by real active listings, not gut feel.

**Who this is for:**
- **Resellers** sourcing lots — get a fee-aware BUY/PASS call before you commit
- **Power buyers & lot buyers** — price-check a listing or lot before you bid, even if you're not reselling anything

> Uses the eBay Browse API. Not affiliated with or endorsed by eBay Inc.

---

## Features

### 🔍 Search Listings — item lookup & market browsing
This is the tab to reach for when you just want to see what's out there for a specific
title, or browse a whole category — no profit math attached.

- **Item lookup** — type a specific title into the search box to pull retrieve current
  active listings for that exact item: prices, condition, listing type, and seller info, so you
  can eyeball the market before deciding whether it's even worth running the numbers
- Live eBay search by category, listing type (Auction / Fixed Price / Best Offer), and max price
- Seller filtering by feedback rating (Elite, Excellent, Very Good, Good, Inexperienced) and
  optional charity/thrift-store seller detection (Goodwill, Salvation Army, Habitat for
  Humanity, St. Vincent de Paul, Catholic Charities, and more)
- Price analytics: average/median price and automatic "best deals" surfacing (listings
  15%+ below average)
- Save and reload searches from the sidebar
- Export results to CSV

### 📦 Lot Analysis
Answers the sourcing question directly — for a single title or a whole lot at once.
Unlike Search Listings, this tab takes your acquisition cost as an input and runs the
full fee-and-margin math to give you a BUY/PASS call, rather than just showing you raw
market listings.

- **Single Title** — enter a title and your acquisition cost, get an instant profit/margin
  breakdown against real market comps
- **CSV Upload (Lot)** — upload a lot of titles and choose:
  - **Fixed price mode** — you already know the asking price; splits it evenly across all
    titles and shows per-title profit
  - **Derived mode** — don't know a price yet; the app calculates the **maximum you should
    pay** for the whole lot to hit your target margin
- Every title gets a ✅ WINNER / ❌ DUD decision, plus links to the actual comparable
  listings used to price it
- Full lot summary: total acquisition cost, total profit, blended margin, and a final
  BUY LOT / PASS ON LOT call

---

## ⚠️ Important: this prices off active listings, not sold comps

**eBay's Browse API only returns active (currently listed) items — there is no public
API for sold/completed listings.** The "equilibrium price" this app calculates is the
median of the 5 lowest *current asking prices* for comparable items, not what those
items actually sold for.

What this means in practice:
- It tells you what you're **competing against** in the market right now, not a
  guaranteed sale price
- Asking prices run higher than sold prices on average (sellers list optimistically;
  many items sell below list or via offers)
- Use the equilibrium price as a **conservative ceiling for your BUY/PASS decision**,
  not as a promise of what you'll actually collect — build in your own margin buffer
  beyond the app's target margin if you want additional safety
- Periodically spot-check equilibrium prices against eBay's own "sold listings" filter
  (visible when browsing eBay.com directly, though not available via this API) to
  calibrate how far off active-vs-sold tends to run in your categories

This is a fundamental limitation of eBay's public API, not something this app can work
around — no third-party tool has legitimate access to eBay's sold-comp data at scale.

---

## How the pricing logic works

**Equilibrium price** — for each title, the app pulls used/pre-owned listings from eBay's
Browse API, takes the 5 lowest prices found, and uses the median of that bottom-5 as the
"equilibrium price." This avoids being skewed by outlier high asks and reflects what an
item will realistically sell for if you're pricing competitively.

**Fee-aware profit math** — every calculation accounts for:
| Cost | Rate |
|---|---|
| Final Value Fee (media categories*) | 15.3% |
| Final Value Fee (all other categories, incl. Video Games & Vinyl Records) | 13.6% |
| Promoted Listings | +2.0% |
| Sales tax gross-up | 8.25% (added to fee basis) |
| Per-transaction fee | $0.40 |
| Packaging cost | $0.35 |
| Shipping — Video Games & Consoles | $5.97 |
| Shipping — Media Mail eligible† | $4.39 |
| Shipping — everything else | $6.50 flat |

\* *Media FVF categories: Books, DVD & Blu-ray, Music CDs, Music Cassettes, Manga*

† *Media Mail eligible categories: Books, DVD & Blu-ray, Music CDs, Music Cassettes,
Manga, VHS Tapes, Vinyl Records*

Note: Vinyl Records uses the 13.6% (non-media) FVF rate but the $4.39 Media Mail
shipping cost, since vinyl is Media Mail eligible despite not falling under eBay's
discounted media FVF category. All non-media, non-video-game categories (Action
Figures, Collectible Figures & Bobbleheads, Fragrances, Furniture, Hats, Headphones,
Men's Clothing, Men's Shoes, Sporting Goods) use a flat $6.00 shipping estimate.

**Max acquisition price** — for "derived" mode, the app works backward from the
equilibrium price and your target margin to tell you the most you can pay and still hit
that margin after all fees.

---

## Categories supported

Action Figures & Accessories · Books · Collectible Figures & Bobbleheads · DVD & Blu-ray ·
Fragrances · Furniture · Hats · Headphones · Manga · Men's Clothing · Men's Shoes ·
Music CDs · Music Cassettes · Sporting Goods · VHS Tapes · Video Games & Consoles ·
Vinyl Records

---

## Getting Started

### Option 1: Deploy your own copy (recommended, no local setup)

1. **Fork this repo** (button in the top right of the GitHub page)
2. Go to [Streamlit Community Cloud](https://streamlit.io/cloud) and sign in with GitHub
3. Click **New app**, select your forked repo, and set the main file to
   `ebay_added_fields_github.py`
4. Before/after deploying, add your eBay API credentials as a secret (see below)
5. Deploy — your app will be live at `your-app-name.streamlit.app`

### eBay API credentials (required)

You'll need your own eBay Developer credentials:

1. Register for a free account at the [eBay Developers Program](https://developer.ebay.com)
2. Create an application to get a **Client ID** and **Client Secret**
   (production keys, not sandbox, for real listing data)
3. In Streamlit Cloud, go to your app → **Settings → Secrets** and add:

```toml
[ebay]
CLIENT_ID = "your-client-id-here"
CLIENT_SECRET = "your-client-secret-here"
```

That's the only secret the app needs.

### Option 2: Run locally

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-FORK.git
cd YOUR-FORK
pip install -r requirements.txt
```

Create a `.streamlit/secrets.toml` file in the project root with the same `[ebay]`
block shown above, then run:

```bash
streamlit run ebay_added_fields_github.py
```

---

## CSV format for lot uploads

Only two columns are needed — `title` and `category`:

```csv
title,category
Die Hard,DVD & Blu-ray
Halo 3,Video Games & Consoles
Nirvana Nevermind,Music CDs
```

A sample CSV is also downloadable directly from within the app.

---

## Requirements

- Python 3.9+
- `streamlit`, `pandas`, `requests`, `plotly`, `pytz` (see `requirements.txt`)

---

## Notes

- This tool uses the eBay Browse API (read-only, public **active** listing data) — it
  does not place bids, create listings, or take any action on your behalf. See the
  callout above regarding active listings vs. sold comps.
- Pricing/margin figures assume US eBay fee rates and are provided for decision support,
  not guaranteed accuracy — always sanity-check against current eBay fee schedules.
- Each user runs the app with their own eBay API credentials; no data is shared between
  users or sent anywhere besides eBay's own API.

## License

*(Add a license of your choice — MIT is a common permissive option for tools like this.)*
