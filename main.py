from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import time
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- SAFE FUNCTIONS ----------------

def safe_div(a, b):
    if a is None or b in [None, 0]:
        return None
    return a / b

def fetch(stock):
    for _ in range(3):
        try:
            data = stock.history(period="1y")
            if not data.empty:
                return data
        except:
            pass
        time.sleep(2)
    return None

def get(df, keys):
    try:
        if df is None or df.empty:
            return None
        for idx in df.index:
            name = str(idx).lower()
            if any(k in name for k in keys):
                return float(df.loc[idx].iloc[0])
    except:
        pass
    return None

# ---------------- STOCK LIST ----------------

STOCKS = [
"BAJFINANCE","RELIANCE","HDFCBANK","ICICIBANK","BHARTIARTL","ADANIENT",
"AXISBANK","COALINDIA","INDIGO","ONGC","LT","INFY","M&M","SBIN",
"TCS","MARUTI","TATASTEEL","SUNPHARMA","ITC","HINDALCO","ULTRACEMCO",
"EICHERMOT","HCLTECH","POWERGRID","KOTAKBANK","WIPRO","NTPC",
"BAJAJ-AUTO","TECHM","HINDUNILVR","DRREDDY","CIPLA","TITAN"
]

# ---------------- RATIO ENGINE ----------------

def get_ratios(ticker):

    stock = yf.Ticker(ticker + ".NS")

    hist = fetch(stock)
    if hist is None:
        return None

    price = float(hist["Close"].iloc[-1])
    dma50 = float(hist["Close"].tail(50).mean())
    dma200 = float(hist["Close"].tail(200).mean())

    fin = stock.financials
    bs = stock.balance_sheet

    net_income = get(fin, ["net income"])
    ebit = get(fin, ["ebit"])

    equity = get(bs, ["equity"])
    debt = get(bs, ["debt"])
    total_assets = get(bs, ["total assets"])
    current_assets = get(bs, ["current assets"])
    current_liabilities = get(bs, ["current liabilities"])

    roe = safe_div(net_income, equity)
    roce = safe_div(ebit, (total_assets - current_liabilities) if total_assets and current_liabilities else None)
    debt_eq = safe_div(debt, equity)
    current_ratio = safe_div(current_assets, current_liabilities)

    info = stock.info
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    market_cap = info.get("marketCap")

    return {
        "price": price,
        "dma50": dma50,
        "dma200": dma200,
        "roe": roe * 100 if roe else None,
        "roce": roce * 100 if roce else None,
        "debt": debt_eq,
        "current_ratio": current_ratio,
        "pe": pe,
        "pb": pb,
        "market_cap": market_cap
    }

# ---------------- SCREENERS ----------------

@app.get("/screener")
def screener(type: str):

    results = []

    for s in STOCKS:

        data = get_ratios(s)
        if data is None:
            continue

        try:

            # -------- ALL ROUNDER --------
            if type == "allrounder":
                if (
                    data["roe"] and data["roe"] > 15 and
                    data["roce"] and data["roce"] > 18 and
                    data["debt"] is not None and data["debt"] < 0.5 and
                    data["current_ratio"] and data["current_ratio"] > 1.5 and
                    data["pe"] and data["pe"] < 25 and
                    data["price"] > data["dma200"] and
                    data["price"] > data["dma50"]
                ):
                    results.append({"stock": s, "tag": "ALL-ROUNDER", "signal": "BUY 🟢"})

            # -------- MULTIBAGGER --------
            elif type == "multibagger":
                if (
                    data["roe"] and data["roe"] > 20 and
                    data["roce"] and data["roce"] > 20 and
                    data["debt"] is not None and data["debt"] < 0.3 and
                    data["pe"] and data["pe"] < 30 and
                    data["market_cap"] and data["market_cap"] > 500e7
                ):
                    results.append({"stock": s, "tag": "MULTIBAGGER", "signal": "BUY 🚀"})

            # -------- BLUECHIP --------
            elif type == "bluechip":
                if (
                    data["market_cap"] and data["market_cap"] > 20000e7 and
                    data["roe"] and data["roe"] > 15 and
                    data["roce"] and data["roce"] > 18 and
                    data["debt"] is not None and data["debt"] < 0.5
                ):
                    results.append({"stock": s, "tag": "BLUECHIP", "signal": "SAFE 🛡️"})

        except:
            continue

    return {"stocks": results}