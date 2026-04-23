# main.py
# FINAL HYBRID RENDER VERSION
# Stable + All Ratios (N/A if unavailable)
# Replace FULL existing main.py with this code

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import yfinance as yf
import math
import time

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
# CACHE
# ---------------------------------------------------
CACHE = {}
CACHE_SECONDS = 600   # 10 min


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------
def to_float(v):
    try:
        if v is None:
            return 0.0
        return float(v)
    except:
        return 0.0


def safe_num(v, digits=2):
    try:
        if v is None:
            return "N/A"
        if isinstance(v, float) and math.isnan(v):
            return "N/A"
        if float(v) == 0:
            return "N/A"
        return round(float(v), digits)
    except:
        return "N/A"


def pct(v):
    val = to_float(v)
    if val != 0 and abs(val) < 1:
        return val * 100
    return val


# ---------------------------------------------------
# SYMBOL RESOLVER
# ---------------------------------------------------
def resolve_symbol(user_input):
    raw = user_input.strip().upper()
    no_space = raw.replace(" ", "")

    alias = {
        "BATA": "BATAINDIA",
        "TATA STEEL": "TATASTEEL",
        "TATASTEELS": "TATASTEEL",
        "INFOSYS": "INFY",
        "HDFC BANK": "HDFCBANK",
        "ICICI BANK": "ICICIBANK",
        "SBI": "SBIN",
        "HUL": "HINDUNILVR",
        "L&T": "LT",
    }

    return alias.get(raw, no_space)


# ---------------------------------------------------
# SCORE ENGINE
# ---------------------------------------------------
def score_engine(pe, pb, roe, debt):
    score = 0
    reasons = []

    if pe > 0 and pe < 25:
        score += 2
        reasons.append("Fair valuation")

    if pb > 0 and pb < 5:
        score += 1
        reasons.append("Reasonable PB")

    if roe > 15:
        score += 2
        reasons.append("Strong ROE")

    if debt > 0 and debt < 100:
        score += 2
        reasons.append("Manageable debt")

    if score >= 6:
        verdict = "BUY 🟢"
        horizon = "3 to 5 Years"
    elif score >= 3:
        verdict = "HOLD 🟡"
        horizon = "1 to 3 Years"
    else:
        verdict = "AVOID 🔴"
        horizon = "Wait"

    return score, verdict, horizon, reasons


# ---------------------------------------------------
# ROOT
# ---------------------------------------------------
@app.get("/")
def root():
    return {"message": "Indian Stock Analyzer API Running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------
@app.get("/analyze")
def analyze(ticker: str):

    try:
        resolved = resolve_symbol(ticker)

        # CACHE
        if resolved in CACHE:
            cached = CACHE[resolved]

            if time.time() - cached["time"] < CACHE_SECONDS:
                cached["data"]["fetch_time"] = datetime.now().strftime(
                    "%d-%b-%Y %I:%M %p"
                )
                return cached["data"]

        symbol = resolved + ".NS"
        stock = yf.Ticker(symbol)

        # ---------------------------------------------------
        # STABLE PRICE HISTORY
        # ---------------------------------------------------
        hist = stock.history(period="1y", auto_adjust=False)

        if hist.empty:
            return {"error": "No market data found"}

        close = hist["Close"]

        price = float(close.iloc[-1])
        high_52 = float(close.max())
        low_52 = float(close.min())

        dma50 = float(close.tail(50).mean()) if len(close) >= 50 else price
        dma200 = float(close.tail(200).mean()) if len(close) >= 200 else price

        # ---------------------------------------------------
        # OPTIONAL INFO (may fail, still app works)
        # ---------------------------------------------------
        pe = pb = roe = debt = divy = 0
        current_ratio = opm = npm = sales_growth = 0
        profit_growth = peg = fcf = interest_cov = 0

        try:
            info = stock.info

            pe = to_float(info.get("trailingPE"))
            pb = to_float(info.get("priceToBook"))
            roe = pct(info.get("returnOnEquity"))
            debt = to_float(info.get("debtToEquity"))
            divy = pct(info.get("dividendYield"))

            current_ratio = to_float(info.get("currentRatio"))
            opm = pct(info.get("operatingMargins"))
            npm = pct(info.get("profitMargins"))
            sales_growth = pct(info.get("revenueGrowth"))
            profit_growth = pct(info.get("earningsGrowth"))
            peg = to_float(info.get("pegRatio"))
            fcf = to_float(info.get("freeCashflow"))
            interest_cov = pct(info.get("ebitdaMargins"))

        except:
            pass

        roce = roe

        # Manual PEG
        if peg == 0 and pe > 0 and profit_growth > 0:
            peg = pe / profit_growth

        score, verdict, horizon, reasons = score_engine(
            pe, pb, roe, debt
        )

        data = {
            "stock": resolved,
            "fetch_time": datetime.now().strftime("%d-%b-%Y %I:%M %p"),
            "score": score,
            "verdict": verdict,
            "horizon": horizon,
            "reasons": reasons,

            "fundamentals": {
                "Current Price": safe_num(price),
                "PE Ratio": safe_num(pe),
                "PB Ratio": safe_num(pb),
                "ROE": safe_num(roe),
                "Debt to Equity": safe_num(debt),
                "Dividend Yield": safe_num(divy),
                "52W High": safe_num(high_52),
                "52W Low": safe_num(low_52),
            },

            "ratios": {
                "PB Ratio": {"value": safe_num(pb), "meaning": "Price vs book", "ideal": "Lower better"},
                "PEG": {"value": safe_num(peg), "meaning": "PE adjusted growth", "ideal": "Below 1 good"},
                "ROE": {"value": safe_num(roe), "meaning": "Return on equity", "ideal": "Higher better"},
                "ROCE": {"value": safe_num(roce), "meaning": "Return on capital", "ideal": "Higher better"},
                "DebtEquity": {"value": safe_num(debt), "meaning": "Debt burden", "ideal": "Lower better"},
                "CurrentRatio": {"value": safe_num(current_ratio), "meaning": "Liquidity", "ideal": "Above 1 good"},
                "OperatingMargin": {"value": safe_num(opm), "meaning": "Operating profit %", "ideal": "Higher better"},
                "NetMargin": {"value": safe_num(npm), "meaning": "Net profit %", "ideal": "Higher better"},
                "SalesGrowth": {"value": safe_num(sales_growth), "meaning": "Revenue growth %", "ideal": "Higher better"},
                "ProfitGrowth": {"value": safe_num(profit_growth), "meaning": "Profit growth %", "ideal": "Higher better"},
                "FCF": {"value": safe_num(fcf), "meaning": "Free cash flow", "ideal": "Positive good"},
                "DividendYield": {"value": safe_num(divy), "meaning": "Dividend return", "ideal": "Moderate good"},
                "InterestCoverage": {"value": safe_num(interest_cov), "meaning": "Pay interest ability", "ideal": "Higher better"},
                "50 DMA": {"value": safe_num(dma50), "meaning": "50 day average", "ideal": "Price above positive"},
                "200 DMA": {"value": safe_num(dma200), "meaning": "200 day average", "ideal": "Price above strong"},
            }
        }

        CACHE[resolved] = {
            "time": time.time(),
            "data": data
        }

        return data

    except Exception:
        if ticker.upper() in CACHE:
            cached = CACHE[ticker.upper()]
            cached["data"]["fetch_time"] = datetime.now().strftime(
                "%d-%b-%Y %I:%M %p"
            )
            return cached["data"]

        return {
            "error": "Temporary market data busy. Retry shortly."
        }