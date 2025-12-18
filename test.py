import requests
import json
import yaml

# 1. 설정 로드
with open("config.yaml", encoding="UTF-8") as f:
    _cfg = yaml.load(f, Loader=yaml.FullLoader)

APP_KEY = _cfg["APP_KEY"]
APP_SECRET = _cfg["APP_SECRET"]
CANO = _cfg["CANO"]
ACNT_PRDT_CD = _cfg["ACNT_PRDT_CD"]
URL_BASE = _cfg["URL_BASE"].rstrip("/")

def get_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(body))
    return res.json().get("access_token")

def get_hashkey(data):
    """POST 주문 시 보안을 위한 해시키 생성"""
    url = f"{URL_BASE}/uapi/hashkey"
    headers = {
        "content-Type": "application/json",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
    }
    res = requests.post(url, headers=headers, data=json.dumps(data))
    return res.json()["HASH"]

def check_unfilled_orders(token):
    """미체결 내역 조회"""
    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-nccs" # 미체결 조회 TR
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": "VTTT3018R" # 모의투자 미체결 조회
    }
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",
        "SORT_SQN": "DS", # 내림차순
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    res = requests.get(url, headers=headers, params=params)
    data = res.json()
    
    if data.get("rt_cd") == "0":
        orders = data.get("output", [])
        if not orders:
            print("대기 중인 미체결 주문이 없습니다.")
        else:
            for o in orders:
                print(f"📌 주문번호: {o['odno']} | 종목: {o['ft_ord_prca']} | 수량: {o['ft_ord_qty']} | 상태: 미체결 대기 중")

def buy_overseas_stock(symbol="TSLA", qty=1, price="250.00"):
    token = get_token()
    if not token: return

    url = f"{URL_BASE}/uapi/overseas-stock/v1/trading/order"
    
    # ⚠️ 주문 데이터 설정
    # 잔고 조회에서 'OVRS_EXCG_CD'라고 에러가 났으므로, 주문에서도 동일하게 맞춰줍니다.
    # 만약 'OVRS_EXCG_CD'에서 에러가 나면 다시 'OVRS_EXCH_CD'로 바꾸면 됩니다.
    data = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD",    # 👈 잔고 조회 때 성공했던 그 이름(G 버전)
        "PDNO": symbol,            # 종목코드 (예: TSLA)
        "ORD_QTY": str(qty),       # 주문 수량
        "OVRS_ORD_UNPR": str(price), # 주문 가격 (지정가)
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00"           # 00: 지정가 (상시대회는 지정가 권장)
    }

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": "VTTT1002U",      # 해외주식 매수 주문 TR ID (모의/상시대회)
        "hashkey": get_hashkey(data) # 해시키 필수
    }

    print(f"🚀 주문 전송 중: {symbol} {qty}주를 ${price}에 매수 시도...")
    res = requests.post(url, headers=headers, data=json.dumps(data))
    res_data = res.json()

    if res_data.get("rt_cd") == "0":
        print("✅ [주문 성공]")
        print(f"주문번호: {res_data['output']['ODNO']}")
        print(f"메시지: {res_data.get('msg1')}")
    else:
        print("❌ [주문 실패]")
        print(f"실패 원인: {res_data.get('msg1')}")
        print(f"상세 에러코드: {res_data.get('msg_cd')}")
        
        # 만약 여기서 또 필드명 에러가 나면, 서버가 주문 시에는 정상적인 'OVRS_EXCH_CD'를 원하는 것일 수 있습니다.
        if "INPUT_FIELD_NAME" in res_data.get("msg1", ""):
            print("💡 팁: 'OVRS_EXCG_CD'를 'OVRS_EXCH_CD'로 바꿔보세요.")

if __name__ == "__main__":
    # 테슬라(TSLA) 1주를 250달러 지정가로 매수 테스트
    # 실제 현재가에 맞춰 가격을 수정하고 실행하세요.
    buy_overseas_stock("TSLA", 1, "250.00")
