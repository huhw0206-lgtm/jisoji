#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
인천 연수구 단지 데이터 수집기 (표준 라이브러리만 사용, 설치 불필요)

사용법 (Windows 명령 프롬프트 기준):
    set DATA_GO_KR_KEY=여기에_인증키
    python collect_yeonsu.py list      # 1) 단지 목록
    python collect_yeonsu.py basic     # 2) 단지 기본정보
    python collect_yeonsu.py trade     # 3) 최근 N개월 매매 실거래
    python collect_yeonsu.py rent      # 4) 최근 N개월 전월세 실거래
    python collect_yeonsu.py all       # 위 네 가지 순서대로

맥/리눅스:  export DATA_GO_KR_KEY=여기에_인증키

결과 파일은 이 스크립트가 있는 폴더에 저장됩니다.
    apt_list.csv, apt_basic.csv, trades.csv, rents.csv
"""
import csv
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

# ---------------- 설정 ----------------
SIGUNGU = "28185"          # 인천 연수구 법정동 시군구 코드 5자리
MONTHS = 36                # 실거래 몇 개월치를 받을지 (최근 달부터 과거로)
SLEEP = 0.15               # 호출 간격(초)

# 엔드포인트: 포털 활용신청 상세페이지의 '요청주소'와 다르면 여기만 고치세요.
URL_LIST = "https://apis.data.go.kr/1613000/AptListService4/getSigunguAptList4"
URL_BASIC = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusDtlInfoV5"
URL_TRADE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
URL_RENT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
# --------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))


def get_key():
    k = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not k:
        sys.exit("환경변수 DATA_GO_KR_KEY 가 비어 있습니다. 인증키를 먼저 설정하세요.")
    # Encoding 키(%2B 등 포함)를 넣었어도 되도록 한 번 풀었다가 다시 인코딩
    return urllib.parse.quote(urllib.parse.unquote(k), safe="")


class NoService(Exception):
    """해당 주소의 API가 존재하지 않을 때"""


class Transient(Exception):
    """서버의 일시적 오류(재시도하면 되는 경우)"""


def _find_items(o):
    """JSON 안에서 item 목록(딕셔너리 리스트)을 찾아 반환"""
    if isinstance(o, dict):
        for k in ("item", "items"):
            if k in o:
                v = o[k]
                if isinstance(v, dict) and "item" in v:
                    v = v["item"]
                if isinstance(v, dict):
                    return [v]
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
        for v in o.values():
            r = _find_items(v)
            if r is not None:
                return r
    elif isinstance(o, list) and o and all(isinstance(x, dict) for x in o):
        return o
    return None


def parse_json(body, url):
    import json
    d = json.loads(body)
    if isinstance(d, dict) and "OpenAPI_ServiceResponse" in d:
        hdr = (d["OpenAPI_ServiceResponse"] or {}).get("cmmMsgHeader") or {}
        err = hdr.get("errMsg", "")
        if err == "HTTP_ERROR":  # 게이트웨이 일시 오류 → 재시도 대상
            raise Transient("HTTP_ERROR(서버 일시 오류)")
        sys.exit(f"[오류] {err} / {hdr.get('returnAuthMsg', '')} (코드 {hdr.get('returnReasonCode', '')})\n"
                 f"주소: {url}\n(호출 한도 초과·키 미활성·권한 문제일 수 있습니다)")
    code = None
    msg = ""
    h = None
    if isinstance(d, dict):
        h = (d.get("response") or {}).get("header") if isinstance(d.get("response"), dict) else d.get("header")
    if isinstance(h, dict):
        code = str(h.get("resultCode", "")).strip()
        msg = h.get("resultMsg", "")
    if code and code not in ("00", "000", "0"):
        sys.exit(f"[오류] resultCode={code} {msg}\n주소: {url}")
    items = _find_items(d)
    if items is None:
        sys.exit(f"[오류] 응답에서 목록을 찾지 못했습니다.\n주소: {url}\n"
                 f"서버 응답 앞부분:\n{body[:600]}")
    items = [{k: ("" if v is None else str(v).strip()) for k, v in it.items()} for it in items]
    total = 0
    node = d
    for key in ("response", "body"):
        if isinstance(node, dict) and isinstance(node.get(key), dict):
            node = node[key]
    if isinstance(node, dict):
        try:
            total = int(node.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = 0
    return items, total


def call(url, params, tries=3, soft=False):
    """호출 후 (items, totalCount) 반환. 오류면 원문을 보여주고 종료.
    soft=True 이면 일시 오류가 계속될 때 종료하지 않고 (None, 0)을 반환."""
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full = f"{url}?serviceKey={get_key()}&{q}"
    last = ""
    for i in range(tries):
        try:
            with urllib.request.urlopen(full, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            if body.lstrip().startswith(("{", "[")):
                return parse_json(body, url)
            try:
                root = ET.fromstring(body)
            except ET.ParseError:
                sys.exit(f"[오류] XML도 JSON도 아닌 응답입니다.\n주소: {url}\n"
                         f"서버 응답 앞부분:\n{body[:600]}")
            code = (root.findtext(".//resultCode") or "").strip()
            if code not in ("00", "000", "0"):
                msg = root.findtext(".//resultMsg") or ""
                sys.exit(f"[오류] resultCode={code} {msg}\n주소: {url}\n"
                         f"(키 종류 Decoding/Encoding, 활성화 대기, 호출 한도, 주소 오타를 확인하세요)")
            items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
            total = int(root.findtext(".//totalCount") or 0)
            return items, total
        except SystemExit:
            raise
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:600]
            except Exception:
                pass
            if "NO_OPENAPI_SERVICE_ERROR" in body:
                raise NoService(url)
            safe = full.replace(get_key(), "인증키")
            sys.exit(f"[오류] HTTP {e.code}\n서버 응답: {body}\n"
                     f"호출한 주소(키 가림): {safe}\n"
                     f"(포털 상세페이지의 '요청주소'와 '요청변수' 이름이 이것과 같은지 확인하세요)")
        except Exception as e:  # 네트워크/파싱 일시 오류는 재시도
            last = str(e)
            time.sleep(1.5 * (i + 1))
    if soft:
        print(f"  (건너뜀) {last}")
        return None, 0
    sys.exit(f"[오류] 호출 실패: {last}\n주소: {url}")


def save_csv(name, rows):
    path = os.path.join(HERE, name)
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # 엑셀에서 한글 안 깨짐
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {path} ({len(rows)}행)")


def read_csv(name):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        sys.exit(f"{name} 이 없습니다. 먼저 앞 단계를 실행하세요.")
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def paged(url, base, rows_per=1000):
    out, page = [], 1
    while True:
        items, total = call(url, {**base, "pageNo": page, "numOfRows": rows_per})
        out += items
        if not items or len(out) >= total:
            return out
        page += 1
        time.sleep(SLEEP)


# 단지 목록 API는 정확한 주소를 확인하지 못해 후보를 순서대로 시도합니다.
# 포털 상세페이지의 '요청주소'를 알게 되면 맨 위 URL_LIST 하나만 쓰면 됩니다.
LIST_CANDIDATES = [
    (URL_LIST, "sigunguCode"),
    ("https://apis.data.go.kr/1613000/AptListService3/getSigunguAptList3", "sigunguCode"),
    ("https://apis.data.go.kr/1613000/AptListService2/getSigunguAptList", "sigunguCode"),
    ("https://apis.data.go.kr/1613000/AptListService1/getSigunguAptList", "sigunguCode"),
    ("https://apis.data.go.kr/1613000/AptListService/getSigunguAptList", "sigunguCode"),
]


def step_list():
    rows = None
    seen = set()
    for url, pname in LIST_CANDIDATES:
        if url in seen:
            continue
        seen.add(url)
        try:
            rows = paged(url, {pname: SIGUNGU})
            print(f"사용한 주소: {url}")
            break
        except NoService:
            print(f"  (없는 주소) {url}")
    if rows is None:
        sys.exit("[오류] 후보 주소가 모두 없는 서비스입니다.\n"
                 "포털의 '공동주택 단지 목록제공 서비스' 상세페이지에서 '요청주소'와 '요청변수'를 확인해 알려주세요.")
    save_csv("apt_list.csv", rows)
    if rows:
        print("필드:", ", ".join(rows[0].keys()))


def step_basic():
    lst = read_csv("apt_list.csv")
    codes = [r.get("kaptCode") for r in lst if r.get("kaptCode")]
    # 이어받기: 이전에 성공한 단지(코드 외 정보가 있는 행)는 다시 받지 않습니다.
    done = {}
    if os.path.exists(os.path.join(HERE, "apt_basic.csv")):
        for r in read_csv("apt_basic.csv"):
            if r.get("kaptCode") and sum(1 for v in r.values() if v) > 1:
                done[r["kaptCode"]] = r
        if done:
            print(f"  이전에 받은 {len(done)}개는 건너뜁니다.")
    failed = []
    for i, c in enumerate(codes, 1):
        if c in done:
            continue
        items, _ = call(URL_BASIC, {"kaptCode": c}, tries=3, soft=True)
        time.sleep(0.3)  # 너무 빠른 연속 호출을 피함
        if items:
            row = items[0]
            row.setdefault("kaptCode", c)
            done[c] = row
        elif items is None:
            failed.append(c)
            name = next((r.get("kaptName", "") for r in lst if r.get("kaptCode") == c), "")
            print(f"    -> 못 받은 단지: {c} {name}")
        else:
            done[c] = {"kaptCode": c}
        if i % 20 == 0:
            print(f"  기본정보 {i}/{len(codes)}")
            save_csv("apt_basic.csv", list(done.values()))  # 중간 저장
        time.sleep(SLEEP)
    save_csv("apt_basic.csv", list(done.values()))
    if failed:
        print(f"[알림] {len(failed)}개 단지는 서버 오류로 못 받았습니다. "
              f"같은 명령(python collect_yeonsu.py basic)을 다시 실행하면 실패분만 이어서 받습니다.")


def months_back(n):
    y, m = date.today().year, date.today().month
    res = []
    for _ in range(n):
        res.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return res


def step_trade():
    out = []
    for ym in months_back(MONTHS):
        rows = paged(URL_TRADE, {"LAWD_CD": SIGUNGU, "DEAL_YMD": ym})
        for r in rows:
            r["_조회월"] = ym
        out += rows
        print(f"  {ym}: {len(rows)}건")
        time.sleep(SLEEP)
    save_csv("trades.csv", out)


def step_rent():
    out = []
    for ym in months_back(MONTHS):
        rows = paged(URL_RENT, {"LAWD_CD": SIGUNGU, "DEAL_YMD": ym})
        for r in rows:
            r["_조회월"] = ym
        out += rows
        print(f"  {ym}: {len(rows)}건")
        time.sleep(SLEEP)
    save_csv("rents.csv", out)


BASS_CANDIDATES = [
    "https://apis.data.go.kr/1613000/AptBasisInfoServiceV5/getAphusBassInfoV5",
    "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4",
    "https://apis.data.go.kr/1613000/AptBasisInfoServiceV3/getAphusBassInfoV3",
    "https://apis.data.go.kr/1613000/AptBasisInfoServiceV2/getAphusBassInfoV2",
    "https://apis.data.go.kr/1613000/AptBasisInfoService1/getAphusBassInfo",
]


def step_bass():
    """세대수(kaptdaCnt)·사용승인일(kaptUsedate)이 들어 있는 '기본정보'를 받습니다."""
    lst = read_csv("apt_list.csv")
    codes = [r.get("kaptCode") for r in lst if r.get("kaptCode")]
    url = None
    for u in BASS_CANDIDATES:
        missing = False
        for c0 in codes[:5]:          # 한 단지에서 일시 오류가 나도 다른 단지로 다시 확인
            try:
                items, _ = call(u, {"kaptCode": c0}, tries=2, soft=True)
            except NoService:
                print("  없는 주소:", u)
                missing = True
                break
            if items:
                url = u
                print("  사용한 주소:", u)
                print("  첫 단지 응답 필드:", ", ".join(items[0].keys()))
                break
        if url:
            break
        if not missing:               # 없는 주소가 아니라 일시 오류였던 경우: 다음 주소로 넘어가지 않음
            url = u
            print("  (일시 오류로 확인 못 함) 이 주소로 계속 진행:", u)
            break
    if not url:
        sys.exit("[오류] 기본정보 주소를 찾지 못했습니다. 포털 '공동주택 기본 정보제공 서비스' 상세페이지의 "
                 "'기본정보 조회' 요청주소를 알려주세요.")
    done = {}
    if os.path.exists(os.path.join(HERE, "apt_bass.csv")):
        for r in read_csv("apt_bass.csv"):
            if r.get("kaptCode") and sum(1 for v in r.values() if v) > 1:
                done[r["kaptCode"]] = r
        if done:
            print(f"  이전에 받은 {len(done)}개는 건너뜁니다.")
    failed = []
    for i, c in enumerate(codes, 1):
        if c in done:
            continue
        items, _ = call(url, {"kaptCode": c}, tries=3, soft=True)
        time.sleep(0.3)
        if items:
            row = items[0]
            row.setdefault("kaptCode", c)
            done[c] = row
        else:
            failed.append(c)
        if i % 20 == 0:
            print(f"  기본정보 {i}/{len(codes)}")
            save_csv("apt_bass.csv", list(done.values()))
        time.sleep(SLEEP)
    save_csv("apt_bass.csv", list(done.values()))
    if failed:
        print(f"[알림] {len(failed)}개 단지는 못 받았습니다. 같은 명령(python collect_yeonsu.py bass)을 다시 실행하면 이어서 받습니다.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    steps = {"list": [step_list], "basic": [step_basic], "trade": [step_trade],
             "rent": [step_rent], "bass": [step_bass],
             "all": [step_list, step_basic, step_trade, step_rent]}
    if cmd not in steps:
        sys.exit(__doc__)
    for s in steps[cmd]:
        s()
    print("완료")
