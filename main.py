from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- RATIO DEFINITIONS --------
DEFINITIONS = {
    "ROE": "Return on Equity - Profit generated from shareholder money",
    "ROCE": "Return on Capital Employed - Efficiency of capital usage",
    "Debt": "Debt to Equity - Financial leverage (lower is safer)",
    "CurrentRatio": "Liquidity measure (ability to pay short-term liabilities)",
    "FCF": "Free Cash Flow - Cash left after expenses",
}

# -------- SAFE DIVISION --------
def safe_div(a, b):
    try:
        if a and b:
            return a / b
    except:
        return None

# -------- ANALYZE --------
@app.get("/analyze")
def analyze(ticker: str):

    try:
        stock = yf.Ticker(ticker + ".NS")
        hist = stock.history(period="1y")

        if hist.empty:
            return {"error": "No data"}

        price = hist["Close"].iloc[-1]
        dma50 = hist["Close"].tail(50).mean()
        dma200 = hist["Close"].tail(200).mean()

        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        net_income = fin.loc["Net Income"].iloc[0] if "Net Income" in fin.index else None
        ebit = fin.loc["EBIT"].iloc[0] if "EBIT" in fin.index else None

        equity = bs.loc["Total Stockholder Equity"].iloc[0] if "Total Stockholder Equity" in bs.index else None
        debt = bs.loc["Total Debt"].iloc[0] if "Total Debt" in bs.index else 0

        current_assets = bs.loc["Total Current Assets"].iloc[0] if "Total Current Assets" in bs.index else None
        current_liabilities = bs.loc["Total Current Liabilities"].iloc[0] if "Total Current Liabilities" in bs.index else None

        op_cf = cf.loc["Operating Cash Flow"].iloc[0] if "Operating Cash Flow" in cf.index else None
        capex = abs(cf.loc["Capital Expenditure"].iloc[0]) if "Capital Expenditure" in cf.index else 0

        # -------- RATIOS --------
        roe = safe_div(net_income, equity)
        roce = safe_div(ebit, (equity + debt))
        debt_equity = safe_div(debt, equity)
        current_ratio = safe_div(current_assets, current_liabilities)
        fcf = op_cf - capex if op_cf else None

        ratios = {
            "ROE": roe * 100 if roe else None,
            "ROCE": roce * 100 if roce else None,
            "Debt": debt_equity,
            "CurrentRatio": current_ratio,
            "FCF": fcf
        }

        # -------- SCORING --------
        score = 0
        total = 0
        reasons = []

        def check(cond, msg):
            nonlocal score, total
            if cond is not None:
                total += 1
                if cond:
                    score += 1
                    reasons.append(msg + " ✅")
                else:
                    reasons.append(msg + " ❌")

        check(ratios["ROE"] and ratios["ROE"] > 15, "ROE > 15")
        check(ratios["ROCE"] and ratios["ROCE"] > 18, "ROCE > 18")
        check(ratios["Debt"] is not None and ratios["Debt"] < 0.5, "Low Debt")
        check(ratios["CurrentRatio"] and ratios["CurrentRatio"] > 1.5, "Good Liquidity")
        check(ratios["FCF"] and ratios["FCF"] > 0, "Positive Cash Flow")
        check(price > dma200, "Above 200DMA")

        final_score = score / total if total else 0

        if final_score > 0.8:
            verdict = "STRONG BUY 🟢"
        elif final_score > 0.6:
            verdict = "BUY 🟢"
        elif final_score > 0.4:
            verdict = "HOLD 🟡"
        else:
            verdict = "AVOID 🔴"

        return {
            "stock": ticker,
            "price": price,
            "score": round(final_score, 2),
            "verdict": verdict,
            "ratios": ratios,
            "definitions": DEFINITIONS,
            "reasons": reasons,
            "technical": {
                "Above50DMA": price > dma50,
                "Above200DMA": price > dma200
            }
        }

    except Exception as e:
        return {"error": str(e)}