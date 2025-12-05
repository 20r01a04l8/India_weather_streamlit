# app.py — Streamlit India Weather Dashboard (Open-Meteo)
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import date, timedelta
from functools import lru_cache

st.set_page_config(layout="wide", page_title="India Weather Dashboard")

st.title("India Weather — Live Dashboard (API)")

# Predefined regions (expand as you like)
REGIONS = {
    "New Delhi": (28.6139, 77.2090),
    "Mumbai": (19.0760, 72.8777),
    "Kolkata": (22.5726, 88.3639),
    "Chennai": (13.0827, 80.2707),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
}

col1, col2 = st.columns([1,2])

with col1:
    region = st.selectbox("Region", list(REGIONS.keys()), index=0)
    lat, lon = REGIONS[region]

    # Date inputs
    today = date.today()
    default_start = today - timedelta(days=365)
    start = st.date_input("Start date", default_start)
    end = st.date_input("End date", today)

    if start > end:
        st.error("Start date must be before end date.")
        st.stop()

    # Rolling window
    roll_days = st.number_input("Rolling average window (days)", min_value=1, max_value=365, value=30, step=1)
    fetch_btn = st.button("Fetch data")

with col2:
    st.markdown("#### Quick instructions")
    st.markdown("Choose a region and date range then click **Fetch data**. The app fetches daily mean temperature and daily precipitation from Open-Meteo and shows interactive charts.")
    st.markdown("You can expand REGIONS in the code to include more cities or lat/lon coordinates.")

# Cache the API calls to prevent repeated requests while developing
@st.cache_data(ttl=3600)  # cache for 1 hour
def fetch_open_meteo(lat, lon, start_date, end_date):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        "&daily=temperature_2m_mean,precipitation_sum&timezone=Asia/Kolkata"
    )
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"API request failed (HTTP {r.status_code})")
    j = r.json()
    df = pd.DataFrame({
        "date": j["daily"]["time"],
        "temp": j["daily"]["temperature_2m_mean"],
        "precip": j["daily"]["precipitation_sum"]
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df

if fetch_btn:
    try:
        df = fetch_open_meteo(lat, lon, start.isoformat(), end.isoformat())
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

    # compute rolling average
    df["temp_roll"] = df["temp"].rolling(roll_days, min_periods=1).mean()

    # layout: time series + heatmap + table
    st.subheader(f"Temperature time series — {region}")
    fig_ts = px.line(df, x="date", y=["temp","temp_roll"], labels={"value":"Temperature (°C)"}, title="Daily mean temperature and rolling average")
    st.plotly_chart(fig_ts, use_container_width=True)

    st.subheader("Precipitation (daily) and monthly averages")
    fig_prec = px.bar(df, x="date", y="precip", labels={"precip":"Precipitation (mm)"}, title="Daily precipitation")
    st.plotly_chart(fig_prec, use_container_width=True)

    # Monthly heatmap: for a single region, create month-by-year heatmap of avg temp
    st.subheader("Monthly average temperature (heatmap)")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["temp"].mean().reset_index()
    # Show as bar (simple) and provide pivot-style heatmap alternative
    fig_month = px.bar(monthly, x="month", y="temp", labels={"temp":"Avg Temp (°C)"}, title="Monthly average temp")
    st.plotly_chart(fig_month, use_container_width=True)

    # Top statistics & extremes
    max_temp = df["temp"].max()
    max_temp_date = df.loc[df["temp"].idxmax(), "date"].date()
    hot_days = (df["temp"] >= 40).sum()
    st.markdown(f"**Max temp:** {max_temp} °C on {max_temp_date} — **Hot days (≥40°C):** {hot_days}")

    # Data table (last 50 rows)
    st.subheader("Data (most recent 50 rows)")
    st.dataframe(df.tail(50))

    # Allow CSV download
    csv = df.to_csv(index=False)
    st.download_button("Download CSV", csv, file_name=f"{region}_weather_{start}_{end}.csv", mime="text/csv")

else:
    st.info("Choose parameters and click **Fetch data** to load data from the API.")
