from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from bs4 import BeautifulSoup
import yfinance as yf
import math
import requests

app = FastAPI(title="Indian Stock Analyzer API")

# ---------------------------------------------------
# CORS
# ---------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def safe_round(val, digits=2):
    try:
        if val is None:
            return "N/A"
        if isinstance(val, float) and math.isnan(val):
            return "N/A"
        return round(float(val), digits)
    except:
        return "N/A"


def to_float(val):
    try:
        if val is None:
            return 0.0

        val = str(val)
        val = val.replace(",", "")
        val = val.replace("%", "")
        val = val.replace("₹", "")
        val = val.strip()

        return float(val)
    except:
        return 0.0


def calculate_rsi(close_series, period=14):
    delta = close_series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return float(rsi.iloc[-1])


def final_score(pe, roe, debt, divy, price, dma50, dma200, rsi):
    score = 0
    reasons = []

    if pe > 0 and pe < 25:
        score += 2
        reasons.append("Fair valuation")

    if roe > 15:
        score += 2
        reasons.append("Strong ROE")

    # Yahoo debtToEquity often uses percentage-style numbers
    if debt > 0 and debt < 100:
        score += 2
        reasons.append("Manageable debt")

    if divy > 1:
        score += 1
        reasons.append("Pays dividend")

    if price > dma50:
        score += 1
        reasons.append("Above 50 DMA")

    if price > dma200:
        score += 1
        reasons.append("Above 200 DMA")

    if rsi < 70:
        score += 1
        reasons.append("Healthy RSI")

    if score >= 8:
        verdict = "BUY 🟢"
        horizon = "3 to 5+ Years"
    elif score >= 5:
        verdict = "HOLD 🟡"
        horizon = "Accumulate gradually"
    else:
        verdict = "AVOID 🔴"
        horizon = "Weak / expensive"

    return score, verdict, horizon, reasons


# ---------------------------------------------------
# Screener Scraper (Fundamentals)
# ---------------------------------------------------
def get_screener_data(ticker):
    url = f"https://www.screener.in/company/{ticker.upper()}/"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    values = {}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        rows = soup.select("li.flex.flex-space-between")

        for row in rows:
            spans = row.find_all("span")

            if len(spans) >= 2:
                label = spans[0].get_text(strip=True)
                value = spans[1].get_text(strip=True)

                values[label] = value

    except:
        pass

    return values


# ---------------------------------------------------
# Routes
# ---------------------------------------------------
@app.get("/")
def root():
    return {"message": "Indian Stock Analyzer API Running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analyze")
def analyze(ticker: str):
    try:
        symbol = ticker.upper() + ".NS"

        # --------------------------------
        # Yahoo Finance
        # --------------------------------
        stock = yf.Ticker(symbol)
        info = stock.info

        # --------------------------------
        # Screener Fundamentals
        # --------------------------------
        scr = get_screener_data(ticker)

        current_price = scr.get("Current Price", "N/A")
        market_cap = scr.get("Market Cap", "N/A")

        pe = to_float(scr.get("Stock P/E"))
        pb = to_float(scr.get("Price to book value"))
        roe = to_float(scr.get("ROE"))
        divy = to_float(scr.get("Dividend Yield"))
        book_value = to_float(scr.get("Book Value"))

        # Debt from Yahoo
        debt = to_float(info.get("debtToEquity"))

        # 52 Week High / Low
        hl = scr.get("High / Low", "0 / 0")

        try:
            high52, low52 = hl.split("/")
            high52 = to_float(high52)
            low52 = to_float(low52)
        except:
            high52 = 0
            low52 = 0

        # --------------------------------
        # Yahoo Technicals
        # --------------------------------
        df = yf.download(symbol, period="1y", progress=False)

        if df.empty:
            return {"error": "No historical data found"}

        close = df["Close"].squeeze()

        price = float(close.iloc[-1])
        dma50 = float(close.rolling(50).mean().iloc[-1])
        dma200 = float(close.rolling(200).mean().iloc[-1])
        rsi = float(calculate_rsi(close))

        # --------------------------------
        # Final Score
        # --------------------------------
        score, verdict, horizon, reasons = final_score(
            pe, roe, debt, divy, price, dma50, dma200, rsi
        )

        # --------------------------------
        # Final Output
        # --------------------------------
        return {
            "stock": ticker.upper(),
            "fetch_time": datetime.now().strftime("%d-%b-%Y %I:%M %p"),

            "fundamentals": {
                "Current Price": current_price,
                "Market Cap": market_cap,
                "PE Ratio": safe_round(pe),
                "PB Ratio": safe_round(pb),
                "ROE": safe_round(roe),
                "Debt to Equity": safe_round(debt),
                "Dividend Yield": safe_round(divy),
                "Book Value": safe_round(book_value),
                "52W High": safe_round(high52),
                "52W Low": safe_round(low52),
            },

            "technicals": {
                "Price": safe_round(price),
                "50 DMA": safe_round(dma50),
                "200 DMA": safe_round(dma200),
                "RSI": safe_round(rsi),
            },

            "score": score,
            "verdict": verdict,
            "horizon": horizon,
            "reasons": reasons
        }

    except Exception as e:
        return {"error": str(e)}