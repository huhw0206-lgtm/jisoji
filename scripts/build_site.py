# -*- coding: utf-8 -*-
"""data/수집결과/<지역>/ 의 CSV로 단소지수 행을 만들고 docs/index.html(사이트)을 조립합니다."""
import os, sys, json, subprocess, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_region as br

SRC = os.path.join(ROOT, "data", "수집결과")
need = ["apt_list.csv", "apt_bass.csv", "trades.csv", "rents.csv"]
rows, ok, bad = [], [], []
for name in sorted(os.listdir(SRC)):
    d = os.path.join(SRC, name)
    if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "done.txt")): continue
    if not all(os.path.exists(os.path.join(d, f)) for f in need): continue
    if any(os.path.getsize(os.path.join(d, f)) < 20 for f in need):      # 자료가 비어 있는 지역(코드 변경·거래 없음)은 건너뜀
        bad.append(f"{name}: 수집 자료가 비어 있습니다(시군구 코드 확인 필요)"); continue
    try:
        r, m, n = br.build(d, name)
        rows += r; ok.append(f"{name} {len(r)}행 (거래 연결 {br.build.share*100:.1f}%)")
    except Exception as e:
        bad.append(f"{name}: {e}"); traceback.print_exc()
os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
json.dump(rows, open(os.path.join(ROOT, "build", "dan_all.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\n".join(ok)); 
if bad: print("실패:", *bad, sep="\n  ")
print("단소지수 합계", len(rows), "행")
if not rows: sys.exit("만들 행이 없습니다.")
subprocess.check_call([sys.executable, os.path.join(HERE, "merge_dan.py")])
