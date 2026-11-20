# -*- coding: utf-8 -*-
"""매일 한 번 실행되는 자동 수집기.

순서 (하루 호출 한도 5,000건 중 BUDGET 건까지만 사용)
 1) 이미 받은 지역: 최근 2개월 매매·전월세만 새로 받아 덮어씀 (지역당 약 8~20건)
 2) 매월 1일 또는 수동 실행(FORCE_BASS=1): 단지 목록 갱신 + 못 받은 기본정보 재시도
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
KEEP_MONTHS = 14
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
    for name in todo:
        try:
            ca.run_region(name, ca.REGIONS[name])
        except SystemExit as e:
            if stop_on(e, name): break
    print(f"\n오늘 사용한 호출 {calls}건 / 완료 지역 {sum(ca.is_done(k) for k in ca.REGIONS)}곳")


if __name__ == "__main__":
    main()
