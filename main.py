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

# -------- CACHE --------
cache = {}
cache_time = {}
CACHE_TTL = 600


# -------- SAFE --------
def safe(v):
    try:
        return float(v)
    except:
        return None


def safe_div(a, b):
    if a in [None] or b in [None, 0]:
        return None
    return a / b


def get(df, keys):
    try:
        if df is None or df.empty:
            return None
        for idx in df.index:
            if any(k in str(idx).lower() for k in keys):
                return safe(df.loc[idx].iloc[0])
    except:
        pass
    return None


# -------- FETCH WITH RETRY --------
def fetch_history(stock):
    for i in range(3):
        try:
            data = stock.history(period="6mo")
            if data is not None and not data.empty:
                return data
        except:
            pass
        time.sleep(2)
    return None


def fetch_info(stock):
    for i in range(2):
        try:
            return stock.info
        except:
            time.sleep(1)
    return {}


# -------- ANALYZE --------
@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()
    now = time.time()

    # -------- CACHE --------
    if ticker in cache and now - cache_time.get(ticker, 0) < CACHE_TTL:
        return cache[ticker]

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = fetch_history(stock)
        info = fetch_info(stock)

        # -------- FALLBACK --------
        if hist is None:
            if ticker in cache:
                return {
                    **cache[ticker],
                    "note": "⚠️ Showing cached data (live unavailable)"
                }
            return {"error": "⚠️ Data provider busy. Try again in 30 sec"}

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet

        # -------- WATERFALL DATA --------
        net_income = get(fin, ["net income"])
        ebit = get(fin, ["ebit"])
        revenue = get(fin, ["total revenue"])
        interest = get(fin, ["interest"])

        equity = get(bs, ["equity"])
        debt = get(bs, ["debt"])
        assets = get(bs, ["total assets"])
        current_assets = get(bs, ["current assets"])
        current_liab = get(bs, ["current liabilities"])
        inventory = get(bs, ["inventory"])

        # -------- RATIOS --------
        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, equity)
        npm = safe_div(net_income, revenue)
        debt_eq = safe_div(debt, equity)
        interest_cov = safe_div(ebit, interest)
        asset_turn = safe_div(revenue, assets)
        inventory_turn = safe_div(revenue, inventory)
        current_ratio = safe_div(current_assets, current_liab)
        quick_ratio = safe_div(
            (current_assets - inventory) if current_assets and inventory else None,
            current_liab
        )

        pe = safe(info.get("trailingPE"))
        pb = safe(info.get("priceToBook"))

        dividend = info.get("dividendYield")
        if dividend is not None:
            dividend = round(dividend * 100, 2)
            if dividend > 50:
                dividend = None

        peg = safe_div(pe, roe) if pe and roe else None

        # -------- FORMAT --------
        def pct(x): return round(x * 100, 2) if x else None
        def num(x): return round(x, 2) if x else None

        ratios = []

        def add(name, value, ideal, better, definition, percent=False):
            if value is None:
                return

            val = pct(value) if percent else num(value)

            good = False
            try:
                if better == "HIGH":
                    good = val > float(ideal.replace(">", "").replace("%", ""))
                else:
                    good = val < float(ideal.replace("<", ""))
            except:
                pass

            ratios.append({
                "name": name,
                "value": f"{val}%" if percent else val,
                "ideal": ideal,
                "interpretation": f"{better} is better",
                "definition": definition,
                "status": "GOOD" if good else "WEAK"
            })

        # -------- ADD RATIOS --------
        add("ROE", roe, ">15%", "HIGH", "Profit generated on shareholder money", True)
        add("ROCE", roce, ">18%", "HIGH", "Capital efficiency", True)
        add("Net Profit Margin", npm, ">10%", "HIGH", "Profit after expenses", True)
        add("P/E Ratio", pe, "<25", "LOW", "Valuation vs earnings")
        add("PEG Ratio", peg, "<1.5", "LOW", "Valuation adjusted for growth")
        add("Debt to Equity", debt_eq, "<0.5", "LOW", "Debt burden")
        add("Interest Coverage", interest_cov, ">3", "HIGH", "Interest safety")
        add("Asset Turnover", asset_turn, ">1", "HIGH", "Revenue efficiency")
        add("Inventory Turnover", inventory_turn, ">3", "HIGH", "Stock efficiency")
        add("Current Ratio", current_ratio, ">1.5", "HIGH", "Liquidity")
        add("Quick Ratio", quick_ratio, ">1", "HIGH", "Liquidity without inventory")

        # -------- SCORE --------
        score = sum(1 for r in ratios if r["status"] == "GOOD")
        total = len(ratios) + 1

        trend = price > dma200
        if trend:
            score += 1

        final_score = round((score / total) * 10, 1)

        # -------- VERDICT --------
        verdict = (
            "STRONG BUY 🟢" if final_score >= 8 else
            "BUY 🟢" if final_score >= 6 else
            "HOLD 🟡" if final_score >= 4 else
            "AVOID 🔴"
        )

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
        return {"error": "Something went wrong. Please try again."}
