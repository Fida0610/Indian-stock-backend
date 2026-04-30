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

# ---------------- CACHE ----------------
cache = {}
cache_time = {}
CACHE_TTL = 300

# ---------------- SAFE FUNCTIONS ----------------
def safe_div(a, b):
    if a is None or b in [None, 0]:
        return None
    try:
        return a / b
    except:
        return None

def safe_sub(a, b):
    if a is None or b is None:
        return None
    try:
        return a - b
    except:
        return None

def fetch(stock):
    for _ in range(5):
        try:
            data = stock.history(period="1y")
            if not data.empty:
                return data
        except:
            pass
        time.sleep(3 + random.random())
    return None

def get(df, keys):
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

# ---------------- ANALYZE ----------------
@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()
    now = time.time()

    # cache
    if ticker in cache and now - cache_time.get(ticker, 0) < CACHE_TTL:
        return cache[ticker]

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = fetch(stock)
        if hist is None:
            return {"error": "Data not available. Try later."}

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet
        info = stock.info or {}

        # safe extraction
        net_income = get(fin, ["net income"])
        ebit = get(fin, ["ebit"])
        equity = get(bs, ["equity"])
        debt = get(bs, ["debt", "borrowings"])
        total_assets = get(bs, ["total assets"])
        current_liabilities = get(bs, ["current liabilities"])

        # safe calculations
        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, safe_sub(total_assets, current_liabilities))
        debt_eq = safe_div(debt, equity)

        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        dividend = info.get("dividendYield")

        if dividend is not None:
            dividend = dividend * 100

        # store ratios safely
        raw = {
            "ROE": roe * 100 if roe is not None else None,
            "ROCE": roce * 100 if roce is not None else None,
            "Debt": debt_eq,
            "PE": pe,
            "PB": pb,
            "Dividend": dividend
        }

        ratios = []
        score = 0
        total = 0

        def check(name, val, cond, ideal, better, definition, percent=False):
            nonlocal score, total

            if val is None:
                return

            total += 1

            try:
                good = cond(val)
            except:
                good = False

            if good:
                score += 1

            display = f"{round(val,2)}%" if percent else round(val,2)

            ratios.append({
                "name": name,
                "value": display,
                "ideal": ideal,
                "definition": definition,
                "interpretation": f"{better} is better",
                "status": "GOOD" if good else "BAD"
            })

        # checks
        check("ROE", raw["ROE"], lambda x: x > 15, ">15%", "higher",
              "Profit per ₹100 shareholder investment", True)

        check("ROCE", raw["ROCE"], lambda x: x > 18, ">18%", "higher",
              "Capital efficiency", True)

        check("Debt", raw["Debt"], lambda x: x < 0.5, "<0.5", "lower",
              "Debt burden")

        check("PE", raw["PE"], lambda x: x < 25, "<25", "lower",
              "Valuation vs earnings")

        check("PB", raw["PB"], lambda x: x < 3, "<3", "lower",
              "Valuation vs assets")

        check("Dividend", raw["Dividend"], lambda x: x > 1, ">1%", "higher",
              "Cash return", True)

        # trend
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
            "ratios": ratios,
            "reasons": [f"{r['name']} is {r['status']}" for r in ratios]
        }

        cache[ticker] = response
        cache_time[ticker] = now

        return response

    except Exception as e:
        return {"error": f"Internal error: {str(e)}"}
