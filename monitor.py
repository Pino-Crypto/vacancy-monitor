"""
東横イン那覇 空室監視スクリプト(楽天トラベル空室検索API・新ドメイン版)

- 那覇市内の東横イン4店舗を1回のAPI呼び出しでまとめてチェック
  (新APIは hotelNo をカンマ区切りで最大15件指定可能)
- 禁煙ルームの絞り込みは API の squeezeCondition=kinen に任せる
- 店舗ごとに「満室 → 空室あり」へ変化した瞬間だけ LINE に通知
- 3回連続で取得に失敗したら障害通知、復旧したら復旧通知

必要な環境変数(GitHub Secrets に設定):
  RAKUTEN_APP_ID            Rakuten Developers のアプリID
  RAKUTEN_ACCESS_KEY        同アクセスキー(applicationSecret)※新APIで必須
  LINE_CHANNEL_ACCESS_TOKEN LINE Messaging API のチャネルアクセストークン(長期)
"""

import json
import os
import sys
from pathlib import Path

import requests

# ============================================================
# 設定
# ============================================================

CHECKIN = "2026-07-04"
CHECKOUT = "2026-07-09"
ADULTS = 1

# 楽天トラベルのホテル番号と表示名(那覇市内の東横イン)
HOTELS = {
    52641: "東横INN那覇旭橋駅前",
    52723: "東横INN那覇新都心おもろまち",
    54087: "東横INN那覇国際通り美栄橋駅",
    78191: "東横INN那覇おもろまち駅前",
}

# 新APIドメイン(2026年5月に app.rakuten.co.jp から移行)
API_URL = "https://openapi.rakuten.co.jp/engine/api/Travel/VacantHotelSearch/20170426"

# この回数連続で取得に失敗したら障害通知
ERROR_THRESHOLD = 3

STATE_FILE = Path("state.json")


# ============================================================
# 楽天トラベルAPI
# ============================================================


def check_all_hotels(app_id: str, access_key: str) -> dict | None:
    """全店舗の空室を1リクエストでまとめて確認する。

    Returns:
        {hotel_no(int): {"min_price": int|None, "url": str|None}, ...}
        空室のある店舗だけがキーに含まれる(全店満室なら空dict)。
        通信エラー等で判定不能の場合は None。
    """
    params = {
        "applicationId": app_id,
        "accessKey": access_key,
        "format": "json",
        "hotelNo": ",".join(str(no) for no in HOTELS),
        "checkinDate": CHECKIN,
        "checkoutDate": CHECKOUT,
        "adultNum": ADULTS,
        "squeezeCondition": "kinen",  # 禁煙ルームのみ
        "responseType": "middle",
        "hits": 30,
    }
    headers = {         
      "Authorization": f"Bearer {access_key}",
      "Referer": "https://github.com/",     } # 新APIの認証方式

    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"[error] request failed: {e}", file=sys.stderr)
        return None

    # 「条件に合う空室なし」は 404 (not_found) で返る → 全店満室扱い
    if resp.status_code == 404:
        return {}

    if resp.status_code != 200:
        print(f"[error] HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        return None

    try:
        data = resp.json()
        vacant: dict[int, dict] = {}
        for hotel_entry in data.get("hotels", []):
            parts = hotel_entry.get("hotel", [])
            hotel_no = None
            url = None
            min_charge = None
            prices = []
            for part in parts:
                if "hotelBasicInfo" in part:
                    info = part["hotelBasicInfo"]
                    hotel_no = info.get("hotelNo")
                    url = info.get("hotelInformationUrl")
                    min_charge = info.get("hotelMinCharge")
                if "roomInfo" in part:
                    for r in part["roomInfo"]:
                        if "dailyCharge" in r:
                            total = r["dailyCharge"].get("total")
                            if total:
                                prices.append(total)
            if hotel_no in HOTELS:
                vacant[hotel_no] = {
                    "min_price": min(prices) if prices else min_charge,
                    "url": url,
                }
        return vacant
    except (ValueError, KeyError, TypeError) as e:
        print(f"[error] parse failed: {e}", file=sys.stderr)
        return None


# ============================================================
# LINE通知(broadcast: 友だち登録した自分に届く)
# ============================================================


def send_line(message: str) -> None:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    resp = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": message}]},
        timeout=30,
    )
    resp.raise_for_status()


# ============================================================
# 状態管理
# ============================================================


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"hotels": {}, "error_streak": 0, "error_notified": False}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ============================================================
# メイン
# ============================================================


def main() -> None:
    app_id = os.environ["RAKUTEN_APP_ID"]
    access_key = os.environ["RAKUTEN_ACCESS_KEY"]
    state = load_state()
    hotel_states = state.get("hotels", {})

    vacant = check_all_hotels(app_id, access_key)

    if vacant is None:
        # ---- 取得失敗(障害カウント) ----
        state["error_streak"] = state.get("error_streak", 0) + 1
        if state["error_streak"] >= ERROR_THRESHOLD and not state.get("error_notified"):
            send_line(
                "⚠️ 空室監視システムでエラーが続いています。\n"
                f"{state['error_streak']}回連続で空室情報を取得できていません。\n"
                "GitHubのActionsログを確認してください。"
            )
            state["error_notified"] = True
        save_state(state)
        return

    # ---- 正常に取得できた ----
    if state.get("error_notified"):
        send_line("✅ 空室監視システムが復旧しました。監視を継続しています。")
    state["error_streak"] = 0
    state["error_notified"] = False

    for hotel_no, name in HOTELS.items():
        key = str(hotel_no)
        was_vacant = hotel_states.get(key, {}).get("vacant", False)
        now_vacant = hotel_no in vacant
        print(f"{name}: before={was_vacant} now={now_vacant}")

        if now_vacant and not was_vacant:
            info = vacant[hotel_no]
            price = info.get("min_price")
            price_str = f"{price:,}円〜" if price else "料金は予約ページで確認"
            url = info.get("url") or f"https://travel.rakuten.co.jp/HOTEL/{hotel_no}/{hotel_no}.html"
            send_line(
                "🏨 空室が出ました!\n"
                f"{name}\n"
                f"{CHECKIN} → {CHECKOUT}({ADULTS}名・禁煙)\n"
                f"{price_str}\n"
                f"今すぐ予約 → {url}"
            )
            print("notified!")

        hotel_states[key] = {"vacant": now_vacant}

    state["hotels"] = hotel_states
    save_state(state)


if __name__ == "__main__":
    main()
