# main.py
# FINAL MAIN.PY V3 (ZERO FIXED + STABLE + RAW CALCULATIONS)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import yfinance as yf
import math
import time

app = FastAPI(title="Indian Stock Analyzer FINAL V3")

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
CACHE_SECONDS = 600


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


def safe_num(v, digits=2, allow_zero=False):
    try:
        if v is None:
            return "N/A"

        if isinstance(v, float) and math.isnan(v):
            return "N/A"

        if float(v) == 0 and not allow_zero:
            return "N/A"

        return round(float(v), digits)
    except:
        return "N/A"


def pct(a, b):
    try:
        if b == 0:
            return 0
        return (a / b) * 100
    except:
        return 0


def first(series):
    try:
        return to_float(series.iloc[0])
    except:
        return 0


# ---------------------------------------------------
# SYMBOL
# ---------------------------------------------------
def resolve_symbol(txt):
    raw = txt.strip().upper()
    return raw.replace(" ", "")


# ---------------------------------------------------
# SCORE
# ---------------------------------------------------
def get_score(pe, pb, roe, debt_equity, current_ratio):
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

    if debt_equity >= 0 and debt_equity < 1:
        score += 2
        reasons.append("Low debt")

    if current_ratio > 1:
        score += 1
        reasons.append("Healthy liquidity")

    if score >= 7:
        return score, "BUY 🟢", "3-5 Years", reasons
    elif score >= 4:
        return score, "HOLD 🟡", "1-3 Years", reasons
    else:
        return score, "AVOID 🔴", "Wait", reasons


# ---------------------------------------------------
# ROUTES
# ---------------------------------------------------
@app.get("/")
def root():
    return {"message": "API Running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------
@app.get("/analyze")
def analyze(ticker: str):

    try:
        code = resolve_symbol(ticker)

        # CACHE
        if code in CACHE:
            c = CACHE[code]
            if time.time() - c["time"] < CACHE_SECONDS:
                c["data"]["fetch_time"] = datetime.now().strftime("%d-%b-%Y %I:%M %p")
                return c["data"]

        stock = yf.Ticker(code + ".NS")

        # ---------------- PRICE ----------------
        hist = stock.history(period="1y")

        if hist.empty:
            return {"error": "No data"}

        close = hist["Close"]
        price = float(close.iloc[-1])

        # ---------------- RAW DATA ----------------
        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        revenue = net_income = ebit = interest = 0
        equity = debt = current_assets = current_liabilities = total_assets = 0
        op_cf = capex = 0

        # INCOME
        try:
            for idx in fin.index:
                n = str(idx).lower()
                if "revenue" in n:
                    revenue = first(fin.loc[idx])
                if "net income" in n:
                    net_income = first(fin.loc[idx])
                if "ebit" in n:
                    ebit = first(fin.loc[idx])
                if "interest expense" in n:
                    interest = abs(first(fin.loc[idx]))
        except:
            pass

        # BALANCE SHEET
        try:
            for idx in bs.index:
                n = str(idx).lower()

                if "equity" in n:
                    equity = first(bs.loc[idx])

                if "current assets" in n:
                    current_assets = first(bs.loc[idx])

                if "current liabilities" in n:
                    current_liabilities = first(bs.loc[idx])

                if "total assets" in n:
                    total_assets = first(bs.loc[idx])

                if (
                    "debt" in n
                    or "borrowings" in n
                    or "lease" in n
                ):
                    debt += first(bs.loc[idx])
        except:
            pass

        # CASH FLOW
        try:
            for idx in cf.index:
                n = str(idx).lower()
                if "operating cash flow" in n:
                    op_cf = first(cf.loc[idx])
                if "capital expenditure" in n:
                    capex = abs(first(cf.loc[idx]))
        except:
            pass

        # MARKET DATA
        shares = 0
        try:
            info = stock.info
            shares = to_float(info.get("sharesOutstanding"))
        except:
            pass

        # ---------------- RATIOS ----------------
        eps = net_income / shares if shares else 0
        book_ps = equity / shares if shares else 0

        pe = price / eps if eps > 0 else 0
        pb = price / book_ps if book_ps > 0 else 0

        roe = pct(net_income, equity)
        roce = pct(ebit, (total_assets - current_liabilities))
        debt_equity = debt / equity if equity else 0
        current_ratio = current_assets / current_liabilities if current_liabilities else 0

        op_margin = pct(ebit, revenue)
        net_margin = pct(net_income, revenue)

        fcf = op_cf - capex if op_cf else 0
        interest_cov = ebit / interest if interest else 0

        # SCORE
        score, verdict, horizon, reasons = get_score(
            pe, pb, roe, debt_equity, current_ratio
        )

        data = {
            "stock": code,
            "fetch_time": datetime.now().strftime("%d-%b-%Y %I:%M %p"),
            "score": score,
            "verdict": verdict,
            "horizon": horizon,
            "reasons": reasons,

            "fundamentals": {
                "Current Price": safe_num(price, allow_zero=True),
                "PE Ratio": safe_num(pe),
                "PB Ratio": safe_num(pb),
                "ROE": safe_num(roe),
                "Debt to Equity": safe_num(debt_equity, allow_zero=True),
            },

            "ratios": {
                "ROE": safe_num(roe),
                "ROCE": safe_num(roce),
                "DebtEquity": safe_num(debt_equity, allow_zero=True),
                "CurrentRatio": safe_num(current_ratio),
                "OperatingMargin": safe_num(op_margin),
                "NetMargin": safe_num(net_margin),
                "FCF": safe_num(fcf, allow_zero=True),
                "InterestCoverage": safe_num(interest_cov),
            }
        }

        CACHE[code] = {"time": time.time(), "data": data}

        return data

    except Exception as e:
        return {"error": str(e)}