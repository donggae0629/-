from flask import Flask, render_template, jsonify, request
import threading
import requests
import json
import datetime
import time
import yaml
import yfinance as yf

app = Flask(__name__)

# --- [1. 설정 로드] ---
with open('config.yaml', encoding='UTF-8') as f:
    _cfg = yaml.load(f, Loader=yaml.FullLoader)

APP_KEY = _cfg['APP_KEY']
APP_SECRET = _cfg['APP_SECRET']
CANO = _cfg['CANO']
ACNT_PRDT_CD = _cfg['ACNT_PRDT_CD']
URL_BASE = _cfg['URL_BASE'].rstrip('/')
DISCORD_URL = _cfg.get('DISCORD_WEBHOOK_URL', '')
BUY_AMOUNT_KR = _cfg.get('BUY_AMOUNT', 1000000)

ACCESS_TOKEN = ""
token_issued_time = None

# 종목 설정
ASSETS_KR = {"KODEX 200": "069500", "TIGER 나스닥100": "133690", "KODEX 국고채3년": "069660"}
CODE_TO_NAME_KR = {v: k for k, v in ASSETS_KR.items()}

bot_status = {"is_running": False, "log": [], "target": "-", "last_update": "-", "balance": 0}
overseas_status = {"is_running": False, "log": [], "deposit": "0.00", "evlu_amt": "0.00", "total_asset": "0.00", "target": "-", "last_update": "-"}

# --- [2. 유틸리티 함수: 장 시간 확인] ---

def is_market_open_kr():
    """국내 주식 시장 시간 확인 (09:00 ~ 15:20)"""
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False # 주말
    start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=20, second=0, microsecond=0)
    return start_time <= now <= end_time

def is_market_open_os():
    """미국 주식 시장 시간 확인 (23:30 ~ 06:00 KST 기준)"""
    now = datetime.datetime.now()
    # 평일 밤 11:30 ~ 다음날 새벽 06:00 (썸머타임 미고려 대략적 설정)
    current_time = now.time()
    open_time = datetime.time(23, 30)
    close_time = datetime.time(6, 0)
    
    if current_time >= open_time or current_time <= close_time:
        if now.weekday() < 5 or (now.weekday() == 5 and current_time <= close_time):
            return True
    return False

# --- [3. 공통 함수] ---

def log_msg(msg, is_overseas=False):
    now = datetime.datetime.now().strftime('%H:%M:%S')
    full_msg = f"[{now}] {msg}"
    print(full_msg)
    target = overseas_status if is_overseas else bot_status
    target["log"].insert(0, f"<div>{full_msg}</div>") # HTML 태그 포함
    if len(target["log"]) > 50: target["log"].pop()
    if DISCORD_URL:
        try:
            prefix = "🇺🇸 " if is_overseas else "🇰🇷 "
            requests.post(DISCORD_URL, json={"content": prefix + full_msg}, timeout=5)
        except: pass

def get_token():
    global ACCESS_TOKEN, token_issued_time
    if ACCESS_TOKEN and token_issued_time:
        if (datetime.datetime.now() - token_issued_time).total_seconds() < 80000:
            return ACCESS_TOKEN
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
        ACCESS_TOKEN = res.json()["access_token"]
        token_issued_time = datetime.datetime.now()
        return ACCESS_TOKEN
    except Exception as e:
        log_msg(f"토큰 발급 오류: {e}")
    return None

def hashkey(datas):
    headers = {'content-Type': 'application/json', 'appKey': APP_KEY, 'appSecret': APP_SECRET}
    res = requests.post(f"{URL_BASE}/uapi/hashkey", headers=headers, data=json.dumps(datas))
    return res.json()["HASH"]

# --- [4. 국내 주식 로직] ---

def get_balance_kr():
    token = get_token()
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "VTTC8908R"}
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "PDNO": "005930", "ORD_UNPR": "0", "ORD_DVSN": "01", "CMA_EVLU_AMT_ICLD_YN": "Y", "OVRS_ICLD_YN": "Y"}
    try:
        res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-psbl-order", headers=headers, params=params)
        return int(res.json()['output']['ord_psbl_cash'])
    except: return 0

def trade_order_kr(code, qty, is_buy=True):
    token = get_token()
    tr_id = "VTTC0802U" if is_buy else "VTTC0801U"
    # 현재가 조회
    headers_p = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "FHKST01010100"}
    params_p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    res_p = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price", headers=headers_p, params=params_p)
    curr_price = res_p.json()['output']['stck_prpr']

    data = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "PDNO": code, "ORD_DVSN": "00", "ORD_QTY": str(int(qty)), "ORD_UNPR": str(curr_price)}
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id, "hashkey": hashkey(data)}
    res = requests.post(f"{URL_BASE}/uapi/domestic-stock/v1/trading/order-cash", headers=headers, data=json.dumps(data))
    
    action = "매수" if is_buy else "매도"
    if res.json().get("rt_cd") == "0":
        log_msg(f"✅ [국내] {CODE_TO_NAME_KR.get(code, code)} {qty}주 {action} 주문 성공")
    else:
        log_msg(f"❌ [국내] {action} 실패: {res.json().get('msg1')}")

def trading_logic_kr():
    log_msg("🚀 국내주식 자동매매 쓰레드 가동")
    while bot_status["is_running"]:
        if not is_market_open_kr():
            log_msg("💤 국내 시장이 닫혀 있습니다. (09:00~15:20 대기)")
            time.sleep(600)
            continue

        try:
            token = get_token()
            bot_status["last_update"] = datetime.datetime.now().strftime('%H:%M:%S')
            
            # 6개월 모멘텀 계산
            df_k = yf.Ticker("069500.KS").history(period="7mo")
            df_u = yf.Ticker("133690.KS").history(period="7mo")
            ret_k = (df_k['Close'].iloc[-1] / df_k['Close'].iloc[-126]) - 1
            ret_u = (df_u['Close'].iloc[-1] / df_u['Close'].iloc[-126]) - 1
            
            target_name = ("KODEX 200" if ret_k > ret_u else "TIGER 나스닥100") if max(ret_k, ret_u) > 0 else "KODEX 국고채3년"
            target_code = ASSETS_KR[target_name]
            bot_status["target"] = target_name
            log_msg(f"분석완료: {target_name} 선정 (국장:{ret_k*100:.1f}%, 미장:{ret_u*100:.1f}%)")

            # 잔고 확인
            headers_b = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "VTTC8434R"}
            params_b = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
            res_b = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers_b, params=params_b).json()
            
            # 매도
            for s in res_b.get('output1', []):
                qty = int(s['hldg_qty'])
                if s['pdno'] != target_code and qty > 0:
                    log_msg(f"♻️ 교체 매도: {s['prdt_name']} {qty}주")
                    trade_order_kr(s['pdno'], qty, False)
                    time.sleep(2)

            # 매수
            is_holding = any(s['pdno'] == target_code for s in res_b.get('output1', []))
            if not is_holding:
                cash = get_balance_kr()
                curr_p = int(yf.Ticker(f"{target_code}.KS").history(period="1d")['Close'].iloc[-1])
                qty = int(min(cash, BUY_AMOUNT_KR) / curr_p)
                if qty > 0:
                    log_msg(f"🛒 신규 매수: {target_name} {qty}주 시도 (예수금: {cash}원)")
                    trade_order_kr(target_code, qty, True)
                else:
                    log_msg(f"⚠️ 매수 불가: 예수금({cash}원)이 부족하거나 단가가 높음")
            else:
                log_msg(f"✅ 유지: {target_name} 이미 보유 중")

            time.sleep(3600)
        except Exception as e: log_msg(f"⚠️ 국내 에러: {e}"); time.sleep(60)

# --- [5. 해외 주식 로직] ---

def calculate_real_evlu(holdings):
    total_evlu = 0.0
    for s in holdings:
        qty = float(s.get('ovrs_cblc_qty', 0))
        price = float(s.get('now_pric2', 0))
        total_evlu += (qty * price)
    return total_evlu

def update_overseas_info():
    token = get_token()
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance"
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "VTTT3012R"}
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD", "WCRC_FRCR_DVSN_CD": "02", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        if data.get("rt_cd") == "0":
            summary = data.get("output2", {})
            holdings = data.get("output1", [])
            deposit = summary.get('frcr_dncl_amt_2') or summary.get('frcr_pchs_amt1') or "0.00"
            real_evlu = calculate_real_evlu(holdings)
            overseas_status["deposit"] = f"{float(deposit):,.2f}"
            overseas_status["evlu_amt"] = f"{real_evlu:,.2f}"
            overseas_status["total_asset"] = f"{(float(deposit) + real_evlu):,.2f}"
    except: pass

def trade_order_os(token, symbol, qty, price, is_buy=True):
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order"
    tr_id = "VTTT1002U" if is_buy else "VTTT1001U"
    data = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "NASD", "PDNO": symbol, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": f"{float(price):.2f}", "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"}
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id, "hashkey": hashkey(data)}
    res = requests.post(url, headers=headers, data=json.dumps(data))
    
    action = "매수" if is_buy else "매도"
    if res.json().get("rt_cd") == "0":
        log_msg(f"✅ [해외] {symbol} {qty}주 {action} 주문 성공", True)
    else:
        log_msg(f"❌ [해외] {action} 실패: {res.json().get('msg1')}", True)

def overseas_trading_logic():
    log_msg("🚀 해외주식 자동매매 쓰레드 가동", True)
    while overseas_status["is_running"]:
        if not is_market_open_os():
            log_msg("💤 미국 시장이 닫혀 있습니다. (23:30~06:00 대기)", True)
            time.sleep(600)
            continue

        try:
            token = get_token()
            overseas_status["last_update"] = datetime.datetime.now().strftime('%H:%M:%S')
            
            # 6개월 모멘텀 계산 (TQQQ, EFA, GLD)
            df_t = yf.Ticker("TQQQ").history(period="7mo")
            df_e = yf.Ticker("EFA").history(period="7mo")
            ret_t = (df_t['Close'].iloc[-1] / df_t['Close'].iloc[-126]) - 1
            ret_e = (df_e['Close'].iloc[-1] / df_e['Close'].iloc[-126]) - 1
            
            target_symbol = ("TQQQ" if ret_t > ret_e else "EFA") if max(ret_t, ret_e) > 0 else "GLD"
            overseas_status["target"] = target_symbol
            log_msg(f"분석완료: {target_symbol} 선정 (TQQQ:{ret_t*100:.1f}%, EFA:{ret_e*100:.1f}%)", True)

            # 잔고조회
            url_bal = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance"
            params_bal = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD", "WCRC_FRCR_DVSN_CD": "02", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
            res_bal = requests.get(url_bal, headers={"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "VTTT3012R"}, params=params_bal).json()
            
            if res_bal.get('rt_cd') == '0':
                holdings = res_bal.get("output1", [])
                summary = res_bal.get("output2", {})
                
                # 매도
                for item in holdings:
                    sym = item.get('ovrs_pdno')
                    qty = int(float(item.get('ovrs_cblc_qty', 0)))
                    if sym != target_symbol and qty > 0:
                        log_msg(f"♻️ 교체 매도: {sym} {qty}주", True)
                        trade_order_os(token, sym, qty, item.get('now_pric2'), False)
                        time.sleep(2)

                # 매수
                is_holding = any(h.get('ovrs_pdno') == target_symbol for h in holdings)
                if not is_holding:
                    deposit = float(summary.get('frcr_dncl_amt_2') or summary.get('frcr_pchs_amt1') or 0)
                    price = float(yf.Ticker(target_symbol).history(period="1d")['Close'].iloc[-1])
                    qty = int(deposit / price)
                    if qty > 0:
                        log_msg(f"🛒 신규 매수: {target_symbol} {qty}주 시도 (예수금: ${deposit})", True)
                        trade_order_os(token, target_symbol, qty, price, True)
                    else:
                        log_msg(f"⚠️ 매수 불가: 예수금(${deposit}) 부족", True)
                else:
                    log_msg(f"✅ 유지: {target_symbol} 이미 보유 중", True)

            time.sleep(3600)
        except Exception as e: log_msg(f"⚠️ 해외 에러: {e}", True); time.sleep(60)

# --- [6. Flask 라우트] ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/overseas')
def overseas_page(): return render_template('overseas.html')

@app.route('/status')
def get_status(): 
    get_balance_kr() 
    return jsonify(bot_status)

@app.route('/overseas_status')
def get_o_status():
    update_overseas_info() 
    return jsonify(overseas_status)

@app.route('/start', methods=['POST'])
def start_kr():
    if not bot_status["is_running"]:
        bot_status["is_running"] = True
        threading.Thread(target=trading_logic_kr, daemon=True).start()
        return jsonify(status="ok")
    return jsonify(status="fail")

@app.route('/overseas_start', methods=['POST'])
def start_os():
    if not overseas_status["is_running"]:
        overseas_status["is_running"] = True
        threading.Thread(target=overseas_trading_logic, daemon=True).start()
        return jsonify(status="ok")
    return jsonify(status="fail")

@app.route('/stop', methods=['POST'])
def stop_kr(): bot_status["is_running"] = False; return jsonify(status="ok")
@app.route('/overseas_stop', methods=['POST'])
def stop_os(): overseas_status["is_running"] = False; return jsonify(status="ok")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)