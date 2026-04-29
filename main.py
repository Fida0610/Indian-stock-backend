from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import time
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- HELPERS ----------------

def pct(a, b):
    try:
        if not a or not b:
            return None
        return (a / b) * 100
    except:
        return None

def get_latest(series):
    try:
        return float(series.iloc[0])
    except:
        return None

# ---------------- ANALYZE ----------------

@app.get("/analyze")
def analyze(ticker: str):

    try:
        stock = yf.Ticker(ticker + ".NS")

        hist = stock.history(period="1y")
        if hist.empty:
            return {"error": "No price data"}

        price = float(hist["Close"].iloc[-1])
        dma200 = float(hist["Close"].tail(200).mean())

        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        net_income = ebit = equity = debt = 0
        current_assets = current_liabilities = total_assets = 0
        op_cf = capex = 0

        for idx in fin.index:
            n = str(idx).lower()
            if "net income" in n:
                net_income = get_latest(fin.loc[idx])
            if "ebit" in n:
                ebit = get_latest(fin.loc[idx])

        for idx in bs.index:
            n = str(idx).lower()
            if "equity" in n:
                equity = get_latest(bs.loc[idx])
            if "current assets" in n:
                current_assets = get_latest(bs.loc[idx])
            if "current liabilities" in n:
                current_liabilities = get_latest(bs.loc[idx])
            if "total assets" in n:
                total_assets = get_latest(bs.loc[idx])
            if "debt" in n or "borrowings" in n:
                d = get_latest(bs.loc[idx])
                if d:
                    debt += d

        for idx in cf.index:
            n = str(idx).lower()
            if "operating cash flow" in n:
                op_cf = get_latest(cf.loc[idx])
            if "capital expenditure" in n:
                capex = abs(get_latest(cf.loc[idx]))

        roe = pct(net_income, equity)
        roce = pct(ebit, (total_assets - current_liabilities))
        debt_equity = debt / equity if equity else None
        current_ratio = current_assets / current_liabilities if current_liabilities else None
        fcf = op_cf - capex if op_cf else None

        score = 0
        if roe and roe > 15: score += 2
        if roce and roce > 18: score += 2
        if debt_equity is not None and debt_equity < 0.5: score += 2
        if current_ratio and current_ratio > 1.5: score += 1
        if fcf and fcf > 0: score += 1
        if price > dma200: score += 2

        if score >= 8:
            verdict = "BUY 🟢"
        elif score >= 5:
            verdict = "HOLD 🟡"
        else:
            verdict = "AVOID 🔴"

        return {
            "stock": ticker.upper(),
            "score": score,
            "verdict": verdict,
            "ratios": {
                "ROE": roe,
                "ROCE": roce,
                "Debt": debt_equity,
                "CurrentRatio": current_ratio,
                "FCF": fcf
            }
        }

    except Exception as e:
        return {"error": str(e)}

# ---------------- SCREENER ----------------

NIFTY50 = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK",
    "LT","SBIN","ITC","HINDUNILVR","KOTAKBANK",
    "AXISBANK","ASIANPAINT","BAJFINANCE","MARUTI",
    "SUNPHARMA","TITAN","ULTRACEMCO","WIPRO"
]

def calc_score(r, t):
    roe, roce, debt, cr, fcf = r["ROE"], r["ROCE"], r["Debt"], r["CurrentRatio"], r["FCF"]
    s = 0

    if t == "wealth":
        if roe and roe > 15: s += 2
        if roce and roce > 18: s += 2
        if debt is not None and debt < 0.5: s += 2
        if cr and cr > 1.5: s += 1
        if fcf and fcf > 0: s += 1

    elif t == "multibagger":
        if roe and roe > 18: s += 2
        if roce and roce > 20: s += 2
        if debt is not None and debt < 0.3: s += 2
        if fcf and fcf > 0: s += 1

    elif t == "balanced":
        if roe and roe > 15: s += 2
        if roce and roce > 18: s += 2
        if debt is not None and debt < 0.4: s += 2
        if cr and cr > 1.2: s += 1

    return s

def verdict_fn(s):
    if s >= 7: return "BUY 🟢"
    elif s >= 4: return "HOLD 🟡"
    else: return "AVOID 🔴"

@app.get("/screener")
def screener(type: str):

    res = []

    for stock in NIFTY50:
        try:
            d = analyze(stock)
            if "ratios" not in d:
                continue

            s = calc_score(d["ratios"], type)

            res.append({
                "stock": stock,
                "score": s,
                "verdict": verdict_fn(s)
            })

            time.sleep(1)

        except:
            continue

    return {"stocks": sorted(res, key=lambda x: x["score"], reverse=True)}