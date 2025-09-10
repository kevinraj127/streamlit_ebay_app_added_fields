import streamlit as st
import requests
import pandas as pd
import datetime
import pytz
import plotly.express as px
import plotly.graph_objects as go
from base64 import b64encode
import json
import urllib.parse
import os
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

# Initialize session state for saved searches
if 'saved_searches' not in st.session_state:
    st.session_state.saved_searches = []

# eBay API credentials - with error handling
try:
    CLIENT_ID = st.secrets["ebay"]["CLIENT_ID"]
    CLIENT_SECRET = st.secrets["ebay"]["CLIENT_SECRET"]

    
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error("eBay API credentials not found in secrets. Please configure them in your Streamlit secrets.")
        st.stop()
        
except KeyError:
    st.error("eBay API credentials not found in secrets. Please add them to your Streamlit secrets configuration.")
    st.stop()

# Encode credentials
credentials = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

# Get OAuth2 token with error handling
@st.cache_data(ttl=3600)
def get_access_token():
    try:
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
        response.raise_for_status()  # Raise an exception for bad status codes
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            st.error(f"Failed to get access token: {token_data}")
            return None
            
        return access_token
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting access token: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error getting access token: {e}")
        return None

# Seller categorization function
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

# Functions for saved searches
def save_current_search(search_params):
    """Save current search parameters"""
    search_name = f"{search_params['search_term']} in {search_params['category']} (${search_params['max_price']})"
    
    # Avoid duplicates
    existing_names = [search['name'] for search in st.session_state.saved_searches]
    if search_name not in existing_names:
        search_entry = {
            'name': search_name,
            'params': search_params,
            'saved_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        st.session_state.saved_searches.append(search_entry)
        return True
    return False

def load_saved_search(search_params):
    """Load saved search parameters into session state"""
    for key, value in search_params.items():
        st.session_state[f"loaded_{key}"] = value

def delete_saved_search(index):
    """Delete a saved search"""
    if 0 <= index < len(st.session_state.saved_searches):
        del st.session_state.saved_searches[index]

# Price analytics functions
def create_price_analytics(df):
    """Create price analytics dashboard"""
    if df.empty:
        st.info("No data available for analytics.")
        return
    
    # Ensure numeric columns exist and are valid
    numeric_cols = ['price', 'net_profit']
    for col in numeric_cols:
        if col not in df.columns:
            st.error(f"Missing required column: {col}")
            return
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Remove rows with NaN values in critical columns
    df_clean = df.dropna(subset=numeric_cols)
    
    if df_clean.empty:
        st.warning("No valid price data available for analytics.")
        return
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        avg_price = df_clean['price'].mean()
        st.metric("Average Price", f"${avg_price:.2f}")
    
    with col2:
        median_price = df_clean['price'].median()
        st.metric("Median Price", f"${median_price:.2f}")
    
    with col3:
        median_ebay_payout = df_clean['ebay_pay_out'].median()
        st.metric("Median eBay Pay Out", f"${median_ebay_payout:.2f}")

    with col4:
        median_profit = df_clean['net_profit'].median()
        st.metric("Median Estimated Profit", f"${median_profit:.2f}")

# Calculate profit metrics
def calculate_profit_metrics(price, shipping, cogs, shipping_cost_input, ad_rate, category):
    """Calculate profit metrics with proper error handling"""
    try:
        price = float(price) if price is not None else 0.0
        shipping = float(shipping) if shipping is not None else 0.0
        cogs = float(cogs) if cogs is not None else 0.0
        shipping_cost_input = float(shipping_cost_input) if shipping_cost_input is not None else 0.0
        ad_rate = float(ad_rate) if ad_rate is not None else 0.0
        
        # eBay fee structure
        if category in ["Headphones", "Video Games & Consoles"]:
            ebay_fee = 0.136
        else:
            ebay_fee = 0.153
        
        final_value_fee = 0.4 
        tax_rate = 0.0825
        ad_rate_decimal = ad_rate / 100
        
        sold_price = price + shipping_cost_input
        sold_price_with_shipping_taxes = sold_price * (1 + tax_rate)
        ebay_transaction_fees = (sold_price_with_shipping_taxes * ebay_fee) + final_value_fee
        ad_fees = ad_rate_decimal * sold_price_with_shipping_taxes
        total_expenses = ebay_transaction_fees + ad_fees + shipping_cost_input
        ebay_pay_out = sold_price - total_expenses
        net_profit = ebay_pay_out - cogs
        profit_margin = (net_profit / price * 100) if price > 0 else 0
        
        return net_profit, profit_margin, total_expenses, ebay_pay_out
    except (ValueError, TypeError, ZeroDivisionError) as e:
        st.warning(f"Error calculating profit metrics: {e}")
        return 0.0, 0.0, 0.0, 0.0

# UI
st.title("eBay Product Listings with Estimated Profit")
st.write("Fetch latest eBay listings by category, type, max price, COGS, and estimated profit.")

# Saved Searches Sidebar
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

# Main search interface
category_options = {
    "All Categories": None,
    "Books": "267",
    "DVD & Blu-ray": "617",
    "Headphones": "112529",
    "Music CDs": "176984",
    "Music Cassettes": "176983",
    "Video Games & Consoles": "1249"
}

# Use loaded values if available, otherwise use defaults
selected_category = st.selectbox(
    "Category", 
    options=list(category_options.keys()),
    index=list(category_options.keys()).index(st.session_state.get('loaded_category', 'All Categories'))
)


search_term = st.text_input(
    "Search for:", 
    value=st.session_state.get('loaded_search_term', '')
)

max_price = st.number_input(
    "Maximum total price ($):", 
    min_value=1, 
    max_value=10000, 
    value=st.session_state.get('loaded_max_price', 150)
)

cogs = st.number_input(
    "Cost of Goods Sold ($):",
    min_value=0.0,
    max_value=10000.0,
    value=float(st.session_state.get('loaded_cogs', 2))
)

shipping_cost = st.number_input(
    "Shipping Cost ($):",
    min_value=0.0,
    max_value=10000.0,
    value=float(st.session_state.get('loaded_shipping_cost', 4.47))
)

ad_rate = st.number_input(
    "Advertising Rate (%):",
    min_value=0.0,
    max_value=100.0,
    value=float(st.session_state.get('loaded_ad_rate', 3.0))
)

limit = st.slider(
    "Number of listings to fetch:", 
    min_value=1, 
    max_value=100, 
    value=st.session_state.get('loaded_limit', 25)
)

# Search and Save buttons
col1, col2 = st.columns([3, 1])

with col1:
    search_clicked = st.button("🔍 Search eBay", type="primary")

with col2:
    if st.button("💾 Save Search"):
        search_params = {
            'search_term': search_term,
            'category': selected_category,
            'max_price': max_price,
            'cogs': cogs,
            'shipping_cost': shipping_cost,
            'ad_rate': ad_rate,
            'limit': limit
        }
        
        if save_current_search(search_params):
            st.success("Search saved!")
        else:
            st.warning("Search already exists!")

# Execute search
if search_clicked:
    # Validate inputs
    if not search_term:
        st.error("Please enter a search term.")
        st.stop()
    
    # Get access token
    access_token = get_access_token()
    
    if not access_token:
        st.error("Unable to search - failed to get access token")
        st.stop()

    # Clear loaded values AFTER search is clicked
    for key in list(st.session_state.keys()):
        if key.startswith('loaded_'):
            del st.session_state[key]

    excluded_terms = "-(case only, manual only, insert only, artwork only, booklet only, manaul only, no disc,\"for parts\",\"not working\",\"empty box\",broken,defective)"
    
    if selected_category in ["Video Games & Consoles"]:
        query = f'"{search_term}" {excluded_terms}'
    else:
        query = f'"{search_term}"'

    # Build filters
    filters = [
        f"price:[1..{max_price}]",
        "priceCurrency:USD",
        "conditions:{1000|1500|2000|2500|3000}," # New, Like New, Very Good, Good, Acceptable
        "buyingOptions:{FIXED_PRICE|BEST_OFFER}"  
    ]

    params = {
        "q": query,
        "filter": ",".join(filters),
        "limit": limit,
        "sort": "price"  # Sort by price ascending
    }

    category_ids = category_options[selected_category]
    if category_ids:
        params["category_ids"] = category_ids

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    with st.spinner("Searching eBay..."):
        try:
            response = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search", 
                params=params, 
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                st.error(f"API Error: {response.status_code} - {response.text}")
                st.write("Debug info:")
                st.write(f"Query: {query}")
                st.write(f"Filters: {filters}")
                st.write(f"Params: {params}")
                st.stop()
            
            data = response.json()
            items = data.get("itemSummaries", [])
            
            if not items:
                st.info("No listings found matching your criteria. Try adjusting your search parameters.")
                st.stop()

            results = []
            for item in items:
                try:
                    title = item.get("title", "")
                    price = float(item.get("price", {}).get("value", 0.0))
                    shipping_options = item.get("shippingOptions", [{}])
                    shipping = float(shipping_options[0].get("shippingCost", {}).get("value", 0.0)) if shipping_options else 0.0
                    total_cost = price + shipping
                    link = item.get("itemWebUrl", "")
                    buying_options = item.get("buyingOptions", [])
                    
                    # Skip "for parts" items
                    condition_id = item.get("conditionId")
                    if condition_id == "7000":
                        continue
                    
                    # Calculate profit metrics
                    net_profit, profit_margin, total_expenses, ebay_pay_out = calculate_profit_metrics(
                        price, shipping, cogs, shipping_cost, ad_rate, selected_category
                    )

                    # Get seller information
                    seller_info = item.get("seller", {})
                    seller_username = seller_info.get("username", "Unknown")
                    seller_feedback_score = seller_info.get("feedbackScore", 0)
                    seller_feedback_percent = seller_info.get("feedbackPercentage", 0)
                    
                    # Categorize seller
                    seller_category = categorize_seller(seller_feedback_score, seller_feedback_percent)

                    if total_cost <= max_price:
                        result = {
                            "listing": title,
                            "condition": item.get("condition", "Unknown"),
                            "price": price,
                            "ebay_pay_out": ebay_pay_out,
                            "total_expenses": total_expenses,
                            "cogs": cogs,
                            "net_profit": net_profit,
                            "profit_margin": profit_margin,
                            "listing_type": ", ".join(buying_options),
                            "seller": seller_username,
                            "seller_rating": seller_category,
                            "seller_feedback": seller_feedback_percent,
                            "seller_feedback_score": seller_feedback_score,
                            "link": link
                        }
                        
                        results.append(result)
                        
                except Exception as e:
                    st.warning(f"Error processing item: {e}")
                    continue

            if results:
                df = pd.DataFrame(results)
                df = df.sort_values(by="price").reset_index(drop=True)

                # Price Analytics Dashboard
                st.header("📊 Price Analytics")
                create_price_analytics(df)
                
                st.header("📋 Search Results")
                
                # Display main results
                display_cols = ['listing', 'condition', 'price', 'ebay_pay_out', 'net_profit', 
                              'profit_margin', 'seller', 'seller_rating', 'seller_feedback', 'link']
                available_cols = [col for col in display_cols if col in df.columns]

                st.dataframe(
                    df[available_cols],
                    column_config={
                        "link": st.column_config.LinkColumn("Link", display_text="View Listing"),
                        "price": st.column_config.NumberColumn("Price", format="$%.2f"),
                        "ebay_pay_out": st.column_config.NumberColumn("eBay Payout", format="$%.2f"),
                        "total_expenses": st.column_config.NumberColumn("Total Expenses", format="$%.2f"),
                        "cogs": st.column_config.NumberColumn("COGS", format="$%.2f"),
                        "net_profit": st.column_config.NumberColumn("Net Profit", format="$%.2f"),
                        "profit_margin": st.column_config.NumberColumn("Profit Margin", format="%.2f%%"),
                        "seller_feedback": st.column_config.NumberColumn("Seller Feedback %", format="%.1f%%")
                    },
                    use_container_width=True
                )
            
                # Export functionality
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Download Results as CSV",
                    csv,
                    f"ebay_search_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    "text/csv"
                )
                
                st.success(f"Found {len(results)} listings")
                
            else:
                st.info("No listings found matching your criteria. Try adjusting your search parameters.")
                
        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {e}")
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            st.write("Please try again or contact support if the problem persists.")
