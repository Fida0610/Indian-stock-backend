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
        return stock.history(period="1y")
    except:
        return None


# ---------- MAIN ANALYSIS ----------
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

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        # ---------- WATERFALL ----------
        net_income = safe(fin.loc["Net Income"].iloc[0]) if "Net Income" in fin.index else None
        equity = safe(bs.loc["Total Stockholder Equity"].iloc[0]) if "Total Stockholder Equity" in bs.index else None
        debt = safe(bs.loc["Total Debt"].iloc[0]) if "Total Debt" in bs.index else None
        ebit = safe(fin.loc["EBIT"].iloc[0]) if "EBIT" in fin.index else None
        revenue = safe(fin.loc["Total Revenue"].iloc[0]) if "Total Revenue" in fin.index else None

        current_assets = safe(bs.loc["Total Current Assets"].iloc[0]) if "Total Current Assets" in bs.index else None
        current_liab = safe(bs.loc["Total Current Liabilities"].iloc[0]) if "Total Current Liabilities" in bs.index else None

        # ---------- RATIOS ----------
        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, equity)
        debt_eq = safe_div(debt, equity)
        current_ratio = safe_div(current_assets, current_liab)

        pe = safe(info.get("trailingPE"))
        pb = safe(info.get("priceToBook"))
        dividend = safe(info.get("dividendYield"))
        if dividend:
            dividend *= 100

        opm = safe_div(ebit, revenue)
        if opm:
            opm *= 100

        # ---------- FORMAT ----------
        def pct(x): return round(x * 100, 2) if x else None
        def num(x): return round(x, 2) if x else None

        ratios = []

        def add(name, value, ideal, better, definition, is_pct=False):
            if value is None:
                return

            val = pct(value) if is_pct else num(value)

            good = (
                (better == "HIGH" and val > float(ideal.strip("> %")))
                or (better == "LOW" and val < float(ideal.strip("< ")))
            )

            ratios.append({
                "name": name,
                "value": f"{val}%" if is_pct else val,
                "ideal": ideal,
                "interpretation": f"{better} is better",
                "definition": definition,
                "status": "GOOD" if good else "WEAK"
            })

        # ---------- ADD RATIOS ----------
        add("ROE", roe, ">15%", "HIGH", "Profit generated per ₹100 shareholder money", True)
        add("ROCE", roce, ">18%", "HIGH", "Efficiency of total capital", True)
        add("Debt to Equity", debt_eq, "<0.5", "LOW", "Debt burden on company")
        add("Current Ratio", current_ratio, ">1.5", "HIGH", "Liquidity strength")
        add("PE Ratio", pe, "<25", "LOW", "Valuation vs earnings")
        add("PB Ratio", pb, "<3", "LOW", "Valuation vs assets")
        add("Dividend Yield", dividend, ">1%", "HIGH", "Cash return", True)
        add("OPM", opm, ">15%", "HIGH", "Operating efficiency", True)

        # ---------- SCORE ----------
        score = sum(1 for r in ratios if r["status"] == "GOOD")
        total = len(ratios) + 1

        trend = price > dma200
        if trend:
            score += 1

        final_score = round((score / total) * 10, 1) if total else 0

        # ---------- VERDICT ----------
        if final_score >= 8:
            verdict = "STRONG BUY 🟢"
        elif final_score >= 6:
            verdict = "BUY 🟢"
        elif final_score >= 4:
            verdict = "HOLD 🟡"
        else:
            verdict = "AVOID 🔴"

        reasons = [f"{r['name']} is {r['status']}" for r in ratios]
        reasons.append("Uptrend" if trend else "Downtrend")

        response = {
            "stock": ticker,
            "price": round(price, 2),
            "score": final_score,
            "verdict": verdict,
            "trend": "UPTREND" if trend else "DOWNTREND",
            "ratios": ratios,
            "reasons": reasons
        }

        cache[ticker] = response
        cache_time[ticker] = now

        return response

    except Exception as e:
        return {"error": str(e)}


# ---------- SCREENER (FIXED) ----------
STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "ITC"]

@app.get("/screener")
def screener():
    results = []

    for s in STOCKS:
        try:
            res = analyze(s)

            if "score" in res and res["score"] >= 6:
                results.append({
                    "stock": s,
                    "score": res["score"],
                    "verdict": res["verdict"]
                })

        except:
            continue

    return {"stocks": results}
