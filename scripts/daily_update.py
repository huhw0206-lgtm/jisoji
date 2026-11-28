# -*- coding: utf-8 -*-
"""매일 한 번 실행되는 자동 수집기.

순서 (하루 호출 한도 5,000건 중 BUDGET 건까지만 사용)
 1) 이미 받은 지역: 최근 2개월 매매·전월세만 새로 받아 덮어씀 (지역당 약 8~20건)
 2) 매월 1일 또는 수동 실행(FORCE_BASS=1): 단지 목록 갱신 + 못 받은 기본정보 재시도
 2-1) 분양권 전매(silv.csv)·과거 12개월→24개월 이어받기(hist.txt)
 3) 아직 안 받은 지역: 순서대로 처음부터 수집 (예산이 다 되면 멈추고 내일 이어서)
키는 환경변수 DATA_GO_KR_KEY (GitHub Secrets) 로 받습니다.
"""
import os, sys, time
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import collect_yeonsu as cy
import collect_all as ca

ca.OUT = os.path.join(ROOT, "data", "수집결과")
ca.REGIONS["인천 연수구"] = "28185"
BUDGET = int(os.environ.get("CALL_BUDGET", "4000"))
KST = datetime.utcnow() + timedelta(hours=9)
FORCE = os.environ.get("FORCE_BASS") == "1" or KST.day == 1
KEEP_MONTHS = 26            # 24개월 + 여유 (이보다 오래된 거래는 정리)
HIST_MONTHS = 24            # 과거 이어받기(backfill) 목표 개월 수
SILV_MONTHS = 12            # 분양권 전매 수집 개월 수
URL_SILV = "https://apis.data.go.kr/1613000/RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade"
T0 = time.time()
MAX_MIN = int(os.environ.get("MAX_MINUTES", "85"))   # 이 시간이 지나면 스스로 멈추고 저장 단계로 넘어감

calls = 0
_orig = cy.call
def counted(*a, **k):
    global calls
    if calls >= BUDGET:
        sys.exit("[중단] 오늘 쓸 호출 예산에 도달했습니다 (한도)")
    if time.time() - T0 > MAX_MIN * 60:
        sys.exit(f"[중단] 실행 시간 {MAX_MIN}분에 도달했습니다 (한도) - 받은 데이터를 저장하고 내일 이어서 합니다")
    calls += 1
    return _orig(*a, **k)
cy.call = counted
cy.SLEEP = 0.1


def refresh_recent(name, code):
    d = ca.region_dir(name); cy.HERE = d; cy.SIGUNGU = code
    months = cy.months_back(2)
    cutoff = cy.months_back(KEEP_MONTHS)[-1]
    for fname, url in (("trades.csv", cy.URL_TRADE), ("rents.csv", cy.URL_RENT)):
        new = []
        for ym in months:
            rows = cy.paged(url, {"LAWD_CD": code, "DEAL_YMD": ym})
            for r in rows: r["_조회월"] = ym
            new += rows; time.sleep(cy.SLEEP)
        old = [r for r in cy.read_csv(fname) if r.get("_조회월") not in months and r.get("_조회월", "999999") >= cutoff]
        cy.save_csv(fname, old + new)


def _hist_file(d): return os.path.join(d, "hist.txt")


def backfill(name, code):
    """이미 받은 지역의 과거 달(12개월 이전 → 24개월)을 하루 예산 안에서 이어받습니다. 받은 가장 오래된 달은 hist.txt 에 기록."""
    d = ca.region_dir(name); cy.HERE = d; cy.SIGUNGU = code
    goal = cy.months_back(HIST_MONTHS)[-1]
    hp = _hist_file(d)
    earliest = open(hp).read().strip() if os.path.exists(hp) else cy.months_back(12)[-1]
    have = [r.get("_조회월") for r in cy.read_csv("trades.csv") if r.get("_조회월")]
    if have: earliest = min(earliest, min(have))      # 처음부터 24개월로 받은 지역은 다시 받지 않음
    if earliest <= goal: return False
    todo = [m for m in sorted(cy.months_back(HIST_MONTHS)) if goal <= m < earliest]
    for ym in reversed(todo):                      # 가까운 과거부터 한 달씩
        for fname, url in (("trades.csv", cy.URL_TRADE), ("rents.csv", cy.URL_RENT)):
            rows = cy.paged(url, {"LAWD_CD": code, "DEAL_YMD": ym})
            for r in rows: r["_조회월"] = ym
            old = [r for r in cy.read_csv(fname) if r.get("_조회월") != ym]
            cy.save_csv(fname, old + rows); time.sleep(cy.SLEEP)
        open(hp, "w").write(ym)
    return True


def silv_month_rows(code, ym):
    items, _ = cy.call(URL_SILV, {"LAWD_CD": code, "DEAL_YMD": ym, "pageNo": 1, "numOfRows": 1000}, tries=2, soft=True)
    if items is None: return None
    rows = list(items); total = _
    page = 1
    while len(rows) < total and items:
        page += 1
        items, total = cy.call(URL_SILV, {"LAWD_CD": code, "DEAL_YMD": ym, "pageNo": page, "numOfRows": 1000}, tries=2, soft=True)
        if not items: break
        rows += items
    for r in rows: r["_조회월"] = ym
    return rows


def silv_refresh(name, code):
    """분양권 전매 실거래: silv.csv 가 없으면 최근 12개월을 받고, 있으면 최근 2개월만 갱신. 없는 서비스면 건너뜀."""
    d = ca.region_dir(name); cy.HERE = d; cy.SIGUNGU = code
    path = os.path.join(d, "silv.csv")
    months = cy.months_back(SILV_MONTHS) if not os.path.exists(path) else cy.months_back(2)
    new = []
    for ym in months:
        rows = silv_month_rows(code, ym)
        if rows is None: return False
        new += rows; time.sleep(cy.SLEEP)
    old = []
    if os.path.exists(path):
        old = [r for r in cy.read_csv("silv.csv") if r.get("_조회월") not in months and r.get("_조회월", "999999") >= cy.months_back(KEEP_MONTHS)[-1]]
    cy.save_csv("silv.csv", old + new)
    return True


def refresh_master(name, code):
    """단지 목록 + 기본정보(새로 생긴 단지, 이전에 못 받은 단지만)"""
    d = ca.region_dir(name); cy.HERE = d; cy.SIGUNGU = code
    cy.step_list(); cy.step_bass()


def stop_on(e, name):
    if ca.quota_hit(e.code):
        print(f"\n[멈춤] {name}: 호출 한도/예산 도달 -> 내일 이어서 합니다.\n{e.code}")
        return True
    print(f"\n[오류] {name}: {e.code}  (이 지역은 건너뜀)")
    with open(os.path.join(ca.OUT, "오류.txt"), "a", encoding="utf-8") as f:
        f.write(f"{KST:%Y-%m-%d} {name}: {e.code}\n")
    return False


def main():
    os.makedirs(ca.OUT, exist_ok=True)
    cy.MONTHS = ca.MONTHS
    done = [k for k in ca.REGIONS if ca.is_done(k)]
    todo = [k for k in ca.REGIONS if not ca.is_done(k)]
    print(f"완료 지역 {len(done)}곳, 미수집 {len(todo)}곳, 예산 {BUDGET}건, 마스터 갱신={FORCE}")
    for name in done:
        try:
            refresh_recent(name, ca.REGIONS[name])
            if FORCE: refresh_master(name, ca.REGIONS[name])
        except SystemExit as e:
            if stop_on(e, name): print(f"사용한 호출 {calls}건"); return
        print(f"  {name}: 최근 2개월 갱신 (누적 호출 {calls})")
    # 분양권 전매(신축 단지 거래 보완용): 지역마다 최근 12개월 한 번, 이후 2개월씩 갱신
    silv_ok = True
    for name in done:
        if not silv_ok: break
        try:
            if os.path.getsize(os.path.join(ca.region_dir(name), "trades.csv")) < 20: continue
            silv_ok = silv_refresh(name, ca.REGIONS[name])
            if not silv_ok: print("  [알림] 분양권 전매 API를 쓸 수 없어 건너뜁니다 (활용신청·승인 여부를 확인하세요)")
        except SystemExit as e:
            if stop_on(e, name): print(f"사용한 호출 {calls}건"); return
    # 과거 이어받기: 12개월 이전 → 24개월
    for name in done:
        try:
            if os.path.getsize(os.path.join(ca.region_dir(name), "trades.csv")) < 20: continue
            if backfill(name, ca.REGIONS[name]): print(f"  {name}: 과거 이어받기 (누적 호출 {calls})")
        except SystemExit as e:
            if stop_on(e, name): print(f"사용한 호출 {calls}건"); return
    for name in todo:
        try:
            ca.run_region(name, ca.REGIONS[name])
        except SystemExit as e:
            if stop_on(e, name): break
    print(f"\n오늘 사용한 호출 {calls}건 / 완료 지역 {sum(ca.is_done(k) for k in ca.REGIONS)}곳")


if __name__ == "__main__":
    main()
