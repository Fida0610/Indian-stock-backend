# main.py
# FINAL SMART VERSION WITH MANUAL CURRENT RATIO
# Replace your FULL existing main.py with this code

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from bs4 import BeautifulSoup
import yfinance as yf
import requests
import math

app = FastAPI(title="Indian Stock Analyzer API Smart")

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
# HELPERS
# ---------------------------------------------------
def to_float(val):
    try:
        if val is None:
            return 0.0
        val = str(val).replace(",", "").replace("%", "").replace("₹", "").strip()
        return float(val)
    except:
        return 0.0


def safe_num(val, digits=2):
    try:
        if val is None:
            return "N/A"
        if isinstance(val, float) and math.isnan(val):
            return "N/A"
        if float(val) == 0:
            return "N/A"
        return round(float(val), digits)
    except:
        return "N/A"


def percent_to_number(val):
    v = to_float(val)
    if v != 0 and abs(v) < 1:
        return v * 100
    return v


def first_non_zero(*vals):
    for v in vals:
        n = to_float(v)
        if n != 0:
            return n
    return 0


# ---------------------------------------------------
# AUTO SYMBOL
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

    if raw in alias:
        return alias[raw]

    return no_space


# ---------------------------------------------------
# SCREENER
# ---------------------------------------------------
def get_screener_data(symbol):
    url = f"https://www.screener.in/company/{symbol}/"
    headers = {"User-Agent": "Mozilla/5.0"}

    values = {}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        rows = soup.select("li.flex.flex-space-between")

        for row in rows:
            spans = row.find_all("span")
            if len(spans) >= 2:
                label = spans[0].get_text(strip=True)
                value = spans[1].get_text(strip=True)
                values[label] = value
    except:
        pass

    return values


# ---------------------------------------------------
# VERDICT
# ---------------------------------------------------
def get_verdict(pe, pb, roe, debt, growth, margin):
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

    if growth > 5:
        score += 1
        reasons.append("Growth visible")

    if margin > 8:
        score += 2
        reasons.append("Healthy margins")

    if score >= 8:
        verdict = "BUY 🟢"
        horizon = "3 to 5 Years"
    elif score >= 5:
        verdict = "HOLD 🟡"
        horizon = "1 to 3 Years"
    else:
        verdict = "AVOID 🔴"
        horizon = "Weak fundamentals"

    return score, verdict, horizon, reasons


# ---------------------------------------------------
# ROUTES
# ---------------------------------------------------
@app.get("/")
def root():
    return {"message": "Indian Stock Analyzer API Running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analyze")
def analyze(ticker: str):
    try:
        resolved = resolve_symbol(ticker)
        symbol = resolved + ".NS"

        stock = yf.Ticker(symbol)
        info = stock.info
        scr = get_screener_data(resolved)

        # MAIN RATIOS
        pe = first_non_zero(scr.get("Stock P/E"), info.get("trailingPE"))
        pb = first_non_zero(scr.get("Price to book value"), info.get("priceToBook"))
        roe = first_non_zero(scr.get("ROE"), percent_to_number(info.get("returnOnEquity")))
        roce = first_non_zero(scr.get("ROCE"), roe)
        debt = first_non_zero(info.get("debtToEquity"))
        opm = first_non_zero(percent_to_number(info.get("operatingMargins")))
        npm = first_non_zero(percent_to_number(info.get("profitMargins")))
        sales_growth = first_non_zero(percent_to_number(info.get("revenueGrowth")))
        profit_growth = first_non_zero(percent_to_number(info.get("earningsGrowth")))
        divy = first_non_zero(scr.get("Dividend Yield"), percent_to_number(info.get("dividendYield")))
        price = first_non_zero(scr.get("Current Price"), info.get("currentPrice"))

        # ---------------------------------------------------
        # CURRENT RATIO (DIRECT + MANUAL)
        # ---------------------------------------------------
        current_ratio = first_non_zero(info.get("currentRatio"))

        if current_ratio == 0:
            try:
                bs = stock.balance_sheet

                if not bs.empty:
                    current_assets = 0
                    current_liabilities = 0

                    for idx in bs.index:
                        name = str(idx).lower()

                        if "current assets" in name:
                            current_assets = to_float(bs.loc[idx].iloc[0])

                        if "current liabilities" in name:
                            current_liabilities = to_float(bs.loc[idx].iloc[0])

                    if current_assets > 0 and current_liabilities > 0:
                        current_ratio = current_assets / current_liabilities
            except:
                pass

        # ---------------------------------------------------
        # MANUAL PEG
        # ---------------------------------------------------
        peg = first_non_zero(info.get("pegRatio"))

        if peg == 0 and pe > 0 and profit_growth > 0:
            peg = pe / profit_growth

        # ---------------------------------------------------
        # MANUAL FCF
        # ---------------------------------------------------
        fcf = first_non_zero(info.get("freeCashflow"))

        if fcf == 0:
            try:
                cf = stock.cashflow
                if not cf.empty:
                    operating_cash = to_float(cf.iloc[0, 0])
                    capex = abs(to_float(cf.iloc[-1, 0]))
                    fcf = operating_cash - capex
            except:
                pass

        # ---------------------------------------------------
        # INTEREST COVERAGE
        # ---------------------------------------------------
        interest_cov = first_non_zero(info.get("ebitdaMargins"))

        # ---------------------------------------------------
        # SCORE
        # ---------------------------------------------------
        score, verdict, horizon, reasons = get_verdict(
            pe, pb, roe, debt, sales_growth, npm
        )

        # ---------------------------------------------------
        # FINAL OUTPUT
        # ---------------------------------------------------
        return {
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
                "Dividend Yield": safe_num(divy)
            },

            "ratios": {
                "PB Ratio": {
                    "value": safe_num(pb),
                    "meaning": "Price vs net worth",
                    "ideal": "Lower better"
                },
                "PEG": {
                    "value": safe_num(peg),
                    "meaning": "PE adjusted for growth",
                    "ideal": "Below 1 good"
                },
                "ROE": {
                    "value": safe_num(roe),
                    "meaning": "Return on shareholder money",
                    "ideal": "Higher better"
                },
                "ROCE": {
                    "value": safe_num(roce),
                    "meaning": "Return on capital used",
                    "ideal": "Higher better"
                },
                "DebtEquity": {
                    "value": safe_num(debt),
                    "meaning": "Debt burden",
                    "ideal": "Lower better"
                },
                "CurrentRatio": {
                    "value": safe_num(current_ratio),
                    "meaning": "Short term liquidity",
                    "ideal": "Above 1 good"
                },
                "OperatingMargin": {
                    "value": safe_num(opm),
                    "meaning": "Operating profit %",
                    "ideal": "Higher better"
                },
                "NetMargin": {
                    "value": safe_num(npm),
                    "meaning": "Final profit %",
                    "ideal": "Higher better"
                },
                "SalesGrowth": {
                    "value": safe_num(sales_growth),
                    "meaning": "Revenue growth %",
                    "ideal": "Higher sustainable better"
                },
                "ProfitGrowth": {
                    "value": safe_num(profit_growth),
                    "meaning": "Profit growth %",
                    "ideal": "Higher better"
                },
                "FCF": {
                    "value": safe_num(fcf),
                    "meaning": "Free cash flow",
                    "ideal": "Positive good"
                },
                "DividendYield": {
                    "value": safe_num(divy),
                    "meaning": "Cash return %",
                    "ideal": "Moderate/high good"
                },
                "InterestCoverage": {
                    "value": safe_num(interest_cov),
                    "meaning": "Ability to pay interest",
                    "ideal": "Higher better"
                }
            }
        }

    except Exception as e:
        return {"error": str(e)}