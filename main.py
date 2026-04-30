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

# ---------------- DEFINITIONS ----------------
DEFINITIONS = {
    "ROE": "Return on Equity - Profit generated from shareholders' money",
    "ROCE": "Return on Capital Employed - Efficiency of capital usage",
    "Debt": "Debt to Equity - Financial leverage (lower is better)",
    "CurrentRatio": "Liquidity measure - ability to pay short-term liabilities",
    "FCF": "Free Cash Flow - cash available after expenses",
}

# ---------------- SAFE FUNCTIONS ----------------

def safe_div(a, b):
    if a is None or b is None:
        return None
    try:
        if b == 0:
            return None
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


# ---------------- RETRY FETCH ----------------

def fetch_with_retry(stock):
    for _ in range(3):
        try:
            data = stock.history(period="1y")
            if data is not None and not data.empty:
                return data
        except:
            pass
        time.sleep(2 + random.random())
    return None


# ---------------- WATERFALL FETCH ----------------

def get_value(df, keywords):
    try:
        if df is None or df.empty:
            return None

        for idx in df.index:
            name = str(idx).lower()
            if any(k in name for k in keywords):
                val = df.loc[idx].iloc[0]
                if val is not None:
                    return float(val)
    except:
        pass
    return None


# ---------------- ANALYZE ----------------

@app.get("/analyze")
def analyze(ticker: str):

    ticker = ticker.upper()

    # -------- CACHE --------
    if ticker in cache:
        return cache[ticker]

    try:
        time.sleep(1) # prevent rate limit

        stock = yf.Ticker(ticker + ".NS")

        hist = fetch_with_retry(stock)

        if hist is None:
            return {"error": "Data source busy. Try again."}

        price = float(hist["Close"].iloc[-1])
        dma50 = float(hist["Close"].tail(50).mean())
        dma200 = float(hist["Close"].tail(200).mean())

        # -------- FINANCIALS --------
        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        net_income = get_value(fin, ["net income"])
        ebit = get_value(fin, ["ebit"])

        equity = get_value(bs, ["equity"])
        debt = get_value(bs, ["debt", "borrowings"])
        total_assets = get_value(bs, ["total assets"])

        current_assets = get_value(bs, ["current assets"])
        current_liabilities = get_value(bs, ["current liabilities"])

        op_cf = get_value(cf, ["operating cash"])
        capex = get_value(cf, ["capital expenditure"])

        if capex is not None:
            capex = abs(capex)

        # -------- CALCULATIONS (SAFE) --------
        capital_employed = safe_sub(total_assets, current_liabilities)

        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, capital_employed)
        debt_equity = safe_div(debt, equity)
        current_ratio = safe_div(current_assets, current_liabilities)
        fcf = safe_sub(op_cf, capex)

        # -------- FORMAT RATIOS --------
        def pct(x):
            return round(x * 100, 2) if x is not None else None

        def num(x):
            return round(x, 2) if x is not None else None

        ratios = {
            "ROE": pct(roe),
            "ROCE": pct(roce),
            "Debt": num(debt_equity),
            "CurrentRatio": num(current_ratio),
            "FCF": num(fcf),
        }

        # -------- SCORING (IGNORE NONE) --------
        score = 0
        total = 0
        reasons = []

        def check(value, condition, text):
            nonlocal score, total
            if value is not None:
                total += 1
                if condition:
                    score += 1
                    reasons.append(f"{text} ✅")
                else:
                    reasons.append(f"{text} ❌")

        check(ratios["ROE"], ratios["ROE"] and ratios["ROE"] > 15, "ROE > 15")
        check(ratios["ROCE"], ratios["ROCE"] and ratios["ROCE"] > 18, "ROCE > 18")
        check(ratios["Debt"], ratios["Debt"] is not None and ratios["Debt"] < 0.5, "Low Debt")
        check(ratios["CurrentRatio"], ratios["CurrentRatio"] and ratios["CurrentRatio"] > 1.5, "Good Liquidity")
        check(ratios["FCF"], ratios["FCF"] and ratios["FCF"] > 0, "Positive Cash Flow")
        check(price, price > dma200, "Above 200DMA")

        final_score = round(score / total, 2) if total > 0 else 0

        # -------- VERDICT --------
        if final_score >= 0.8:
            verdict = "STRONG BUY 🟢"
        elif final_score >= 0.6:
            verdict = "BUY 🟢"
        elif final_score >= 0.4:
            verdict = "HOLD 🟡"
        else:
            verdict = "AVOID 🔴"

        response = {
            "stock": ticker,
            "price": round(price, 2),
            "score": final_score,
            "verdict": verdict,
            "ratios": ratios,
            "definitions": DEFINITIONS,
            "technical": {
                "Above50DMA": price > dma50,
                "Above200DMA": price > dma200
            },
            "reasons": reasons
        }

        # -------- CACHE SAVE --------
        cache[ticker] = response

        return response

    except Exception as e:
        return {"error": str(e)}