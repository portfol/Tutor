#!/usr/bin/env python3
"""한국거래소(KRX) 시장 데이터 수집 스크립트.

KRX 정보데이터시스템(data.krx.co.kr)이 2025년부터 데이터 조회에 로그인을
요구하면서 익명 스크래핑이 사실상 막혔다. 대안으로 KRX로부터 실시간 시세를
공급받아 배포하는 네이버 금융 모바일 API를 이용해 주요 지수 종가와 환율을
수집한 뒤 ``data/market.json``에 저장한다.

GitHub Actions 스케줄에서 주기적으로 실행되어 정적 페이지(`app.js`)가
fetch 할 수 있는 JSON 산출물을 갱신한다.
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

# 네이버 금융 종목(지수) 코드 — KRX 공식 코드와 1:1 매핑된다.
#   KOSPI     -> KOSPI
#   KOSDAQ    -> KOSDAQ
#   KOSPI 200 -> KPI200
INDICES: list[tuple[str, str, str]] = [
    # (표시명,      네이버 코드, KRX 티커)
    ("KOSPI",      "KOSPI",  "1001"),
    ("KOSDAQ",     "KOSDAQ", "2001"),
    ("KOSPI 200",  "KPI200", "1028"),
]

INDEX_URL = "https://m.stock.naver.com/api/index/{code}/basic"
FX_URL = (
    "https://m.stock.naver.com/front-api/marketIndex/prices"
    "?category=exchange&reutersCode={code}&pageSize=10"
)


def _to_float(text: str | float | int | None) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).replace(",", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fetch_index(display_name: str, code: str, ticker: str) -> dict[str, Any] | None:
    """네이버 금융 모바일 API에서 지수 basic 정보를 수집."""
    try:
        r = requests.get(INDEX_URL.format(code=code), headers=HEADERS, timeout=10)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        print(f"[warn] {display_name} fetch failed: {exc}", file=sys.stderr)
        return None

    close = _to_float(d.get("closePrice"))
    diff = _to_float(d.get("compareToPreviousClosePrice"))
    pct = _to_float(d.get("fluctuationsRatio"))
    traded_at = d.get("localTradedAt") or ""
    direction = (d.get("compareToPreviousPrice") or {}).get("name") if isinstance(
        d.get("compareToPreviousPrice"), dict
    ) else None

    if close is None:
        return None

    # fluctuationsType 은 RISING / FALLING / FLAT 등
    ftype = (d.get("fluctuationsType") or {})
    if isinstance(ftype, dict):
        ftype_name = ftype.get("name") or ""
    else:
        ftype_name = ""
    if ftype_name == "FALLING" and diff is not None and diff > 0:
        diff = -diff
    if ftype_name == "FALLING" and pct is not None and pct > 0:
        pct = -pct

    return {
        "name": display_name,
        "ticker": ticker,
        "naverCode": code,
        "close": round(close, 2),
        "change": round(diff, 2) if diff is not None else 0.0,
        "changePct": round(pct, 2) if pct is not None else 0.0,
        "date": traded_at[:10] if traded_at else None,
        "tradedAt": traded_at or None,
        "marketStatus": d.get("marketStatus"),
    }


def fetch_fx(reuters_code: str, display: str) -> dict[str, Any] | None:
    try:
        r = requests.get(FX_URL.format(code=reuters_code), headers=HEADERS, timeout=10)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        print(f"[warn] {display} fetch failed: {exc}", file=sys.stderr)
        return None

    rows = (d or {}).get("result") or []
    if not rows:
        return None
    latest = rows[0]
    close = _to_float(latest.get("closePrice"))
    diff = _to_float(latest.get("fluctuations"))
    pct = _to_float(latest.get("fluctuationsRatio"))
    ftype = (latest.get("fluctuationsType") or {}).get("name") or ""
    if ftype == "FALLING":
        if diff is not None and diff > 0:
            diff = -diff
        if pct is not None and pct > 0:
            pct = -pct
    return {
        "name": display,
        "reutersCode": reuters_code,
        "close": round(close, 2) if close is not None else None,
        "change": round(diff, 2) if diff is not None else 0.0,
        "changePct": round(pct, 2) if pct is not None else 0.0,
        "date": latest.get("localTradedAt"),
    }


def main() -> int:
    snapshots: list[dict[str, Any]] = []
    for display, code, ticker in INDICES:
        snap = fetch_index(display, code, ticker)
        if snap:
            snapshots.append(snap)
            print(
                f"[info] {display}: {snap['close']:.2f} "
                f"({snap['changePct']:+.2f}%) [{snap['date']}]"
            )
        else:
            print(f"[warn] {display}: no data", file=sys.stderr)

    fx = fetch_fx("FX_USDKRW", "USD/KRW")
    if fx:
        print(
            f"[info] USD/KRW: {fx['close']:.2f} "
            f"({fx['changePct']:+.2f}%) [{fx['date']}]"
        )

    payload = {
        "updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "Naver Finance Mobile API (KRX real-time feed)",
        "notice": (
            "KRX 정보데이터시스템(data.krx.co.kr) 이 로그인 월을 도입하여 "
            "익명 직접조회가 불가함에 따라 KRX 데이터를 실시간 제공하는 "
            "네이버 금융 모바일 API를 경유한다."
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
