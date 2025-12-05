# app.py - Multi-region Streamlit dashboard with cache and prefetched-data support
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import date, timedelta
from io import StringIO
import time

st.set_page_config(layout="wide", page_title="India Weather — Multi-region")

st.title("India Weather — Multi-region Dashboard")

# ----- CONFIG: expand this with any lat/lon pairs you want -----
REGIONS = {
    "New Delhi": (28.6139, 77.2090),
    "Mumbai": (19.0760, 72.8777),
    "Kolkata": (22.5726, 88.3639),
    "Chennai": (13.0827, 80.2707),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Pune": (18.5204, 73.8567),
    "Ahmedabad": (23.0225, 72.5714),
    "Jaipur": (26.9124, 75.7873),
    "Lucknow": (26.8467, 80.9462)
}
# ---------------------------------------------------------------

st.sidebar.header("Data source & options")
use_prefetched = st.sidebar.checkbox("Use prefetched data.csv (recommended)", value=True)
prefetch_path = "data.csv"  # created by GitHub Actions if enabled

# Date range
today = date.today()
default_start = today - timedelta(days=365)
start = st.sidebar.date_input("Start date", default_start)
end = st.sidebar.date_input("End date", today)
if start > end:
    st.error("Start date must be before end date.")
    st.stop()

# Regions selection (multi-select)
selected_regions = st.sidebar.multiselect("Regions (multi-select)", list(REGIONS.keys()), default=list(REGIONS.keys())[:4])

# Rolling average window
roll_days = st.sidebar.number_input("Rolling average window (days)", min_value=1, max_value=365, value=30, step=1)

# Force live fetch even if data.csv exists
force_live = st.sidebar.checkbox("Force live API fetch (ignore prefetched)", value=False)

# --- Utility: robust requests with retries/backoff (rate-limit friendly) ---
def safe_get(url, retries=3, backoff=1.5, timeout=30):
    for i in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r
            # handle 429 or 5xx with backoff
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff * (i+1))
                continue
            r.raise_for_status()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(backoff * (i+1))
    raise RuntimeError("Failed to GET " + url)

# --- Cache API fetches to avoid repeated calls during app lifetime ---
@st.cache_data(ttl=3600)
def fetch_open_meteo_single(lat, lon, start_date, end_date):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        "&daily=temperature_2m_mean,precipitation_sum&timezone=Asia/Kolkata"
    )
    resp = safe_get(url)
    j = resp.json()
    df = pd.DataFrame({
        "date": j["daily"]["time"],
        "temp": j["daily"]["temperature_2m_mean"],
        "precip": j["daily"]["precipitation_sum"]
    })
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=3600)
def fetch_open_meteo_multi(regions_map, start_date, end_date, progress=False):
    # regions_map: dict name -> (lat,lon)
    rows = []
    total = len(regions_map)
    i = 0
    for name, (lat, lon) in regions_map.items():
        i += 1
        if progress:
            st.sidebar.write(f"Fetching {name} ({i}/{total})")
        df = fetch_open_meteo_single(lat, lon, start_date, end_date)
        df["region"] = name
        rows.append(df)
        # small sleep to be gentle on API
        time.sleep(0.3)
    if rows:
        big = pd.concat(rows, ignore_index=True)
        return big
    return pd.DataFrame(columns=["date","temp","precip","region"])

# --- Load data: prefetched CSV if available, else fetch live for selected regions ---
data = None
if use_prefetched and not force_live:
    try:
        with open(prefetch_path, "r", encoding="utf-8") as f:
            data = pd.read_csv(f, parse_dates=["date"])
            st.sidebar.success("Loaded prefetched data.csv")
    except FileNotFoundError:
        st.sidebar.info("Prefetched data.csv not found in repo - will fetch live")
    except Exception as e:
        st.sidebar.warning(f"Failed to load prefetched data.csv: {e}")

# If prefetched present but we still want only selected regions/time window, filter:
if data is not None:
    # Keep rows for selected regions and date range
    data = data[(data["region"].isin(selected_regions)) & (data["date"] >= pd.to_datetime(start)) & (data["date"] <= pd.to_datetime(end))].copy()
    if data.empty:
        st.sidebar.warning("Prefetched file had no data for your selection; falling back to live fetch.")
        data = None

if data is None:
    # Fetch live only for selected_regions (be careful about selecting many to avoid many API calls)
    if not selected_regions:
        st.info("Select at least one region on the left to fetch or view data.")
        st.stop()
    to_fetch = {r: REGIONS[r] for r in selected_regions}
    with st.spinner("Fetching data from Open-Meteo (live) — this may take a few seconds per region..."):
        try:
            data = fetch_open_meteo_multi(to_fetch, start.isoformat(), end.isoformat(), progress=True)
        except Exception as e:
            st.error(f"Live fetch failed: {e}")
            st.stop()

# Now we have a DataFrame `data` with columns: date,temp,precip,region
if data is None or data.empty:
    st.warning("No data available for chosen parameters.")
    st.stop()

# compute rolling mean per region
data = data.sort_values(["region","date"])
data["temp_roll"] = data.groupby("region")["temp"].transform(lambda s: s.rolling(roll_days, min_periods=1).mean())

# === UI: Multi-region time series ===
st.markdown("## Multi-region time series (temperature)")
fig_ts = px.line(data, x="date", y="temp", color="region", labels={"temp":"Temp (°C)"}, title="Daily mean temperature")
# add rolling for each region as separate traces (lighter style)
for region in data["region"].unique():
    df_r = data[data["region"]==region]
    fig_ts.add_scatter(x=df_r["date"], y=df_r["temp_roll"], mode="lines", name=f"{region} ({roll_days}d roll)", line=dict(dash="dash"))
st.plotly_chart(fig_ts, use_container_width=True)

# === Multi-region heatmap: pivot month x region (avg temp) ===
st.markdown("## Multi-region heatmap: Month × Region (avg temp)")
data["month"] = data["date"].dt.to_period("M").astype(str)
pivot = data.groupby(["region","month"])["temp"].mean().reset_index()
heat = pivot.pivot(index="region", columns="month", values="temp").reindex(index=selected_regions)
# If too many months/regions, trim for legibility or allow horizontal scroll
fig_heat = px.imshow(heat, labels=dict(x="Month", y="Region", color="Avg Temp (°C)"))
fig_heat.update_layout(height=600, width=1000)
st.plotly_chart(fig_heat, use_container_width=True)

# === Precipitation comparison (stacked) ===
st.markdown("## Precipitation — cumulative over selected period")
prec_sum = data.groupby("region")["precip"].sum().reset_index().sort_values("precip", ascending=False)
fig_prec = px.bar(prec_sum, x="region", y="precip", title="Total precipitation (selected date range)", labels={"precip":"Total precip (mm)"})
st.plotly_chart(fig_prec, use_container_width=True)

# === Quick stats & table ===
st.markdown("## Quick statistics")
stats = data.groupby("region").agg(
    avg_temp=("temp","mean"),
    max_temp=("temp","max"),
    hot_days=("temp", lambda s: (s>=40).sum()),
    total_precip=("precip","sum")
).reset_index().sort_values("avg_temp", ascending=False)
st.dataframe(stats.style.format({"avg_temp":"{:.2f}","max_temp":"{:.1f}","hot_days":"{:.0f}","total_precip":"{:.1f}"}))

st.markdown("## Raw data (preview)")
st.dataframe(data.tail(200))

# Download filtered CSV
csv_bytes = data.to_csv(index=False).encode("utf-8")
st.download_button("Download filtered CSV", csv_bytes, file_name="weather_filtered.csv", mime="text/csv")
