#!/usr/bin/env python3
"""한국거래소(KRX) 시장 데이터 수집 스크립트.

KRX 정보데이터시스템(data.krx.co.kr)이 2025년부터 데이터 조회에 로그인을
요구하면서 익명 스크래핑이 막혔다. 대안으로 KRX 실시간 피드를 공급받는
네이버 금융 모바일 API(`m.stock.naver.com/api/index`)를 경유해 다음을 수집한다.

- KOSPI / KOSDAQ / KOSPI 200 종가·등락률·전일종가
- 각 지수의 52주 최고/최저
- KOSPI 투자자별 순매수(외국인/기관/개인, 단위: 억원)
- 최근 5 영업일 종가로부터 산출한 주간 변동률
- USD/KRW 환율 (서울외국환중개 기준, 네이버 경유)

결과는 ``data/market.json`` 으로 저장되며 GitHub Actions 스케줄에서
주기적으로 갱신된다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

KST = timezone(timedelta(hours=9))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}

# (표시명, 네이버 지수코드, KRX 티커)
INDICES: list[tuple[str, str, str]] = [
    ("KOSPI",     "KOSPI",  "1001"),
    ("KOSDAQ",    "KOSDAQ", "2001"),
    ("KOSPI 200", "KPI200", "1028"),
]

BASE = "https://m.stock.naver.com/api/index/{code}"
BASIC_URL = BASE + "/basic"
INTEGRATION_URL = BASE + "/integration"
PRICE_URL = BASE + "/price"
FX_URL = (
    "https://m.stock.naver.com/front-api/marketIndex/prices"
    "?category=exchange&reutersCode={code}&pageSize=10"
)


def _to_float(text: Any) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).replace(",", "").replace("+", "").strip()
    if not t or t == "-":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _apply_direction(value: float | None, ftype_name: str) -> float | None:
    """fluctuationsType 가 FALLING 이면 부호를 뒤집는다 (네이버는 절댓값 반환)."""
    if value is None:
        return None
    if ftype_name == "FALLING" and value > 0:
        return -value
    return value


def _get(url: str) -> dict | list | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[warn] GET failed {url}: {exc}", file=sys.stderr)
        return None


def fetch_index(display_name: str, code: str, ticker: str) -> dict[str, Any] | None:
    """basic + integration + price(5일) 를 합쳐 풍부한 지수 스냅샷을 반환."""
    basic = _get(BASIC_URL.format(code=code))
    if not isinstance(basic, dict):
        return None

    close = _to_float(basic.get("closePrice"))
    diff = _to_float(basic.get("compareToPreviousClosePrice"))
    pct = _to_float(basic.get("fluctuationsRatio"))
    ftype = (basic.get("fluctuationsType") or {}).get("name") or ""
    diff = _apply_direction(diff, ftype) or 0.0
    pct = _apply_direction(pct, ftype) or 0.0
    traded_at = basic.get("localTradedAt") or ""

    if close is None:
        return None

    snapshot: dict[str, Any] = {
        "name": display_name,
        "ticker": ticker,
        "naverCode": code,
        "close": round(close, 2),
        "change": round(diff, 2),
        "changePct": round(pct, 2),
        "date": traded_at[:10] if traded_at else None,
        "tradedAt": traded_at or None,
        "marketStatus": basic.get("marketStatus"),
    }

    integration = _get(INTEGRATION_URL.format(code=code))
    if isinstance(integration, dict):
        infos = {
            ti.get("code"): _to_float(ti.get("value"))
            for ti in integration.get("totalInfos") or []
        }
        snapshot["prevClose"] = infos.get("lastClosePrice")
        snapshot["open"] = infos.get("openPrice")
        snapshot["high"] = infos.get("highPrice")
        snapshot["low"] = infos.get("lowPrice")
        snapshot["high52w"] = infos.get("highPriceOf52Weeks")
        snapshot["low52w"] = infos.get("lowPriceOf52Weeks")

        # 투자자별 매매동향 (단위: 억원) — KOSPI/KOSDAQ만 제공
        deal = integration.get("dealTrendInfo") or {}
        if deal and deal.get("foreignValue") is not None:
            snapshot["dealTrend"] = {
                "bizdate": deal.get("bizdate"),
                "foreign":       _to_float(deal.get("foreignValue")),
                "personal":      _to_float(deal.get("personalValue")),
                "institutional": _to_float(deal.get("institutionalValue")),
                "unit": "억원",
            }

    # 5 영업일 종가로 주간 변동률 산출
    price_rows = _get(PRICE_URL.format(code=code) + "?pageSize=7")
    if isinstance(price_rows, list) and len(price_rows) >= 2:
        closes = [_to_float(row.get("closePrice")) for row in price_rows[:6]]
        closes = [c for c in closes if c is not None]
        if len(closes) >= 2:
            latest_c = closes[0]
            base_c = closes[-1]
            snapshot["week"] = {
                "change": round(latest_c - base_c, 2),
                "changePct": round((latest_c - base_c) / base_c * 100, 2)
                if base_c else 0.0,
                "samples": len(closes),
            }

    return snapshot


def fetch_fx(reuters_code: str, display: str) -> dict[str, Any] | None:
    d = _get(FX_URL.format(code=reuters_code))
    if not isinstance(d, dict):
        return None
    rows = d.get("result") or []
    if not rows:
        return None

    latest = rows[0]
    close = _to_float(latest.get("closePrice"))
    diff = _to_float(latest.get("fluctuations"))
    pct = _to_float(latest.get("fluctuationsRatio"))
    ftype = (latest.get("fluctuationsType") or {}).get("name") or ""
    diff = _apply_direction(diff, ftype) or 0.0
    pct = _apply_direction(pct, ftype) or 0.0

    snap = {
        "name": display,
        "reutersCode": reuters_code,
        "close": round(close, 2) if close is not None else None,
        "change": round(diff, 2),
        "changePct": round(pct, 2),
        "date": latest.get("localTradedAt"),
    }
    # 주간(최근 5 영업일) 변동률
    history_closes = [_to_float(r.get("closePrice")) for r in rows[:6]]
    history_closes = [c for c in history_closes if c is not None]
    if len(history_closes) >= 2 and close is not None:
        base = history_closes[-1]
        snap["week"] = {
            "change": round(close - base, 2),
            "changePct": round((close - base) / base * 100, 2) if base else 0.0,
            "samples": len(history_closes),
        }
    return snap


def main() -> int:
    snapshots: list[dict[str, Any]] = []
    for display, code, ticker in INDICES:
        snap = fetch_index(display, code, ticker)
        if snap:
            snapshots.append(snap)
            msg = (
                f"[info] {display}: {snap['close']:.2f} "
                f"({snap['changePct']:+.2f}%) [{snap.get('date')}]"
            )
            if snap.get("week"):
                msg += f" · 주간 {snap['week']['changePct']:+.2f}%"
            if snap.get("dealTrend"):
                f = snap["dealTrend"]["foreign"]
                if f is not None:
                    msg += f" · 외국인 {f:+,.0f}억"
            print(msg)
        else:
            print(f"[warn] {display}: no data", file=sys.stderr)

    fx = fetch_fx("FX_USDKRW", "USD/KRW")
    if fx:
        week = (
            f" · 주간 {fx['week']['changePct']:+.2f}%"
            if fx.get("week") else ""
        )
        print(f"[info] USD/KRW: {fx['close']:.2f} ({fx['changePct']:+.2f}%){week}")

    payload = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "Naver Finance Mobile API (KRX real-time feed)",
        "notice": (
            "KRX 정보데이터시스템(data.krx.co.kr)이 로그인 월을 도입하여 "
            "익명 직접조회가 불가함에 따라 KRX 실시간 시세를 공급받는 "
            "네이버 금융 모바일 API를 경유한다. 값 단위: 지수=pt, 환율=KRW, "
            "투자자별 순매수=억원."
        ),
        "indices": snapshots,
        "fx": [fx] if fx else [],
    }

    out = Path(__file__).resolve().parent.parent / "data" / "market.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[info] wrote {out}")
    return 0 if snapshots else 1


if __name__ == "__main__":
    raise SystemExit(main())
