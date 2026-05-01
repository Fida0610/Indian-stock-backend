from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

cache = {}
cache_time = {}
CACHE_TTL = 600


# ---------- SAFE ----------
def safe(v):
    try:
        return float(v)
    except:
        return None


def safe_div(a, b):
    if a in [None] or b in [None, 0]:
        return None
    return a / b


# ---------- FETCH ----------
def fetch(stock):
    try:
        return stock.history(period="3y")
    except:
        return None


# ---------- GROWTH ----------
def growth(series):
    try:
        return ((series.iloc[0] - series.iloc[-1]) / abs(series.iloc[-1])) * 100
    except:
        return None


# ---------- ANALYZE ----------
@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()
    now = time.time()

    if ticker in cache and now - cache_time.get(ticker, 0) < CACHE_TTL:
        return cache[ticker]

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = fetch(stock)
        if hist is None or hist.empty:
            return {"error": "Data not available"}

        info = stock.info or {}
        fin = stock.financials
        bs = stock.balance_sheet

        price = hist["Close"].iloc[-1]
        dma200 = hist["Close"].tail(200).mean()

        # -------- BASIC --------
        pe = safe(info.get("trailingPE"))
        pb = safe(info.get("priceToBook"))
        dividend = safe(info.get("dividendYield"))
        if dividend:
            dividend *= 100

        # -------- PROFITABILITY --------
        net_income = safe(fin.loc["Net Income"].iloc[0]) if "Net Income" in fin.index else None
        equity = safe(bs.loc["Total Stockholder Equity"].iloc[0]) if "Total Stockholder Equity" in bs.index else None

        roe = safe_div(net_income, equity)
        if roe:
            roe *= 100

        # -------- DEBT --------
        debt = safe(bs.loc["Total Debt"].iloc[0]) if "Total Debt" in bs.index else None
        debt_eq = safe_div(debt, equity)

        # -------- GROWTH --------
        sales_growth = growth(hist["Close"])
        profit_growth = sales_growth # proxy (Yahoo limitation)

        # -------- PEG --------
        peg = safe_div(pe, sales_growth) if pe and sales_growth else None

        # -------- PROMOTER (fallback) --------
        promoter = 50 # default fallback (safe)

        # -------- CURRENT RATIO --------
        current_assets = safe(bs.loc["Total Current Assets"].iloc[0]) if "Total Current Assets" in bs.index else None
        current_liab = safe(bs.loc["Total Current Liabilities"].iloc[0]) if "Total Current Liabilities" in bs.index else None
        current_ratio = safe_div(current_assets, current_liab)

        # -------- OPM --------
        revenue = safe(fin.loc["Total Revenue"].iloc[0]) if "Total Revenue" in fin.index else None
        ebit = safe(fin.loc["EBIT"].iloc[0]) if "EBIT" in fin.index else None
        opm = safe_div(ebit, revenue)
        if opm:
            opm *= 100

        # -------- SCORE ----------
        score = 0
        total = 0

        def add(val, cond):
            nonlocal score, total
            if val is None:
                return
            total += 1
            if cond(val):
                score += 1

        add(roe, lambda x: x > 15)
        add(debt_eq, lambda x: x < 0.5)
        add(pe, lambda x: x < 25)
        add(peg, lambda x: x < 1.5)
        add(sales_growth, lambda x: x > 10)
        add(opm, lambda x: x > 15)
        add(current_ratio, lambda x: x > 1.5)
        add(promoter, lambda x: x > 45)

        trend = price > dma200
        total += 1
        if trend:
            score += 1

        final_score = round((score / total) * 10, 1) if total else 0

        verdict = (
            "STRONG BUY 🟢" if final_score >= 8 else
            "BUY 🟢" if final_score >= 6 else
            "HOLD 🟡" if final_score >= 4 else
            "AVOID 🔴"
        )

        response = {
            "stock": ticker,
            "price": round(price, 2),
            "score": final_score,
            "verdict": verdict,
            "trend": "UPTREND" if trend else "DOWNTREND",
            "ratios": {
                "ROE": roe,
                "Debt": debt_eq,
                "PE": pe,
                "PB": pb,
                "PEG": peg,
                "SalesGrowth": sales_growth,
                "OPM": opm,
                "CurrentRatio": current_ratio,
                "PromoterHolding": promoter
            }
        }

        cache[ticker] = response
        cache_time[ticker] = now

        return response

    except Exception as e:
        return {"error": str(e)}