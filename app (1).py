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

ASSETS_KR = {"KODEX 200": "069500", "TIGER 나스닥100": "133690", "KODEX 국고채3년": "069660"}
CODE_TO_NAME_KR = {v: k for k, v in ASSETS_KR.items()}

# 전역 상태 관리
bot_status = {"is_running": False, "log": [], "target": "-", "last_update": "-", "balance": 0, "evlu_amt": 0, "total_asset": 0, "selected_strategy": "dual_momentum"}
overseas_status = {"is_running": False, "log": [], "deposit": "0.00", "evlu_amt": "0.00", "total_asset": "0.00", "target": "-", "last_update": "-"}

# --- [2. 공통 함수] ---

def log_msg(msg, is_overseas=False):
    now = datetime.datetime.now().strftime('%H:%M:%S')
    full_msg = f"[{now}] {msg}"
    print(full_msg)
    target = overseas_status if is_overseas else bot_status
    target["log"].insert(0, full_msg) # 순수 문자열만 저장
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

# --- [3. 국내 주식 로직] ---

def update_domestic_account_info():
    token = get_token()
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "VTTC8434R"}
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "N", "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
    try:
        res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params)
        data = res.json()
        if data.get('rt_cd') == '0':
            summary = data['output2'][0]
            bot_status["balance"] = int(summary['dncl_amt'])
            bot_status["evlu_amt"] = int(summary['tot_evlu_amt']) - int(summary['dncl_amt'])
            bot_status["total_asset"] = int(summary['tot_evlu_amt'])
    except: pass

def trade_order_kr(code, qty, is_buy=True):
    token = get_token()
    tr_id = "VTTC0802U" if is_buy else "VTTC0801U"
    headers_p = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": "FHKST01010100"}
    params_p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    res_p = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price", headers=headers_p, params=params_p)
    curr_price = res_p.json()['output']['stck_prpr']
    data = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "PDNO": code, "ORD_DVSN": "00", "ORD_QTY": str(int(qty)), "ORD_UNPR": str(curr_price)}
    headers = {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id, "hashkey": hashkey(data)}
    res = requests.post(f"{URL_BASE}/uapi/domestic-stock/v1/trading/order-cash", headers=headers, data=json.dumps(data))
    if res.json().get("rt_cd") == "0":
        log_msg(f"✅ [국내] {CODE_TO_NAME_KR.get(code, code)} {qty}주 {'매수' if is_buy else '매도'} 성공")

def trading_logic_kr():
    log_msg("🚀 국내주식 자동매매 쓰레드 가동")
    while bot_status["is_running"]:
        now = datetime.datetime.now()
        if now.weekday() >= 5 or now.hour < 9 or (now.hour >= 15 and now.minute > 20):
            log_msg("💤 국내 시장 대기 중 (09:00~15:20)")
            time.sleep(600); continue
        try:
            token = get_token()
            bot_status["last_update"] = now.strftime('%H:%M:%S')
            df_k = yf.Ticker("069500.KS").history(period="7mo")
            df_u = yf.Ticker("133690.KS").history(period="7mo")
            ret_k = (df_k['Close'].iloc[-1] / df_k['Close'].iloc[-126]) - 1
            ret_u = (df_u['Close'].iloc[-1] / df_u['Close'].iloc[-126]) - 1
            target_name = ("KODEX 200" if ret_k > ret_u else "TIGER 나스닥100") if max(ret_k, ret_u) > 0 else "KODEX 국고채3년"
            target_code = ASSETS_KR[target_name]
            bot_status["target"] = target_name
            log_msg(f"🎯 국내 목표: {target_name}")
            update_domestic_account_info()
            time.sleep(3600)
        except Exception as e: log_msg(f"⚠️ 국내 에러: {e}"); time.sleep(60)

# --- [4. 해외 주식 로직] ---

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
            deposit = summary.get('frcr_dncl_amt_2') or summary.get('frcr_pchs_amt1') or "0.00"
            real_evlu = calculate_real_evlu(data.get("output1", []))
            overseas_status["deposit"] = f"{float(deposit):,.2f}"
            overseas_status["evlu_amt"] = f"{real_evlu:,.2f}"
            overseas_status["total_asset"] = f"{(float(deposit) + real_evlu):,.2f}"
    except: pass

def overseas_trading_logic():
    log_msg("🚀 해외주식 자동매매 쓰레드 가동", True)
    while overseas_status["is_running"]:
        try:
            token = get_token()
            overseas_status["last_update"] = datetime.datetime.now().strftime('%H:%M:%S')
            ret_t = (yf.Ticker("TQQQ").history(period="7mo")['Close'].iloc[-1] / yf.Ticker("TQQQ").history(period="7mo")['Close'].iloc[-126]) - 1
            ret_e = (yf.Ticker("EFA").history(period="7mo")['Close'].iloc[-1] / yf.Ticker("EFA").history(period="7mo")['Close'].iloc[-126]) - 1
            target_symbol = ("TQQQ" if ret_t > ret_e else "EFA") if max(ret_t, ret_e) > 0 else "GLD"
            overseas_status["target"] = target_symbol
            log_msg(f"🎯 해외 목표: {target_symbol}", True)
            update_overseas_info()
            time.sleep(3600)
        except Exception as e: log_msg(f"⚠️ 해외 에러: {e}", True); time.sleep(60)

# --- [5. Flask Routes] ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/overseas')
def overseas_page(): return render_template('overseas.html')

@app.route('/status')
def get_status():
    update_domestic_account_info()
    return jsonify(bot_status)

@app.route('/overseas_status')
def get_o_status():
    update_overseas_info()
    return jsonify(overseas_status)

@app.route('/start', methods=['POST'])
def start_kr():
    if not bot_status["is_running"]:
        data = request.get_json()
        if data and "strategy" in data: bot_status["selected_strategy"] = data["strategy"]
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