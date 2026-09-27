"""Generate sample_data.csv — realistic weekly sales for a cleaning-products business.

Run: python generate_sample_data.py
Uses a fixed random seed so the output is the same every time.

Story the data tells:
- Floor Cleaner grows ~4% a month
- White Phenyl slowly declines
- March 2024 is an anomaly: every product drops ~50%
- North India is the strongest region, South India grows fastest
- June and July get a seasonal boost every year
- Overall business trends upward
"""

import numpy as np
import pandas as pd

SEED = 42
START = "2024-01-01"
END = "2025-06-30"

# Base weekly units per product per region, list price (INR), monthly growth rate
PRODUCTS = {
    "Floor Cleaner":  {"units": 60, "price": 120, "growth": 0.04},
    "Toilet Cleaner": {"units": 55, "price": 95,  "growth": 0.012},
    "Dishwash":       {"units": 70, "price": 80,  "growth": 0.01},
    "Hand Wash":      {"units": 50, "price": 65,  "growth": 0.015},
    "Glass Cleaner":  {"units": 35, "price": 90,  "growth": 0.008},
    "White Phenyl":   {"units": 65, "price": 55,  "growth": -0.025},
}

# Size multiplier and extra monthly growth per region
REGIONS = {
    "North India": {"size": 1.45, "growth": 0.0},
    "South India": {"size": 0.70, "growth": 0.03},
    "West India":  {"size": 1.00, "growth": 0.0},
    "East India":  {"size": 0.80, "growth": 0.0},
}

CUSTOMER_TYPES = ["Retail", "Wholesale", "Institutional"]
CUSTOMER_WEIGHTS = [0.55, 0.30, 0.15]
CUSTOMER_DISCOUNT = {"Retail": 1.0, "Wholesale": 0.90, "Institutional": 0.85}
CUSTOMER_VOLUME = {"Retail": 1.0, "Wholesale": 1.8, "Institutional": 1.5}

PAYMENT_METHODS = ["Cash", "UPI", "Credit"]
PAYMENT_WEIGHTS = [0.30, 0.45, 0.25]

SEASONAL_BOOST = {6: 1.25, 7: 1.30}   # June, July
ANOMALY = {(2024, 3): 0.5}             # March 2024


def generate(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # 4 weekly sales dates per month (1st, 8th, 15th, 22nd) so every month
    # has the same number of weeks and months compare fairly.
    months = pd.date_range(START, END, freq="MS")
    weeks = [m + pd.Timedelta(days=d) for m in months for d in (0, 7, 14, 21)]
    rows = []

    for date in weeks:
        months_elapsed = (date.year - 2024) * 12 + (date.month - 1)
        season = SEASONAL_BOOST.get(date.month, 1.0)
        anomaly = ANOMALY.get((date.year, date.month), 1.0)

        for product, p in PRODUCTS.items():
            for region, r in REGIONS.items():
                trend = (1 + p["growth"] + r["growth"]) ** months_elapsed
                customer = rng.choice(CUSTOMER_TYPES, p=CUSTOMER_WEIGHTS)
                payment = rng.choice(PAYMENT_METHODS, p=PAYMENT_WEIGHTS)
                noise = rng.normal(1.0, 0.08)

                units = (p["units"] * r["size"] * trend * season * anomaly
                         * CUSTOMER_VOLUME[customer] * noise)
                units = max(1, int(round(units)))
                unit_price = round(p["price"] * CUSTOMER_DISCOUNT[customer], 2)

                rows.append({
                    "Date": date.strftime("%Y-%m-%d"),
                    "Product": product,
                    "Region": region,
                    "Units_Sold": units,
                    "Unit_Price": unit_price,
                    "Total_Revenue": round(units * unit_price, 2),
                    "Customer_Type": customer,
                    "Payment_Method": payment,
                    "Month": date.strftime("%Y-%m"),
                    "Quarter": f"{date.year}-Q{(date.month - 1) // 3 + 1}",
                })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate()
    df.to_csv("sample_data.csv", index=False)
    print(f"Wrote sample_data.csv: {len(df)} rows, "
          f"{df.Date.min()} to {df.Date.max()}")
