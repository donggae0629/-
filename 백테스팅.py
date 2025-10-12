# 필요한 라이브러리: yfinance, pandas, numpy, matplotlib
# 설치: pip install yfinance pandas numpy matplotlib
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import requests
DISCORD_WEBHOOK_URL: "https://discordapp.com/api/webhooks/1425020276327841836/i_qFjAgjKp8seIrVwMP1PNOpGOsry5rysT7Bn1JUspcSrPf5-6rLY_13yg-DDoCBjIJk"

# 설정: 20년 전부터 (현재: 2025-10-12 기준)
START = "2010-10-12"
END   = "2025-10-12"
result_print = ""

def build_dual_momentum_weights(prices_m, lookback_months=9, risky_assets=["SPY", "EFA"], safe_asset="TLT"):
    """
    prices_m: 월말 가격 DataFrame
    risky_assets: 비교할 2개 위험자산 (예: SPY, EFA)
    safe_asset: 절대모멘텀 음수일 때 이동할 안전자산 (예: TLT)
    """
    # 필요한 종목만 필터
    tickers = risky_assets + [safe_asset]
    data = prices_m[tickers].dropna(how="any")
    momentum = data.pct_change(lookback_months)  # 9개월 수익률

    weights = pd.DataFrame(0.0, index=data.index, columns=data.columns)

    for t in momentum.index:
        mom = momentum.loc[t]
        if mom.isnull().any():
            continue

        # 상대 모멘텀: SPY vs EFA
        best_asset = mom[risky_assets].idxmax()
        best_ret = mom[best_asset]

        # 절대 모멘텀 체크: 수익률 > 0 이면 투자, 아니면 TLT
        if best_ret > 0:
            weights.loc[t, best_asset] = 1.0
        else:
            weights.loc[t, safe_asset] = 1.0

    return weights


def download_prices(tickers, start=START, end=END):
    data = yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)
    # auto_adjust=True -> 조정종가 반영된 종가(=총수익 기반)
    if isinstance(tickers, str):
        prices = data['Close'].to_frame(name=tickers)
    else:
        prices = data['Close']
    prices = prices.dropna(how='all')
    return prices

def monthly_prices(prices):
    # 월말 종가 사용
    return prices.resample('M').last()

def compute_metrics(portfolio_returns):
    # portfolio_returns: pd.Series (periodic, 월별 수익률)
    periods_per_year = 12
    total_periods = portfolio_returns.dropna().shape[0]
    if total_periods == 0:
        return {}
    cumulative = (1 + portfolio_returns).cumprod()
    final_value = cumulative.iloc[-1]
    years = total_periods / periods_per_year
    CAGR = final_value ** (1/years) - 1
    ann_vol = portfolio_returns.std() * np.sqrt(periods_per_year)
    # 샤프(무위험 0)
    sharpe = (portfolio_returns.mean() * periods_per_year) / (ann_vol if ann_vol>0 else np.nan)
    # Max Drawdown
    peak = cumulative.cummax()
    dd = (cumulative - peak) / peak
    max_dd = dd.min()
    return {
        "연 평균 복리 수익률 (CAGR)": CAGR,
        "AnnualVol": ann_vol,
        "샤프 지수 (Sharpe)": sharpe,
        "최대 자산 하락률 (MaxDD)": max_dd,
        "1달러로 투자했을때 최종 자산 (Final)": final_value
    }

def simulate_monthly_strategy(prices, weight_df, transaction_cost=0.001):
    """
    prices: 월말 가격 DataFrame (index: month-ends)
    weight_df: 동일 색인(index)으로, 각 월의 포트폴리오 가중치 (각 행합 = 1)
               weight_df.loc[t] 적용되어 다음 월 수익을 가져오게 설계.
    transaction_cost: 턴오버 비용(왕복 포함 비율). 비용 적용 방식: turnover * cost
    """
    returns = prices.pct_change()  # 월별 리턴: index aligns with month-ends
    # ensure same index and tickers in weights & returns
    weight_df = weight_df.reindex(index=returns.index).fillna(0).reindex(columns=returns.columns).fillna(0)
    # portfolio return for month t is dot(weights at t) * returns at t
    port_returns = (weight_df * returns).sum(axis=1).shift(-0)  # weight_t applied to returns in same index period
    # transaction cost: turnover = sum |w_t - w_{t-1}| ; cost = turnover * transaction_cost
    turnover = weight_df.diff().abs().sum(axis=1).fillna(0)
    cost = turnover * transaction_cost
    port_returns = port_returns - cost
    # drop last row if NaN (no forward return)
    port_returns = port_returns.dropna()
    return port_returns

# Strategy builders ---------------------------------------------------------
def build_momentum_weights(prices_m, lookback_months=12, skip_month=1, top_n=3):
    """
    12-1 모멘텀 예:
      momentum = pct_change(12).shift(1)  (skip most recent month)
      매월 상위 top_n 선택하여 동일비중
    prices_m: 월말 가격 DataFrame
    """
    mom = prices_m.pct_change(lookback_months).shift(skip_month)  # skip 1 month typically
    index = prices_m.index
    weights = pd.DataFrame(0.0, index=index, columns=prices_m.columns)
    for t in mom.index:
        scores = mom.loc[t].dropna()
        if scores.empty:
            continue
        top = scores.sort_values(ascending=False).head(top_n).index
        weights.loc[t, top] = 1.0 / len(top)
    return weights

def build_ma_trend_weights(prices_m, ma_window=200):
    """
    단순 MA 트렌드: 가격 > MA -> 보유 (동일비중)
    prices_m: 월말 가격
    ma_window: 월 단위 MA (200월은 지나치게 길지만 예시; 실제로는 일단 월단위 12/50/200 등 시험)
    """
    # For monthly data, use rolling(ma_window) on monthly series
    ma = prices_m.rolling(window=ma_window, min_periods=1).mean()
    weights = pd.DataFrame(0.0, index=prices_m.index, columns=prices_m.columns)
    for t in prices_m.index:
        eligible = prices_m.loc[t] > ma.loc[t]
        eligible = eligible[eligible].index
        if len(eligible) > 0:
            weights.loc[t, eligible] = 1.0 / len(eligible)
    return weights

def build_buy_and_hold_weights(prices_m, tickers):
    # initial equal weight at first period, hold
    w = pd.DataFrame(0.0, index=prices_m.index, columns=prices_m.columns)
    w.iloc[0] = 1.0 / len(tickers)
    w = w.ffill().fillna(0)
    return w
def send_message(msg):
    """디스코드 메세지 전송"""
    now = datetime.datetime.now()
    message = {"content": f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {str(msg)}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message)
    print(message)
# Example usage -------------------------------------------------------------
if __name__ == "__main__":
    # 예시 유니버스(원하시면 기업티커 리스트로 바꾸세요)
    tickers = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT"]
    prices = download_prices(tickers)
    prices_m = monthly_prices(prices)

    # 전략들 생성
    w_mom = build_momentum_weights(prices_m, lookback_months=12, skip_month=1, top_n=2)
    w_ma = build_ma_trend_weights(prices_m, ma_window=12)   # 예: 12개월 MA로 시도
    w_bh = build_buy_and_hold_weights(prices_m, tickers)
    w_dual = build_dual_momentum_weights(prices_m, lookback_months=9,
                                         risky_assets=["SPY", "EFA"], safe_asset="TLT")

    # 시뮬레이션(거래비용 0.1%로 설정)
    port_mom = simulate_monthly_strategy(prices_m, w_mom, transaction_cost=0.001)
    port_ma  = simulate_monthly_strategy(prices_m, w_ma, transaction_cost=0.001)
    port_bh  = simulate_monthly_strategy(prices_m, w_bh, transaction_cost=0.001)
    port_dual = simulate_monthly_strategy(prices_m, w_dual, transaction_cost=0.001)

    metrics = {
        "Momentum12-1_top2": compute_metrics(port_mom),
        "MA12_trend": compute_metrics(port_ma),
        "BuyHold_equal": compute_metrics(port_bh),
        "DualMomentum_9M" : compute_metrics(port_dual)
    }

    for name, m in metrics.items():
        result_print+=f"=== {name}" 
        for k, v in m.items():
            if isinstance(v, float):
                result_print +=f"  {k}: {v:.4f}"
            else:
                result_print+=f"  {k}: {v}"
        result_print+="\n"
    print(result_print)
    # 시각화: 누적수익
    cum_mom = (1 + port_mom).cumprod()
    cum_ma  = (1 + port_ma).cumprod()
    cum_bh  = (1 + port_bh).cumprod()
    cum_dual = (1 + port_dual).cumprod()

    plt.figure(figsize=(10,6))
    cum_mom.plot(label='Momentum12-1_top2')
    cum_ma.plot(label='MA12_trend')
    cum_bh.plot(label='BuyHold_equal')
    cum_dual.plot(label='DualMomentum_9M', linewidth=2.3)
    plt.legend()
    plt.title("Cumulative (monthly) returns")
    plt.show()
