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

# --------- CACHE ----------
cache = {}
cache_time = {}
CACHE_TTL = 600 # 10 minutes


# --------- SAFE HELPERS ----------
def safe(v):
    try:
        if v is None:
            return None
        return float(v)
    except:
        return None


def safe_div(a, b):
    if a in [None] or b in [None, 0]:
        return None
    try:
        return a / b
    except:
        return None


def get(df, keys):
    """Find a row in financial statements using fuzzy keys"""
    try:
        if df is None or df.empty:
            return None
        for idx in df.index:
            name = str(idx).lower()
            if any(k in name for k in keys):
                val = df.loc[idx].iloc[0]
                return float(val) if val is not None else None
    except:
        pass
    return None


# --------- FETCH ----------
def fetch(stock):
    try:
        data = stock.history(period="1y")
        if data is not None and not data.empty:
            return data
    except:
        pass
    return None


# --------- RATIO ENGINE ----------
def add_ratio(ratios, name, value, ideal, better, definition, is_pct=False):
    if value is None:
        return 0, 0 # score, total

    # display
    val_disp = round(value, 2)
    if is_pct:
        val_disp_str = f"{val_disp}%"
    else:
        val_disp_str = val_disp

    # evaluate
    good = False
    try:
        if better == "HIGH":
            thr = float(ideal.replace(">", "").replace("%", "").strip())
            good = val_disp > thr
        else:
            thr = float(ideal.replace("<", "").strip())
            good = val_disp < thr
    except:
        good = False

    ratios.append({
        "name": name,
        "value": val_disp_str,
        "ideal": ideal,
        "interpretation": f"{better} is better",
        "definition": definition,
        "status": "GOOD" if good else "WEAK"
    })

    return (1 if good else 0), 1


# --------- ANALYZE ----------
@app.get("/analyze")
def analyze(ticker: str):

    ticker = (ticker or "").upper()
    now = time.time()

    # cache
    if ticker in cache and now - cache_time.get(ticker, 0) < CACHE_TTL:
        return cache[ticker]

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = fetch(stock)
        if hist is None:
            return {"error": "Data busy. Please try again in a few seconds."}

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet
        info = stock.info or {}

        # -------- WATERFALL DATA ----------
        net_income = get(fin, ["net income"])
        ebit = get(fin, ["ebit"])
        revenue = get(fin, ["total revenue"])
        interest = get(fin, ["interest"])

        equity = get(bs, ["equity"])
        debt = get(bs, ["debt", "borrowings"])
        total_assets = get(bs, ["total assets"])
        current_assets = get(bs, ["current assets"])
        current_liab = get(bs, ["current liabilities"])
        inventory = get(bs, ["inventory"])

        # -------- BASIC MARKET ----------
        pe = safe(info.get("trailingPE"))
        pb = safe(info.get("priceToBook"))

        dividend = info.get("dividendYield")
        if dividend is not None:
            dividend = round(dividend * 100, 2) # FIXED (only once)
            if dividend > 50: # sanity cap
                dividend = None

        # -------- RATIOS ----------
        roe = safe_div(net_income, equity)
        if roe is not None:
            roe *= 100

        roce = safe_div(ebit, equity)
        if roce is not None:
            roce *= 100

        net_margin = safe_div(net_income, revenue)
        if net_margin is not None:
            net_margin *= 100

        debt_eq = safe_div(debt, equity)

        interest_cov = safe_div(ebit, interest)

        asset_turnover = safe_div(revenue, total_assets)

        inventory_turnover = safe_div(revenue, inventory)

        current_ratio = safe_div(current_assets, current_liab)

        quick_ratio = safe_div(
            (current_assets - inventory) if current_assets and inventory else None,
            current_liab
        )

        # PEG (approx using earnings growth proxy)
        peg = None
        if pe and roe:
            peg = safe_div(pe, roe)

        # -------- BUILD RATIOS ----------
        ratios = []
        score = 0
        total = 0

        def add(*args, **kwargs):
            nonlocal score, total
            s, t = add_ratio(ratios, *args, **kwargs)
            score += s
            total += t

        add("ROE", roe, ">15%", "HIGH",
            "Return on Equity: how much profit company generates from shareholder money", True)

        add("ROCE", roce, ">18%", "HIGH",
            "Return on Capital: how efficiently total capital is used", True)

        add("Net Profit Margin", net_margin, ">10%", "HIGH",
            "Profit after all expenses from total sales", True)

        add("P/E Ratio", pe, "<25", "LOW",
            "Price vs earnings: lower means cheaper stock")

        add("PEG Ratio", peg, "<1.5", "LOW",
            "Valuation adjusted for growth: lower is better")

        add("Debt to Equity", debt_eq, "<0.5", "LOW",
            "How much debt company has compared to equity")

        add("Interest Coverage", interest_cov, ">3", "HIGH",
            "Ability to pay interest: higher means safer")

        add("Asset Turnover", asset_turnover, ">1", "HIGH",
            "How efficiently assets generate revenue")

        add("Inventory Turnover", inventory_turnover, ">3", "HIGH",
            "How fast inventory is sold")

        add("Current Ratio", current_ratio, ">1.5", "HIGH",
            "Short-term liquidity strength")

        add("Quick Ratio", quick_ratio, ">1", "HIGH",
            "Liquidity excluding inventory")

        # -------- TREND ----------
        trend = price > dma200
        total += 1
        if trend:
            score += 1

        final_score = round((score / total) * 10, 1) if total else 0

        # -------- VERDICT ----------
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
        return {"error": f"Internal error: {str(e)}"}


# --------- SCREENER ----------
STOCKS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK",
    "ITC","LT","SBIN","AXISBANK","HINDUNILVR"
]

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