#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수도권(서울·인천·경기) 시군구 일괄 수집기.  collect_yeonsu.py 와 같은 폴더에 두세요.

사용법 (Windows 명령 프롬프트):
    set DATA_GO_KR_KEY=여기에_인증키
    python collect_all.py              # 아직 안 받은 지역 전부 (이어받기)
    python collect_all.py 서울         # 서울만
    python collect_all.py 경기         # 경기만
    python collect_all.py "서울 노원구" "서울 금천구"   # 지정한 지역만
    python collect_all.py --목록        # 지역 목록과 진행 상태만 보기

하루 호출 한도(5,000건)에 걸리면 알아서 멈춥니다. 다음 날 같은 명령을 다시 실행하면
받은 지역은 건너뛰고 이어서 받습니다.

결과: 이 폴더 안의 '수집결과' 폴더에 지역별로 저장됩니다.
    수집결과/서울 노원구/apt_list.csv, apt_bass.csv, trades.csv, rents.csv
"""
import os
import sys
import time

import collect_yeonsu as cy

MONTHS = 12   # 단소지수 계산에는 최근 12개월이면 충분합니다.

REGIONS = {
    # ---- 서울 ----
    "서울 종로구": "11110", "서울 중구": "11140", "서울 용산구": "11170", "서울 성동구": "11200",
    "서울 광진구": "11215", "서울 동대문구": "11230", "서울 중랑구": "11260", "서울 성북구": "11290",
    "서울 강북구": "11305", "서울 도봉구": "11320", "서울 노원구": "11350", "서울 은평구": "11380",
    "서울 서대문구": "11410", "서울 마포구": "11440", "서울 양천구": "11470", "서울 강서구": "11500",
    "서울 구로구": "11530", "서울 금천구": "11545", "서울 영등포구": "11560", "서울 동작구": "11590",
    "서울 관악구": "11620", "서울 서초구": "11650", "서울 강남구": "11680", "서울 송파구": "11710",
    "서울 강동구": "11740",
    # ---- 인천 (연수구는 이미 받았으므로 제외) ----
    "인천 제물포구": "28125", "인천 영종구": "28155", "인천 미추홀구": "28177", "인천 남동구": "28200",
    "인천 부평구": "28237", "인천 계양구": "28245", "인천 서해구": "28275", "인천 검단구": "28290",
    "인천 강화군": "28710", "인천 옹진군": "28720",
    # ---- 경기 ----
    "경기 수원시 장안구": "41111", "경기 수원시 권선구": "41113", "경기 수원시 팔달구": "41115",
    "경기 수원시 영통구": "41117", "경기 성남시 수정구": "41131", "경기 성남시 중원구": "41133",
    "경기 성남시 분당구": "41135", "경기 의정부시": "41150", "경기 안양시 만안구": "41171",
    "경기 안양시 동안구": "41173", "경기 부천시 원미구": "41192", "경기 부천시 소사구": "41194", "경기 부천시 오정구": "41196", "경기 광명시": "41210",
    "경기 평택시": "41220", "경기 동두천시": "41250", "경기 안산시 상록구": "41271",
    "경기 안산시 단원구": "41273", "경기 고양시 덕양구": "41281", "경기 고양시 일산동구": "41285",
    "경기 고양시 일산서구": "41287", "경기 과천시": "41290", "경기 구리시": "41310",
    "경기 남양주시": "41360", "경기 오산시": "41370", "경기 시흥시": "41390", "경기 군포시": "41410",
    "경기 의왕시": "41430", "경기 하남시": "41450", "경기 용인시 처인구": "41461",
    "경기 용인시 기흥구": "41463", "경기 용인시 수지구": "41465", "경기 파주시": "41480",
    "경기 이천시": "41500", "경기 안성시": "41550", "경기 김포시": "41570", "경기 화성시 만세구": "41591", "경기 화성시 효행구": "41593", "경기 화성시 병점구": "41595", "경기 화성시 동탄구": "41597",
    "경기 광주시": "41610", "경기 양주시": "41630", "경기 포천시": "41650", "경기 여주시": "41670",
    "경기 연천군": "41800", "경기 가평군": "41820", "경기 양평군": "41830",
}

OUT = os.path.join(cy.HERE, "수집결과")
FILES = ["apt_list.csv", "apt_bass.csv", "trades.csv", "rents.csv"]


def region_dir(name):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    return d


def is_done(name):
    return os.path.exists(os.path.join(OUT, name, "done.txt"))


def quota_hit(msg):
    m = str(msg)
    return ("resultCode=22" in m or "LIMITED" in m.upper() or "EXCEEDS" in m.upper()
            or "한도" in m)


def bass_complete(d):
    try:
        cy.HERE = d
        lst = cy.read_csv("apt_list.csv")
        got = {r["kaptCode"] for r in cy.read_csv("apt_bass.csv")
               if r.get("kaptCode") and sum(1 for v in r.values() if v) > 1}
        return all(r.get("kaptCode") in got for r in lst if r.get("kaptCode"))
    except SystemExit:
        return False


def run_region(name, code):
    d = region_dir(name)
    cy.HERE = d
    cy.SIGUNGU = code
    cy.MONTHS = MONTHS
    print(f"\n===== {name} ({code}) =====")
    steps = [("apt_list.csv", cy.step_list), ("apt_bass.csv", cy.step_bass),
             ("trades.csv", cy.step_trade), ("rents.csv", cy.step_rent)]
    for fname, fn in steps:
        path = os.path.join(d, fname)
        if fname == "apt_bass.csv":
            if os.path.exists(path) and bass_complete(d):
                continue
        elif os.path.exists(path):
            continue
        cy.HERE = d
        fn()
    cy.HERE = d
    lst = cy.read_csv("apt_list.csv")
    if not lst:
        with open(os.path.join(OUT, "확인필요.txt"), "a", encoding="utf-8") as f:
            f.write(f"{name} ({code}): 단지 목록이 0건입니다. 시군구 코드를 확인하세요.\n")
        print(f"[확인필요] {name}: 단지 목록 0건 (코드 확인 필요)")
    with open(os.path.join(d, "done.txt"), "w", encoding="utf-8") as f:
        f.write("ok")


def pick(args):
    if not args:
        return list(REGIONS)
    out = []
    for a in args:
        if a in REGIONS:
            out.append(a)
        else:
            out += [k for k in REGIONS if k.startswith(a + " ") or k.startswith(a)]
    seen = []
    for k in out:
        if k not in seen:
            seen.append(k)
    return seen


def main():
    args = sys.argv[1:]
    if "--목록" in args:
        for k, v in REGIONS.items():
            print(("[완료] " if is_done(k) else "[대기] ") + f"{k} ({v})")
        print(f"\n전체 {len(REGIONS)}곳, 완료 {sum(is_done(k) for k in REGIONS)}곳")
        return
    targets = [k for k in pick(args) if not is_done(k)]
    if not targets:
        print("받을 지역이 없습니다(이미 모두 완료했거나 이름이 맞지 않습니다). --목록 으로 확인하세요.")
        return
    print(f"이번에 받을 지역 {len(targets)}곳. 한도에 걸리면 자동으로 멈춥니다.")
    for name in targets:
        try:
            run_region(name, REGIONS[name])
        except SystemExit as e:
            if quota_hit(e.code):
                print(f"\n[중단] 오늘 호출 한도에 걸린 것 같습니다. 내일 같은 명령을 다시 실행하세요.\n{e.code}")
                return
            print(f"\n[오류] {name}: {e.code}\n  이 지역은 건너뛰고 다음으로 갑니다.")
            os.makedirs(OUT, exist_ok=True)
            with open(os.path.join(OUT, "오류.txt"), "a", encoding="utf-8") as f:
                f.write(f"{name}: {e.code}\n")
        time.sleep(1)
    print("\n이번 실행이 끝났습니다. --목록 으로 진행 상태를 보세요.")


if __name__ == "__main__":
    main()
