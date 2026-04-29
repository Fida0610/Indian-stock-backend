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

# ---------------- ANALYZE STOCK ----------------

@app.get("/analyze")
def analyze(ticker: str):

    try:
        stock = yf.Ticker(ticker + ".NS")
        hist = stock.history(period="1y")

        if hist.empty:
            return {"error": "No data"}

        price = float(hist["Close"].iloc[-1])
        dma50 = hist["Close"].tail(50).mean()
        dma200 = hist["Close"].tail(200).mean()

        # -------- RSI --------
        delta = hist["Close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])

        # -------- FUNDAMENTALS --------
        fin = stock.financials
        bs = stock.balance_sheet
        cf = stock.cashflow

        net_income = equity = ebit = debt = 0
        current_assets = current_liabilities = total_assets = 0
        op_cf = capex = 0

        for idx in fin.index:
            n = str(idx).lower()
            if "net income" in n:
                net_income = float(fin.loc[idx].iloc[0])
            if "ebit" in n:
                ebit = float(fin.loc[idx].iloc[0])

        for idx in bs.index:
            n = str(idx).lower()
            if "equity" in n:
                equity = float(bs.loc[idx].iloc[0])
            if "current assets" in n:
                current_assets = float(bs.loc[idx].iloc[0])
            if "current liabilities" in n:
                current_liabilities = float(bs.loc[idx].iloc[0])
            if "total assets" in n:
                total_assets = float(bs.loc[idx].iloc[0])
            if "debt" in n:
                debt += float(bs.loc[idx].iloc[0])

        for idx in cf.index:
            n = str(idx).lower()
            if "operating cash flow" in n:
                op_cf = float(cf.loc[idx].iloc[0])
            if "capital expenditure" in n:
                capex = abs(float(cf.loc[idx].iloc[0]))

        # -------- RATIOS --------
        roe = (net_income / equity) * 100 if equity else None
        roce = (ebit / (total_assets - current_liabilities)) * 100 if total_assets else None
        debt_equity = debt / equity if equity else None
        current_ratio = current_assets / current_liabilities if current_liabilities else None
        fcf = op_cf - capex if op_cf else None

        # -------- SCORING --------
        score = 0
        reasons = []

        if roe and roe > 15:
            score += 2
            reasons.append("Strong ROE ✅")
        else:
            reasons.append("Weak ROE ❌")

        if roce and roce > 18:
            score += 2
            reasons.append("High ROCE ✅")

        if debt_equity is not None and debt_equity < 0.5:
            score += 2
            reasons.append("Low Debt ✅")

        if rsi < 70:
            score += 1
            reasons.append("RSI healthy ✅")
        else:
            reasons.append("Overbought RSI ⚠️")

        if price > dma200:
            score += 2
            reasons.append("Uptrend ✅")
        else:
            reasons.append("Below 200DMA ❌")

        if score >= 7:
            verdict = "BUY 🟢"
        elif score >= 4:
            verdict = "HOLD 🟡"
        else:
            verdict = "SELL 🔴"

        return {
            "stock": ticker.upper(),
            "price": price,
            "score": score,
            "verdict": verdict,
            "technical": {
                "RSI": rsi,
                "50DMA": dma50,
                "200DMA": dma200
            },
            "fundamental": {
                "ROE": roe,
                "ROCE": roce,
                "Debt": debt_equity,
                "CurrentRatio": current_ratio,
                "FCF": fcf
            },
            "reasons": reasons
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

def score_stock(r, t):
    roe, roce, debt = r["ROE"], r["ROCE"], r["Debt"]
    s = 0

    if t == "wealth":
        if roe and roe > 15: s += 2
        if roce and roce > 18: s += 2
        if debt is not None and debt < 0.5: s += 2

    elif t == "multibagger":
        if roe and roe > 18: s += 2
        if roce and roce > 20: s += 2
        if debt is not None and debt < 0.3: s += 2

    elif t == "balanced":
        if roe and roe > 15: s += 2
        if roce and roce > 18: s += 2
        if debt is not None and debt < 0.4: s += 2

    return s

@app.get("/screener")
def screener(type: str):

    results = []

    for stock in NIFTY50:
        try:
            d = analyze(stock)
            if "fundamental" not in d:
                continue

            s = score_stock(d["fundamental"], type)

            results.append({
                "stock": stock,
                "score": s,
                "verdict": "BUY 🟢" if s >= 5 else "HOLD 🟡" if s >= 3 else "AVOID 🔴"
            })

            time.sleep(1)

        except:
            continue

    return {"stocks": sorted(results, key=lambda x: x["score"], reverse=True)}