# fetch_data.py
# Prefetch multi-region daily temp & precip from Open-Meteo and write data.csv
# Usage: python fetch_data.py
import requests
import pandas as pd
import time
from datetime import date, timedelta

# Expand this list as desired
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

START_DATE = "2023-01-01"   # change if you want a longer history
END_DATE = date.today().isoformat()

def safe_get(url, retries=3, backoff=1.5, timeout=30):
    for i in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff * (i+1))
                continue
            r.raise_for_status()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(backoff * (i+1))
    raise RuntimeError("Failed to GET " + url)

def fetch_region(name, lat, lon, start_date, end_date):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        "&daily=temperature_2m_mean,precipitation_sum&timezone=Asia/Kolkata"
    )
    r = safe_get(url)
    j = r.json()
    df = pd.DataFrame({
        "date": j["daily"]["time"],
        "temp": j["daily"]["temperature_2m_mean"],
        "precip": j["daily"]["precipitation_sum"]
    })
    df["region"] = name
    return df

def main():
    rows = []
    for i,(name,(lat,lon)) in enumerate(REGIONS.items(), start=1):
        print(f"[{i}/{len(REGIONS)}] Fetching {name}")
        df = fetch_region(name, lat, lon, START_DATE, END_DATE)
        rows.append(df)
        time.sleep(0.3)  # polite pause
    if rows:
        big = pd.concat(rows, ignore_index=True)
        big["date"] = pd.to_datetime(big["date"])
        big = big.sort_values(["region","date"]).reset_index(drop=True)
        big.to_csv("data.csv", index=False)
        print("Wrote data.csv rows:", len(big))
    else:
        print("No data fetched")

if __name__ == "__main__":
    main()
