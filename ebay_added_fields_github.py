import streamlit as st
import requests
import pandas as pd
import datetime
import pytz
from base64 import b64encode
import warnings

# Initialize session state
if 'saved_searches' not in st.session_state:
    st.session_state.saved_searches = []

# eBay API credentials
CLIENT_ID = st.secrets["ebay"]["CLIENT_ID"]
CLIENT_SECRET = st.secrets["ebay"]["CLIENT_SECRET"]

credentials = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

@st.cache_data(ttl=3600)
def get_access_token():
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {credentials}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    response = requests.post(token_url, headers=headers, data=data)
    return response.json().get("access_token")

access_token = get_access_token()

# ============================================================
# HELPERS
# ============================================================

def categorize_seller(feedback_score, feedback_percent):
    try:
        score = int(feedback_score) if feedback_score is not None else 0
        percent = float(feedback_percent) if feedback_percent is not None else 0
    except (ValueError, TypeError):
        return "Uncategorized"
    if score >= 5000 and percent >= 99:
        return "Elite"
    elif score >= 1000 and percent >= 98:
        return "Excellent"
    elif score >= 500 and percent >= 97:
        return "Very Good"
    elif score >= 100 and percent >= 95:
        return "Good"
    elif score >= 100 and percent >= 90:
        return "Average"
    elif score < 100 and percent >= 90:
        return "Inexperienced"
    elif percent < 90:
        return "Low Rated"
    else:
        return "Uncategorized"

def is_charity_seller(seller_username):
    if not seller_username:
        return False
    seller_lower = seller_username.lower()
    charity_keywords = [
        "goodwill","shopsastores","salvationarmy","salvation_army","habitat",
        "habitatrestore","habitatforhumanity","faith_resale_online","vaporthriftonline",
        "nonprofit","svdp","stvincentdepaul","vincentdepaul","catholiccharities",
        "catholiccharity","oxfam","barnardos","britishheartfoundation","bhf",
        "redcross","charity","charities","thriftstoreusa","charitythrift","nonprofitstore"
    ]
    return any(keyword in seller_lower for keyword in charity_keywords)

def save_current_search(search_params):
    search_name = f"{search_params['search_term']} in {search_params['category']} (${search_params['max_price']})"
    existing_names = [s['name'] for s in st.session_state.saved_searches]
    if search_name not in existing_names:
        st.session_state.saved_searches.append({
            'name': search_name,
            'params': search_params,
            'saved_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        return True
    return False

def load_saved_search(search_params):
    for key, value in search_params.items():
        st.session_state[f"loaded_{key}"] = value

def delete_saved_search(index):
    if 0 <= index < len(st.session_state.saved_searches):
        del st.session_state.saved_searches[index]

def create_price_analytics(df):
    if df.empty:
        return
    col1, col2, col3, _ = st.columns(4)
    avg_price = df['price'].mean()
    with col1:
        st.metric("Average Price", f"${avg_price:.2f}")
    with col2:
        st.metric("Median Price", f"${df['price'].median():.2f}")
    with col3:
        deal_count = len(df[df['price'] < (avg_price * 0.85)])
        st.metric("Potential Deals", f"{deal_count} item(s)", help="Items priced 15% below average")
    st.subheader("🎯 Best Deals (15% below average)")
    deals = df[df['price'] < (avg_price * 0.85)]
    if not deals.empty:
        deals_display = deals.copy()
        deals_display['savings'] = deals_display['price'].apply(lambda p: f"${avg_price - p:.2f}")
        st.dataframe(
            deals_display[['listing', 'condition', 'price', 'savings', 'seller', 'seller_rating', 'seller_feedback', 'link']],
            column_config={
                "link": st.column_config.LinkColumn("Link", display_text="View Deal"),
                "price": st.column_config.NumberColumn("price", format="$%.2f")
            },
            use_container_width=True
        )
    else:
        st.info("No significant deals found in current results.")

# ============================================================
# CATEGORY & ASPECT MAPS
# ============================================================

category_options = {
    "All Categories": None,
    "Action Figures & Accessories": "246",
    "Books": "267",
    "DVD & Blu-ray": "617",
    "Fragrances": "180345",
    "Furniture": "3197",
    "Hats": "52365",
    "Headphones": "112529",
    "Manga": "33346",
    "Men's Clothing": "1059",
    "Men's Shoes": "93427",
    "Music CDs": "176984",
    "Music Cassettes": "176983",
    "Sporting Goods": "888",
    "Video Games & Consoles": "1249",
    "Vinyl Records": "176985"
}

aspect_map = {
    "Men's Shoes": ("US Shoe Size", "11")
}

# ============================================================
# LOT ANALYSIS — Fee constants & functions
# ============================================================

# Media (excl. video games & vinyl): 15.3% FVF
# Everything else (incl. video games & vinyl): 13.6% FVF
# All categories: +2% promoted listings
MEDIA_CATEGORIES_153 = {"Books", "DVD & Blu-ray", "Music CDs", "Music Cassettes", "Manga"}
PROMOTED_LISTINGS_FEE = 0.02
TAX_RATE = 0.0825
PER_TRANSACTION_FEE = 0.40
PACKAGING_COST = 0.35

VIDEO_GAME_CATEGORIES = {"Video Games & Consoles"}
SHIPPING_VIDEO_GAMES = 5.50
SHIPPING_MEDIA = 4.47

def get_shipping_cost(category):
    return SHIPPING_VIDEO_GAMES if category in VIDEO_GAME_CATEGORIES else SHIPPING_MEDIA

def get_combined_fee_rate(category):
    fvf = 0.153 if category in MEDIA_CATEGORIES_153 else 0.136
    return fvf + PROMOTED_LISTINGS_FEE

def calculate_profit(sale_price, acquisition_cost, margin_target, category="All Categories"):
    combined_fee_rate = get_combined_fee_rate(category)
    shipping = get_shipping_cost(category)
    tax_gross_up = sale_price * TAX_RATE
    fee_basis = sale_price + shipping + tax_gross_up
    total_fees = (fee_basis * combined_fee_rate) + PER_TRANSACTION_FEE + PACKAGING_COST
    net_profit = sale_price - total_fees - acquisition_cost
    margin = (net_profit / sale_price) * 100 if sale_price > 0 else 0
    return {
        "net_profit": round(net_profit, 2),
        "margin_pct": round(margin, 1),
        "total_fees": round(total_fees, 2),
        "meets_target": margin >= margin_target
    }

def get_equilibrium_price(title, category_id, bulk_max_price, bulk_limit, access_token, condition_ids="1000|1500|2000|2500|3000"):
    params = {
        "q": title,
        "filter": ",".join([
            f"price:[1..{bulk_max_price}]",
            "priceCurrency:USD",
            f"conditions:{{{condition_ids}}}"
        ]),
        "limit": bulk_limit
    }
    if category_id:
        params["category_ids"] = category_id
    headers_api = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        resp = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            params=params, headers=headers_api
        )
        prices = []
        if resp.status_code == 200:
            for item in resp.json().get("itemSummaries", []):
                if item.get("conditionId") == "7000":
                    continue
                price = float(item.get("price", {}).get("value", 0.0))
                if 1 <= price <= bulk_max_price:
                    prices.append(price)
        if not prices:
            return 0.0, 0
        prices_sorted = sorted(prices)
        bottom_5 = prices_sorted[:5]
        mid = len(bottom_5) // 2
        equilibrium = bottom_5[mid] if len(bottom_5) % 2 != 0 else (bottom_5[mid - 1] + bottom_5[mid]) / 2
        return round(equilibrium, 2), len(prices)
    except Exception:
        return 0.0, 0

def run_lot_analysis(titles_df, bulk_max_price, bulk_limit, margin_target, access_token, category_options, condition_ids="3000"):
    bulk_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    for i, row in titles_df.iterrows():
        title = str(row["title"]).strip()
        acquisition_cost = float(row["acquisition_cost"])
        row_category = str(row.get("category", "All Categories")).strip() if "category" in titles_df.columns else "All Categories"
        category_id = category_options.get(row_category, None)
        status_text.text(f"Searching {i+1}/{len(titles_df)}: {title}")
        progress_bar.progress((i + 1) / len(titles_df))
        equilibrium_price, listing_count = get_equilibrium_price(
            title, category_id, bulk_max_price, bulk_limit, access_token, condition_ids
        )
        profit_data = calculate_profit(equilibrium_price, acquisition_cost, margin_target, row_category) if equilibrium_price > 0 else {
            "net_profit": 0.0, "margin_pct": 0.0, "total_fees": 0.0, "meets_target": False
        }
        bulk_results.append({
            "title": title,
            "category": row_category,
            "acquisition_cost": acquisition_cost,
            "equilibrium_price": equilibrium_price,
            "listing_count": listing_count,
            "total_fees": profit_data["total_fees"],
            "net_profit": profit_data["net_profit"],
            "margin_pct": profit_data["margin_pct"],
            "decision": "✅ BUY" if profit_data["meets_target"] else "❌ PASS"
        })
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(bulk_results).sort_values("net_profit", ascending=False).reset_index(drop=True)

def display_lot_results(results_df, margin_target, is_lot=True):
    def color_decision(val):
        if "BUY" in str(val):
            return "background-color: #d4edda; color: #155724;"
        elif "PASS" in str(val):
            return "background-color: #f8d7da; color: #721c24;"
        return ""

    if is_lot:
        st.subheader("🎯 Lot Decision")
        buys = results_df[results_df["decision"] == "✅ BUY"]
        no_data = results_df[results_df["listing_count"] == 0]
        total_acquisition = results_df["acquisition_cost"].sum()
        total_revenue = buys["equilibrium_price"].sum()
        total_profit = buys["net_profit"].sum()
        lot_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        lot_decision = "✅ BUY LOT" if lot_margin >= margin_target else "❌ PASS ON LOT"
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("BUY titles", len(buys))
        col2.metric("PASS titles", len(results_df) - len(buys))
        col3.metric("Total Acquisition", f"${total_acquisition:.2f}")
        col4.metric("Est. Net Profit", f"${total_profit:.2f}")
        col5.metric("Lot Margin", f"{lot_margin:.1f}%")
        if lot_decision.startswith("✅"):
            st.success(f"## {lot_decision} — {lot_margin:.1f}% margin")
        else:
            st.error(f"## {lot_decision} — {lot_margin:.1f}% margin (target: {margin_target}%)")
        if not no_data.empty:
            st.warning(f"⚠️ No listings found for: {', '.join(no_data['title'].tolist())}")

    st.subheader("📋 Per-Title Breakdown")
    styled = results_df.style.format({
        "acquisition_cost": "${:.2f}",
        "equilibrium_price": "${:.2f}",
        "total_fees": "${:.2f}",
        "net_profit": "${:.2f}",
        "margin_pct": "{:.1f}%"
    }).applymap(color_decision, subset=["decision"])
    st.dataframe(styled, use_container_width=True)
    csv_out = results_df.to_csv(index=False)
    st.download_button(
        "📥 Download Analysis CSV",
        csv_out,
        f"lot_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv"
    )

# ============================================================
# PAGE LAYOUT
# ============================================================

st.title("eBay Product Listings")

# Sidebar — saved searches
with st.sidebar:
    st.header("💾 Saved Searches")
    if st.session_state.saved_searches:
        st.write(f"You have {len(st.session_state.saved_searches)} saved searches")
        for i, search in enumerate(st.session_state.saved_searches):
            with st.expander(f"🔍 {search['name'][:30]}..."):
                st.write(f"**Saved:** {search['saved_at']}")
                st.write(f"**Search:** {search['params']['search_term']}")
                st.write(f"**Category:** {search['params']['category']}")
                st.write(f"**Max Price:** ${search['params']['max_price']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Load", key=f"load_{i}"):
                        load_saved_search(search['params'])
                        st.success("Search loaded!")
                        st.rerun()
                with col2:
                    if st.button("Delete", key=f"del_{i}"):
                        delete_saved_search(i)
                        st.success("Search deleted!")
                        st.rerun()
    else:
        st.info("No saved searches yet. Run a search and save it!")

# ============================================================
# TABS
# ============================================================

tab1, tab2 = st.tabs(["🔍 Search Listings", "📦 Lot Analysis"])

# ============================================================
# TAB 1 — Search Listings
# ============================================================

with tab1:
    st.write("Fetch latest eBay listings by category, type, and max price.")

    selected_category = st.selectbox(
        "Category",
        options=list(category_options.keys()),
        index=list(category_options.keys()).index(st.session_state.get('loaded_category', 'All Categories'))
    )
    listing_type_filter = st.selectbox(
        "Filter by listing type",
        ["All", "Auction", "Fixed Price", "Best Offer"],
        index=["All", "Auction", "Fixed Price", "Best Offer"].index(st.session_state.get('loaded_listing_type', 'All'))
    )
    seller_type_filter = st.selectbox(
        "Seller Type",
        ["All", "Charity"],
        index=["All", "Charity"].index(st.session_state.get('loaded_seller_type', 'All')),
        help="Charity includes Goodwill, Salvation Army, Habitat for Humanity, St. Vincent de Paul, Catholic Charities, and other nonprofit thrift stores"
    )
    seller_rating_filter = st.multiselect(
        "Filter by seller rating (select multiple or leave empty for all)",
        ["Elite", "Excellent", "Very Good", "Good", "Inexperienced"],
        help="Elite: ≥5000/99% | Excellent: ≥1000/98% | Very Good: ≥500/97% | Good: ≥100/95% | Average: ≥100/90% | Inexperienced: <100/≥90%",
        default=st.session_state.get('loaded_seller_rating', [])
    )
    search_term = st.text_input("Search for:", value=st.session_state.get('loaded_search_term', ''))
    max_price = st.number_input("Maximum total price ($):", min_value=1, max_value=10000, value=st.session_state.get('loaded_max_price', 150))
    limit = st.slider("Number of listings to fetch:", min_value=1, max_value=100, value=st.session_state.get('loaded_limit', 25))

    col1, col2 = st.columns([3, 1])
    with col1:
        search_clicked = st.button("🔍 Search eBay", type="primary")
    with col2:
        if st.button("💾 Save Search"):
            search_params = {
                'search_term': search_term,
                'category': selected_category,
                'listing_type': listing_type_filter,
                'seller_rating': seller_rating_filter,
                'max_price': max_price,
                'limit': limit
            }
            if save_current_search(search_params):
                st.success("Search saved!")
            else:
                st.warning("Search already exists!")

    if search_clicked:
        for key in list(st.session_state.keys()):
            if key.startswith('loaded_'):
                del st.session_state[key]

        if not access_token:
            st.error("Unable to search - missing access token")
        else:
            if selected_category in ["Cell Phones & Smartphones", "Tablets & eBook Readers"]:
                query = f'"{search_term}" -(case,cover,keyboard,manual,guide,screen,protector,folio,box,accessory,cable,cord,charger,pen,for parts,not working, empty box)'
            elif selected_category == "Tech Accessories":
                query = f'"{search_term}" -(broken,defective,not working,for parts, empty box)'
            else:
                query = search_term

            filters = [
                f"price:[1..{max_price}]",
                "priceCurrency:USD",
                "conditions:{1000|1500|2000|2500|3000}"
            ]
            if listing_type_filter == "Auction":
                filters.append("buyingOptions:{AUCTION}")
            elif listing_type_filter == "Fixed Price":
                filters.append("buyingOptions:{FIXED_PRICE}")
            elif listing_type_filter == "Best Offer":
                filters.append("buyingOptions:{BEST_OFFER}")

            if selected_category in aspect_map:
                aspect_name, aspect_value = aspect_map[selected_category]
                filters.append(f"aspect_filter={aspect_name}:{{{aspect_value}}}")
                if selected_category == "Men's Clothing":
                    query += ' "Medium"'
                elif selected_category == "Men's Shoes":
                    query += ' "11"'

            params = {"q": query, "filter": ",".join(filters), "limit": limit}
            category_ids = category_options[selected_category]
            if category_ids:
                params["category_ids"] = category_ids

            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            with st.spinner("Searching eBay..."):
                response = requests.get(
                    "https://api.ebay.com/buy/browse/v1/item_summary/search",
                    params=params, headers=headers
                )

                if response.status_code != 200:
                    st.error(f"API Error: {response.status_code} - {response.text}")
                else:
                    items = response.json().get("itemSummaries", [])
                    results = []
                    for item in items:
                        price = float(item.get("price", {}).get("value", 0.0))
                        shipping = float(item.get("shippingOptions", [{}])[0].get("shippingCost", {}).get("value", 0.0))
                        total_cost = price + shipping
                        buying_options = item.get("buyingOptions", [])
                        if item.get("conditionId") == "7000":
                            continue
                        seller_info = item.get("seller", {})
                        seller_username = seller_info.get("username", "")
                        seller_feedback_score = seller_info.get("feedbackScore", 0)
                        seller_feedback_percent = seller_info.get("feedbackPercentage", 0)
                        if seller_type_filter == "Charity" and not is_charity_seller(seller_username):
                            continue
                        seller_category = categorize_seller(seller_feedback_score, seller_feedback_percent)
                        if seller_rating_filter and seller_category not in seller_rating_filter:
                            continue
                        end_time = "N/A"
                        end_time_str = item.get("itemEndDate")
                        if "AUCTION" in buying_options and end_time_str:
                            try:
                                utc_dt = datetime.datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                                local_dt = utc_dt.astimezone(pytz.timezone('US/Central'))
                                end_time = local_dt.strftime("%Y-%m-%d %I:%M %p %Z")
                            except Exception:
                                end_time = "Invalid date"
                        current_bid_price = float(item.get("currentBidPrice", {}).get("value", 0.0)) if "AUCTION" in buying_options else None
                        if total_cost <= max_price:
                            results.append({
                                "listing": item.get("title", ""),
                                "condition": item.get("condition"),
                                "price": price,
                                "current_bid_price": current_bid_price,
                                "listing_type": ", ".join(buying_options),
                                "bid_count": item.get("bidCount") if "AUCTION" in buying_options else None,
                                "auction_end_time": end_time,
                                "seller": seller_username,
                                "seller_rating": seller_category,
                                "seller_feedback": seller_feedback_percent,
                                "seller_feedback_score": seller_feedback_score,
                                "link": item.get("itemWebUrl")
                            })

                    if results and listing_type_filter != "Auction":
                        df = pd.DataFrame(results).sort_values(by="price").reset_index(drop=True)
                        df = df.drop(columns=['current_bid_price', 'bid_count', 'auction_end_time'], errors='ignore')
                        st.header("📊 Price Analytics")
                        create_price_analytics(df)
                        st.header("📋 Search Results")
                        if seller_type_filter == "Charity":
                            st.info(f"🏪 Showing {len(df)} listings from charity stores")
                        df_display = df.copy()
                        df_display['price'] = df_display['price'].apply(lambda v: f"${v:,.2f}")
                        st.dataframe(
                            df_display.style.set_properties(**{"text-align": "center", "white-space": "pre-wrap"})
                                .set_table_styles([{"selector": "th", "props": [("font-weight", "bold"), ("text-align", "center")]}]),
                            column_config={"link": st.column_config.LinkColumn("Link", display_text="View Listing")},
                            use_container_width=True
                        )
                        st.download_button("📥 Download Results as CSV", df.to_csv(index=False),
                            f"ebay_search_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")
                        st.success(f"Found {len(results)} listings" + (" from charity stores" if seller_type_filter == "Charity" else ""))

                    elif results and listing_type_filter == "Auction":
                        st.header("📋 Auction Listings")
                        df = pd.DataFrame(results).drop(columns=['price'], errors='ignore')
                        df = df.sort_values(by="auction_end_time", ascending=True, na_position="last").reset_index(drop=True)
                        if seller_type_filter == "Charity":
                            st.info(f"🏪 Showing {len(df)} auction listings from charity stores")
                        df_display = df.copy()
                        if 'current_bid_price' in df_display.columns:
                            df_display['current_bid_price'] = df_display['current_bid_price'].apply(
                                lambda v: f"${v:,.2f}" if v is not None else "N/A"
                            )
                        st.dataframe(
                            df_display.style.set_properties(**{"text-align": "center", "white-space": "pre-wrap"})
                                .set_table_styles([{"selector": "th", "props": [("font-weight", "bold"), ("text-align", "center")]}]),
                            column_config={"link": st.column_config.LinkColumn("Link", display_text="View Listing")},
                            use_container_width=True
                        )
                        st.download_button("📥 Download Results as CSV", df.to_csv(index=False),
                            f"ebay_search_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")
                        st.success(f"Found {len(results)} auction listings" + (" from charity stores" if seller_type_filter == "Charity" else ""))
                    else:
                        st.info("No listings found from charity stores matching your criteria." if seller_type_filter == "Charity"
                                else "No listings found matching your criteria.")

# ============================================================
# TAB 2 — Lot Analysis
# ============================================================

with tab2:
    st.write("Look up a single title or upload a CSV for full lot BUY/PASS decisions.")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        bulk_max_price = st.number_input("Max eBay price ($)", min_value=1, max_value=500, value=50, key="bulk_max_price")
    with col_b:
        bulk_limit = st.slider("Listings to sample per title", min_value=5, max_value=50, value=25, key="bulk_limit")
    with col_c:
        margin_target = st.number_input(
            "Target margin (%)", min_value=1, max_value=100, value=30, key="margin_target",
            help="BUY requires margin >= this. Default: 30%"
        )
    with col_d:
        CONDITION_MAP = {
            "Used only": "3000",
            "New only": "1000",
            "New + Used": "1000|1500|3000",
            "All conditions": "1000|1500|2000|2500|3000"
        }
        condition_label = st.selectbox(
            "Condition filter",
            options=list(CONDITION_MAP.keys()),
            index=0,
            key="bulk_condition",
            help="'Used only' recommended for thrift/lot sourcing to avoid new price skew"
        )
        condition_ids = CONDITION_MAP[condition_label]

    input_mode = st.radio("Input mode", ["Single Title", "CSV Upload (Lot)"], horizontal=True, key="bulk_input_mode")

    if input_mode == "Single Title":
        single_title = st.text_input("Title", placeholder="e.g. Halo 3 Xbox 360", key="single_title_input")
        single_category = st.selectbox("Category", options=list(category_options.keys()), key="single_cat")
        single_cost = st.number_input("Your acquisition cost ($)", min_value=0.0, value=1.00, step=0.25, key="single_cost")

        if st.button("🔍 Look Up & Analyze", type="primary", key="single_search_btn"):
            if not single_title.strip():
                st.error("Please enter a title.")
            elif not access_token:
                st.error("Missing eBay access token.")
            else:
                df_single = pd.DataFrame([{
                    "title": single_title.strip(),
                    "category": single_category,
                    "acquisition_cost": single_cost
                }])
                results = run_lot_analysis(df_single, bulk_max_price, bulk_limit, margin_target, access_token, category_options, condition_ids)
                display_lot_results(results, margin_target, is_lot=False)

    else:
        with st.expander("ℹ️ Expected CSV format"):
            st.write(" Only `title` and `category` needed — acquisition cost is calculated automatically.")
            st.code(
                "title,category\n"
                "Die Hard,DVD & Blu-ray\n"
                "Halo 3,Video Games & Consoles\n"
                "Nirvana Nevermind,Music CDs",
                language="csv"
            )
            sample = "title,category\nDie Hard,DVD & Blu-ray\nHalo 3,Video Games & Consoles\nNirvana Nevermind,Music CDs"
            st.download_button("📥 Download Sample CSV", sample, "sample_lot.csv", "text/csv")

        uploaded_csv = st.file_uploader("Upload title CSV", type=["csv"], key="bulk_upload")

        if uploaded_csv is not None:
            try:
                titles_df = pd.read_csv(uploaded_csv)
                if "title" not in titles_df.columns:
                    st.error("CSV must have a 'title' column.")
                else:
                    st.write(f"Found **{len(titles_df)} titles** ready to analyze.")
                    st.dataframe(titles_df, use_container_width=True)

                    lot_cost = st.number_input(
                        "Total lot acquisition cost ($)",
                        min_value=0.0,
                        value=10.00,
                        step=0.50,
                        key="lot_total_cost",
                        help=f"Will be split evenly across all {len(titles_df)} titles (${10.00/len(titles_df):.2f} each at $10.00)"
                    )
                    per_title_cost = lot_cost / len(titles_df)
                    st.caption(f"📌 Per-title cost: **${per_title_cost:.2f}** ({len(titles_df)} titles)")

                    titles_df["acquisition_cost"] = per_title_cost

                    if st.button("🚀 Analyze Lot", type="primary", key="lot_analyze_btn"):
                        if not access_token:
                            st.error("Missing eBay access token.")
                        else:
                            results = run_lot_analysis(titles_df, bulk_max_price, bulk_limit, margin_target, access_token, category_options, condition_ids)
                            display_lot_results(results, margin_target, is_lot=True)
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
