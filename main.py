from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- CACHE --------
cache = {}
cache_time = {}
CACHE_TTL = 600


# -------- SAFE --------
def safe(v):
    try:
        return float(str(v).replace("%", "").replace(",", ""))
    except:
        return None


def safe_div(a, b):
    if a in [None] or b in [None, 0]:
        return None
    return a / b


# -------- SCRAPER (PRIMARY DATA) --------
def fetch_screener(ticker):
    try:
        url = f"https://www.screener.in/company/{ticker}/"
        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        data = {}

        for li in soup.select("li.flex.flex-space-between"):
            name = li.find("span", class_="name")
            val = li.find("span", class_="number")

            if name and val:
                data[name.text.strip()] = safe(val.text.strip())

        return data
    except:
        return {}


# -------- YAHOO (FALLBACK) --------
def fetch_yahoo(ticker):
    try:
        stock = yf.Ticker(ticker + ".NS")
        info = stock.info
        hist = stock.history(period="6mo")

        return {
            "price": hist["Close"].iloc[-1] if not hist.empty else None,
            "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "dividend": info.get("dividendYield"),
        }
    except:
        return {}


# -------- ANALYZE --------
@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()
    now = time.time()

    if ticker in cache and now - cache_time.get(ticker, 0) < CACHE_TTL:
        return cache[ticker]

    try:
        # -------- WATERFALL --------
        screener = fetch_screener(ticker)
        yahoo = fetch_yahoo(ticker)

        price = yahoo.get("price")

        pe = screener.get("Stock P/E") or yahoo.get("pe")
        pb = screener.get("Price to book value") or yahoo.get("pb")
        roe = screener.get("ROE")
        roce = screener.get("ROCE")
        debt = screener.get("Debt to equity")
        npm = screener.get("Net Profit Margin")
        current_ratio = screener.get("Current ratio")

        dividend = yahoo.get("dividend")
        if dividend:
            dividend = round(dividend * 100, 2)
            if dividend > 50:
                dividend = None

        peg = safe_div(pe, roe) if pe and roe else None

        # -------- RATIOS --------
        ratios = []

        def add(name, val, ideal, better, definition, pct=False):
            if val is None:
                return 0, 0

            display = round(val, 2)
            if pct:
                display_str = f"{display}%"
            else:
                display_str = display

            good = False
            try:
                if better == "HIGH":
                    good = display > float(ideal.replace(">", "").replace("%", ""))
                else:
                    good = display < float(ideal.replace("<", ""))
            except:
                pass

            ratios.append({
                "name": name,
                "value": display_str,
                "ideal": ideal,
                "interpretation": f"{better} is better",
                "definition": definition,
                "status": "GOOD" if good else "WEAK"
            })

            return (1 if good else 0), 1

        score = 0
        total = 0

        def add_wrap(*args, **kwargs):
            nonlocal score, total
            s, t = add(*args, **kwargs)
            score += s
            total += t

        add_wrap("ROE", roe, ">15%", "HIGH", "Profit generated from equity", True)
        add_wrap("ROCE", roce, ">18%", "HIGH", "Capital efficiency", True)
        add_wrap("Net Profit Margin", npm, ">10%", "HIGH", "Profit after expenses", True)
        add_wrap("P/E Ratio", pe, "<25", "LOW", "Valuation vs earnings")
        add_wrap("PEG Ratio", peg, "<1.5", "LOW", "Growth adjusted valuation")
        add_wrap("Debt to Equity", debt, "<0.5", "LOW", "Debt burden")
        add_wrap("Current Ratio", current_ratio, ">1.5", "HIGH", "Liquidity")

        # -------- SCORE --------
        final_score = round((score / total) * 10, 1) if total else 0

        verdict = (
            "STRONG BUY 🟢" if final_score >= 8 else
            "BUY 🟢" if final_score >= 6 else
            "HOLD 🟡" if final_score >= 4 else
            "AVOID 🔴"
        )

        reasons = [f"{r['name']} is {r['status']}" for r in ratios]

        response = {
            "stock": ticker,
            "price": round(price, 2) if price else None,
            "score": final_score,
            "verdict": verdict,
            "trend": "N/A",
            "ratios": ratios,
            "reasons": reasons
        }

        cache[ticker] = response
        cache_time[ticker] = now

        return response

    except Exception:
        return {"error": "System busy. Try again shortly."}