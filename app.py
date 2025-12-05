import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import date, timedelta

st.set_page_config(layout="wide", page_title="India Weather Dashboard")

st.title("India Weather — Dynamic Dashboard (API)")

# Simple region list — you can add more lat/lon pairs
REGIONS = {
    "New Delhi": (28.6139, 77.2090),
    "Mumbai": (19.0760, 72.8777),
    "Kolkata": (22.5726, 88.3639),
    "Chennai": (13.0827, 80.2707)
}

region = st.selectbox("Choose region", list(REGIONS.keys()))
lat, lon = REGIONS[region]

# Date range selector
end_date = date.today()
start_date = st.date_input("Start date", end_date - timedelta(days=365))
end_date = st.date_input("End date", end_date)

if start_date > end_date:
    st.error("Start date must be before end date")
    st.stop()

# Fetch data button (or auto fetch)
if st.button("Fetch data from API") or st.session_state.get("auto", False):
    url = (
      f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
      f"&start_date={start_date}&end_date={end_date}"
      "&daily=temperature_2m_mean,precipitation_sum&timezone=Asia/Kolkata"
    )
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        st.error("API error: " + str(r.status_code))
    else:
        payload = r.json()
        df = pd.DataFrame({
            "date": payload["daily"]["time"],
            "temp": payload["daily"]["temperature_2m_mean"],
            "precip": payload["daily"]["precipitation_sum"]
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        # rolling average
        df["temp_30d"] = df["temp"].rolling(30, min_periods=1).mean()
        st.subheader(f"Time series — {region}")
        fig = px.line(df, x="date", y=["temp","temp_30d"], labels={"value":"Temp (°C)"})
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Monthly heatmap (avg temp)")
        df["month"] = df["date"].dt.to_period("M").astype(str)
        heat = df.groupby("month")["temp"].mean().reset_index()
        fig2 = px.bar(heat, x="month", y="temp", labels={"temp":"Avg Temp (°C)"})
        st.plotly_chart(fig2, use_container_width=True)

        # show table
        st.dataframe(df.tail(50))
