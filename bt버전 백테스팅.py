import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import bt
import yaml
import requests
import datetime

# 설정: 20년 전부터 (현재: 2025-10-12 기준)
import pandas as pd
with open('config.yaml', encoding='UTF-8') as f:
    _cfg = yaml.load(f, Loader=yaml.FullLoader)
DISCORD_WEBHOOK_URL = _cfg['DISCORD_WEBHOOK_URL']
def send_message(msg):
    """디스코드 메세지 전송"""
    now = datetime.datetime.now()
    message = {"content": f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {str(msg)}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message)
    print(message)
# -------------------------------------------------------------------
# 1. 데이터 준비 (예시: SPY, EFA, TLT)
# -------------------------------------------------------------------
tickers = ["SPY", "EFA", "TLT"]
start = "2010-01-01"
end = "2025-12-31"
prices = bt.get(tickers, start=start, end=end)
data = prices.dropna()
prices_m = prices.resample("M").last()  # 월말 가격으로 리샘플링
strategy = bt.Strategy("DCM",[
                       bt.algos.SelectAll(),
                       bt.algos.SelectMomentum(n=1, lookback=pd.DateOffset(months=9)),
                       bt.algos.WeighERC(lookback=pd.DateOffset(months=9)),
                       bt.algos.RunMonthly(),
                       bt.algos.Rebalance()
                       
])

backtest = bt.Backtest(strategy, data) 
backtest_net = bt.Backtest(strategy,data,name = "DCM_net",commissions=lambda q, p: abs(q)*p*0.0025)  
result = bt.run(backtest,backtest_net)

send_message(result.prices)
send_message(result.prices.to_returns())
result.plot()

plt.show()
result.get_security_weights().plot.area()
plt.show()
result.display()