# main.py
# FINAL PERFECTED MAIN.PY V2
# Stable Render + Raw Calculated Ratios + Smart Debt/Equity Detection
# Replace FULL existing main.py with this code

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import yfinance as yf
import math
import time

app = FastAPI(title="Indian Stock Analyzer PRO V2")

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
CACHE_SECONDS = 600   # 10 mins


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
# SYMBOL MAP
# ---------------------------------------------------
def resolve_symbol(txt):
    raw = txt.strip().upper()
    no_space = raw.replace(" ", "")

    alias = {
        "TATA STEEL": "TATASTEEL",
        "TATASTEELS": "TATASTEEL",
        "BATA": "BATAINDIA",
        "INFOSYS": "INFY",
        "SBI": "SBIN",
        "HDFC BANK": "HDFCBANK",
        "ICICI BANK": "ICICIBANK",
        "HUL": "HINDUNILVR",
        "L&T": "LT",
    }

    return alias.get(raw, no_space)


# ---------------------------------------------------
# SCORE ENGINE
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

    if debt_equity > 0 and debt_equity < 1:
        score += 2
        reasons.append("Low debt")

    if current_ratio > 1:
        score += 1
        reasons.append("Healthy liquidity")

    if score >= 7:
        verdict = "BUY 🟢"
        horizon = "3 to 5 Years"
    elif score >= 4:
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
    return {"message": "Indian Stock Analyzer PRO V2 Running"}


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
                c["data"]["fetch_time"] = datetime.now().strftime(
                    "%d-%b-%Y %I:%M %p"
                )
                return c["data"]

        symbol = code + ".NS"
        stock = yf.Ticker(symbol)

        # ---------------------------------------------------
        # PRICE DATA
        # ---------------------------------------------------
        hist = stock.history(period="1y")

        if hist.empty:
            return {"error": "No market data found"}

        close = hist["Close"]

        price = first(close.tail(1))
        high_52 = float(close.max())
        low_52 = float(close.min())

        dma50 = float(close.tail(50).mean()) if len(close) >= 50 else price
        dma200 = float(close.tail(200).mean()) if len(close) >= 200 else price

        # ---------------------------------------------------
        # RAW FINANCIAL DATA
        # ---------------------------------------------------
        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        revenue = net_income = ebit = interest_exp = 0
        equity = debt = current_assets = current_liabilities = total_assets = 0
        operating_cf = capex = 0

        # ---------------- Income Statement ----------------
        try:
            for idx in fin.index:
                n = str(idx).lower()

                if "revenue" in n:
                    revenue = first(fin.loc[idx])

                if "net income" in n:
                    net_income = first(fin.loc[idx])

                if "ebit" in n or "operating income" in n:
                    ebit = first(fin.loc[idx])

                if "interest expense" in n:
                    interest_exp = abs(first(fin.loc[idx]))
        except:
            pass

        # ---------------- Balance Sheet ----------------
        try:
            for idx in bs.index:
                n = str(idx).lower()

                # Equity
                if (
                    "stockholders equity" in n
                    or "total equity" in n
                    or "shareholders equity" in n
                ):
                    equity = first(bs.loc[idx])

                # Assets / Liabilities
                if "current assets" in n:
                    current_assets = first(bs.loc[idx])

                if "current liabilities" in n:
                    current_liabilities = first(bs.loc[idx])

                if "total assets" in n:
                    total_assets = first(bs.loc[idx])

                # Smart Debt Detection
                if (
                    "total debt" in n
                    or "long term debt" in n
                    or "current debt" in n
                    or "borrowings" in n
                    or "lease obligation" in n
                    or "short term debt" in n
                ):
                    debt += first(bs.loc[idx])

        except:
            pass

        # ---------------- Cash Flow ----------------
        try:
            for idx in cf.index:
                n = str(idx).lower()

                if "operating cash flow" in n:
                    operating_cf = first(cf.loc[idx])

                if "capital expenditure" in n:
                    capex = abs(first(cf.loc[idx]))
        except:
            pass

        # ---------------------------------------------------
        # EXTRA INFO
        # ---------------------------------------------------
        shares = divy = 0

        try:
            info = stock.info
            shares = to_float(info.get("sharesOutstanding"))
            divy = to_float(info.get("dividendYield")) * 100
        except:
            pass

        # ---------------------------------------------------
        # RAW CALCULATED RATIOS
        # ---------------------------------------------------
        eps = (net_income / shares) if shares > 0 else 0
        book_value_ps = (equity / shares) if shares > 0 else 0

        pe = (price / eps) if eps > 0 else 0
        pb = (price / book_value_ps) if book_value_ps > 0 else 0

        roe = pct(net_income, equity)
        roce = pct(ebit, (total_assets - current_liabilities))
        debt_equity = (debt / equity) if equity > 0 else 0
        current_ratio = (
            current_assets / current_liabilities
            if current_liabilities > 0 else 0
        )

        op_margin = pct(ebit, revenue)
        net_margin = pct(net_income, revenue)

        fcf = operating_cf - capex if operating_cf else 0

        interest_cov = (
            ebit / interest_exp
            if interest_exp > 0 else 0
        )

        # Growth
        sales_growth = profit_growth = 0

        try:
            if fin.shape[1] >= 2:
                rev_now = revenue
                rev_prev = first(fin.iloc[:, 1])

                ni_now = net_income
                ni_prev = first(fin.iloc[:, 1])

                sales_growth = pct(
                    rev_now - rev_prev,
                    rev_prev
                )

                profit_growth = pct(
                    ni_now - ni_prev,
                    ni_prev
                )
        except:
            pass

        peg = pe / profit_growth if profit_growth > 0 else 0

        # ---------------------------------------------------
        # SCORE
        # ---------------------------------------------------
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
                "Current Price": safe_num(price),
                "PE Ratio": safe_num(pe),
                "PB Ratio": safe_num(pb),
                "ROE": safe_num(roe),
                "Debt to Equity": safe_num(debt_equity),
                "Dividend Yield": safe_num(divy),
                "52W High": safe_num(high_52),
                "52W Low": safe_num(low_52),
            },

            "ratios": {
                "PB Ratio": {"value": safe_num(pb), "meaning": "Price vs book", "ideal": "Lower better"},
                "PEG": {"value": safe_num(peg), "meaning": "PE adjusted growth", "ideal": "Below 1 good"},
                "ROE": {"value": safe_num(roe), "meaning": "Return on equity", "ideal": "Higher better"},
                "ROCE": {"value": safe_num(roce), "meaning": "Return on capital", "ideal": "Higher better"},
                "DebtEquity": {"value": safe_num(debt_equity), "meaning": "Debt burden", "ideal": "Lower better"},
                "CurrentRatio": {"value": safe_num(current_ratio), "meaning": "Liquidity", "ideal": "Above 1 good"},
                "OperatingMargin": {"value": safe_num(op_margin), "meaning": "Operating profit %", "ideal": "Higher better"},
                "NetMargin": {"value": safe_num(net_margin), "meaning": "Net profit %", "ideal": "Higher better"},
                "SalesGrowth": {"value": safe_num(sales_growth), "meaning": "Revenue growth %", "ideal": "Higher better"},
                "ProfitGrowth": {"value": safe_num(profit_growth), "meaning": "Profit growth %", "ideal": "Higher better"},
                "FCF": {"value": safe_num(fcf), "meaning": "Free cash flow", "ideal": "Positive good"},
                "DividendYield": {"value": safe_num(divy), "meaning": "Dividend return", "ideal": "Moderate good"},
                "InterestCoverage": {"value": safe_num(interest_cov), "meaning": "Interest servicing ability", "ideal": "Higher better"},
                "50 DMA": {"value": safe_num(dma50), "meaning": "50 day average", "ideal": "Price above positive"},
                "200 DMA": {"value": safe_num(dma200), "meaning": "200 day average", "ideal": "Price above strong"},
            }
        }

        CACHE[code] = {
            "time": time.time(),
            "data": data
        }

        return data

    except Exception as e:
        return {"error": str(e)}