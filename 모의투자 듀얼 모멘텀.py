import requests
import json
import datetime
from pytz import timezone
import time
import yaml
import datetime as dt


with open('config.yaml', encoding='UTF-8') as f:
    _cfg = yaml.load(f, Loader=yaml.FullLoader)
APP_KEY = _cfg['APP_KEY']
APP_SECRET = _cfg['APP_SECRET']
ACCESS_TOKEN = ""
CANO = _cfg['CANO']
ACNT_PRDT_CD = _cfg['ACNT_PRDT_CD']
DISCORD_WEBHOOK_URL = _cfg['DISCORD_WEBHOOK_URL']
URL_BASE = _cfg['URL_BASE']
ASSETS = {"TQQQ": "공격1", "EFA": "공격2", "GLD": "안전자산"}
LOOKBACK_MONTHS = 6
current_position = None

def get_current_price(market="NAS", code="AAPL"):
    """현재가 조회"""
    PATH = "uapi/overseas-price/v1/quotations/price"
    URL = f"{URL_BASE}/{PATH}"
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {ACCESS_TOKEN}",
            "appKey":APP_KEY,
            "appSecret":APP_SECRET,
            "tr_id":"HHDFS00000300"}
    params = {
        "AUTH": "",
        "EXCD":market,
        "SYMB":code,
    }
    res = requests.get(URL, headers=headers, params=params)
    return float(res.json()['output']['last'])

def send_message(msg):
    """디스코드 메세지 전송"""
    now = datetime.datetime.now()
    message = {"content": f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {str(msg)}"}
    requests.post(DISCORD_WEBHOOK_URL, data=message)
    print(message)

def get_access_token():
    """토큰 발급"""
    headers = {"content-type":"application/json"}
    body = {"grant_type":"client_credentials",
    "appkey":APP_KEY, 
    "appsecret":APP_SECRET}
    PATH = "oauth2/tokenP"
    URL = f"{URL_BASE}/{PATH}"
    res = requests.post(URL, headers=headers, data=json.dumps(body))
    ACCESS_TOKEN = res.json()["access_token"]
    
    return ACCESS_TOKEN


def hashkey(datas):
    """암호화"""
    PATH = "uapi/hashkey"
    URL = f"{URL_BASE}/{PATH}"
    headers = {
    'content-Type' : 'application/json',
    'appKey' : APP_KEY,
    'appSecret' : APP_SECRET,
    }
    res = requests.post(URL, headers=headers, data=json.dumps(datas))
    hashkey = res.json()["HASH"]
    return hashkey


def get_stock_balance():
    """주식 잔고조회"""
    PATH = "uapi/overseas-stock/v1/trading/inquire-balance"
    URL = f"{URL_BASE}/{PATH}"
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {ACCESS_TOKEN}",
        "appKey":APP_KEY,
        "appSecret":APP_SECRET,
        "tr_id":"VTTS3012R",
        "custtype":"P"
    }
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    res = requests.get(URL, headers=headers, params=params)
    stock_list = res.json()['output1']
    evaluation = res.json()['output2']
    stock_dict = {}
    send_message(f"====주식 보유잔고====")
    for stock in stock_list:
        if int(stock['ovrs_cblc_qty']) > 0:
            stock_dict[stock['ovrs_pdno']] = stock['ovrs_cblc_qty']
            send_message(f"{stock['ovrs_item_name']}({stock['ovrs_pdno']}): {stock['ovrs_cblc_qty']}주")
            time.sleep(0.1)
    send_message(f"주식 평가 금액: ${evaluation['tot_evlu_pfls_amt']}")
    time.sleep(0.1)
    send_message(f"평가 손익 합계: ${evaluation['ovrs_tot_pfls']}")
    time.sleep(0.1)
    send_message(f"=================")
    return stock_dict

def get_balance():
    """현금 잔고조회"""
    PATH = "uapi/domestic-stock/v1/trading/inquire-psbl-order"
    URL = f"{URL_BASE}/{PATH}"
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {ACCESS_TOKEN}",
        "appKey":APP_KEY,
        "appSecret":APP_SECRET,
        "tr_id":"VTTC8908R",
        "custtype":"P",
    }
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "PDNO": "005930",
        "ORD_UNPR": "65500",
        "ORD_DVSN": "01",
        "CMA_EVLU_AMT_ICLD_YN": "Y",
        "OVRS_ICLD_YN": "Y"
    }
    res = requests.get(URL, headers=headers, params=params)
    cash = res.json()['output']['ord_psbl_cash']
    send_message(f"주문 가능 현금 잔고: {cash}원")
    return int(cash)


def sell(market="NASD", code="AAPL", qty="1", price="0"):
    """미국 주식 지정가 매도"""
    PATH = "uapi/overseas-stock/v1/trading/order"
    URL = f"{URL_BASE}/{PATH}"
    data = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": market,
        "PDNO": code,
        "ORD_DVSN": "00",
        "ORD_QTY": str(int(qty)),
        "OVRS_ORD_UNPR": f"{round(price,2)}",
        "ORD_SVR_DVSN_CD": "0"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {ACCESS_TOKEN}",
        "appKey":APP_KEY,
        "appSecret":APP_SECRET,
        "tr_id":"VTTT1001U",
        "custtype":"P",
        "hashkey" : hashkey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))
    if res.json()['rt_cd'] == '0':
        send_message(f"[매도 성공]{str(res.json())}")
        return True
    else:
        send_message(f"[매도 실패]{str(res.json())}")
        return False

def get_exchange_rate():
    """환율 조회"""
    PATH = "uapi/overseas-stock/v1/trading/inquire-present-balance"
    URL = f"{URL_BASE}/{PATH}"
    headers = {"Content-Type":"application/json", 
            "authorization": f"Bearer {ACCESS_TOKEN}",
            "appKey":APP_KEY,
            "appSecret":APP_SECRET,
            "tr_id":"VCTRP6504R"}
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "WCRC_FRCR_DVSN_CD": "01",
        "NATN_CD": "840",
        "TR_MKET_CD": "01",
        "INQR_DVSN_CD": "00"
    }
    res = requests.get(URL, headers=headers, params=params)
    exchange_rate = 1270.0
    if len(res.json()['output2']) > 0:
        exchange_rate = float(res.json()['output2'][0]['frst_bltn_exrt'])
    return exchange_rate


def get_six_month_return(symbol="TQQQ", exch="NASD"):
    """해외 ETF 6개월 수익률 계산"""
    today = dt.datetime.today()
    start = (today - dt.timedelta(days=180)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    PATH = "uapi/overseas-stock/v1/quotations/inquire-period-price"
    URL = f"{URL_BASE}/{PATH}"

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": "HHDFS76240000",  # 해외주식기간별시세
        "custtype": "P"
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "N",  # 해외지수 구분
        "FID_INPUT_ISCD": symbol,        # 종목코드 (TQQQ, EFA, GLD)
        "FID_INPUT_DATE_1": start,       # 조회 시작일 (6개월 전)
        "FID_INPUT_DATE_2": end,         # 조회 종료일 (오늘)
        "FID_PERIOD_DIV_CODE": "D"       # 일별 시세
    }

    res = requests.get(URL, headers=headers, params=params)
    data = res.json()

    try:
        prices = [float(x['stck_clpr']) for x in data['output2']]
        if len(prices) >= 2:
            ret = (prices[-1] / prices[0]) - 1
        else:
            ret = 0
    except Exception:
        ret = 0

    return ret

def buy(market="NASD", code="AAPL", qty="1", price="0"):
    """미국 주식 지정가 매수"""
    PATH = "uapi/overseas-stock/v1/trading/order"
    URL = f"{URL_BASE}/{PATH}"
    data = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": market,
        "PDNO": code,
        "ORD_DVSN": "00",
        "ORD_QTY": str(int(qty)),
        "OVRS_ORD_UNPR": f"{round(price,2)}",
        "ORD_SVR_DVSN_CD": "0"
    }
    headers = {"Content-Type":"application/json", 
        "authorization":f"Bearer {ACCESS_TOKEN}",
        "appKey":APP_KEY,
        "appSecret":APP_SECRET,
        "tr_id":"VTTT1002U",
        "custtype":"P",
        "hashkey" : hashkey(data)
    }
    res = requests.post(URL, headers=headers, data=json.dumps(data))
    if res.json()['rt_cd'] == '0':
        send_message(f"[매수 성공]{str(res.json())}")
        return True
    else:
        send_message(f"[매수 실패]{str(res.json())}")
        return False
    

def choose_dual_momentum_asset():
    """6개월 수익률 비교 후 winner 선택"""
    # ① 수익률 계산
    tqqq_ret = get_six_month_return("TQQQ")
    efa_ret = get_six_month_return("EFA")
    gld_ret = get_six_month_return("GLD")

    print(f"TQQQ 6개월 수익률: {tqqq_ret*100:.2f}%")
    print(f"EFA 6개월 수익률: {efa_ret*100:.2f}%")
    print(f"GLD 6개월 수익률: {gld_ret*100:.2f}%")

    # ② 공격자산 중 높은 수익률 선택
    if tqqq_ret > efa_ret:
        winner = "TQQQ"
        winner_ret = tqqq_ret
        print(f"📈 선택된 자산: {winner}")
        return (winner, "NASD")
    else:
        winner = "EFA"
        winner_ret = efa_ret

    # ③ winner의 수익률이 0 이하이면 GLD 선택
    if winner_ret <= 0:
        winner = "GLD"
        return (winner, "NYSE")

    
    
def is_month_end(date=None):
        """오늘이 월말(또는 직전 영업일)인지 확인"""
        if date is None:
            date = dt.date.today()
        tomorrow = date + dt.timedelta(days=1)
        return tomorrow.month != date.month
try:
    print("여기까지는 ok")
    ACCESS_TOKEN = get_access_token()
    print("여기까지는 ok")
    total_cash = get_balance()
    print("여기까지는 ok")
    send_message("===해외 주식 자동매매 프로그램을 시작합니다===")
    while True:
        t_now = dt.datetime.now(timezone('America/New_York')) # 뉴욕 기준 현재 시간
        exchange_rate = get_exchange_rate()
        buy_amount = total_cash/exchange_rate
        t_9 = t_now.replace(hour=9, minute=30, second=0, microsecond=0)
        t_start = t_now.replace(hour=9, minute=35, second=0, microsecond=0)
        t_sell = t_now.replace(hour=15, minute=45, second=0, microsecond=0)
        t_exit = t_now.replace(hour=15, minute=50, second=0,microsecond=0)
        today_week = t_now.weekday()
        month_is = is_month_end(dt.datetime.today())
        if is_month_end() and choose_dual_momentum_asset() != current_position and t_start < t_now < t_sell:
            print(f"[{today_week}] 리밸런싱 실행")
            winner,market_code = choose_dual_momentum_asset()
            current_holdings = list(stock_balance.keys())
            stock_balance = get_stock_balance()
            current_holdings = list(stock_balance.keys())
            send_message(f"현재 보유중인 자산: {current_holdings}")

            # 3️⃣ 기존 보유자산 전량 매도
            if current_holdings:
                send_message(f"📉 현재 보유자산 {current_holdings} 전량 매도 시작")
                for symbol in current_holdings:
                    qty = int(float(stock_balance[symbol]))
                    if qty > 0:
                        sell(market = market_code,code=symbol, qty=qty, price=0)
                        time.sleep(1)
                send_message("✅ 모든 보유자산 매도 완료")
            else:
                send_message("보유자산 없음 → 바로 신규매수로 진행")

            # 4️⃣ 환율 및 현금조회
            exchange_rate = get_exchange_rate()
            total_cash_usd = get_balance() / exchange_rate  # 보유원화 → 달러환산
            send_message(f"환율: {exchange_rate} / 매수 가능 달러: ${total_cash_usd:.2f}")

            # 5️⃣ winner 종목 매수
            #    - 예시: winner 가격조회 API 이용 또는 시장가 매수
            qty_to_buy = int(total_cash_usd / get_current_price(market_code, winner))
            if qty_to_buy > 0:
                send_message(f"📈 {winner} {qty_to_buy}주 매수 시도")
                buy(market = market_code,code=winner, qty=qty_to_buy, price=0)
                send_message(f"✅ {winner} 매수 완료")
            else:
                send_message("❌ 매수 수량이 0으로 계산되어 매수 중단")

            # 6️⃣ current_position 업데이트
            current_position = winner
            send_message(f"🎯 리밸런싱 완료: 현재 보유자산 → {current_position}")

            # 7️⃣ 월말 리밸런싱 이후 하루 대기
            time.sleep(60 * 60 * 24)
        if today_week == 5 or today_week == 6:  # 토요일이나 일요일이면 자동 종료
            send_message("주말이므로 프로그램을 종료합니다.")
            break
    
except Exception as e:
    send_message(f"[에러발생]{e}")
    