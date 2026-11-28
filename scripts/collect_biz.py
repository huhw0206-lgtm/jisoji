"""경기분석 탭용 월별 지표 수집 → data/biz.json
 - 내수경기: 통계청(KOSIS) 경기종합지수 '동행지수 순환변동치'   (환경변수 KOSIS_API_KEY)
 - 기준금리: 한국은행(ECOS) 기준금리                          (환경변수 ECOS_API_KEY)
 - 유동성  : 한국은행(ECOS) Lf(광의유동성) 전년동월대비 증가율    (환경변수 ECOS_API_KEY)
실패해도 기존 data/biz.json 을 그대로 두고 정상 종료합니다(사이트 빌드가 멈추지 않게). 진단 내용은 data/biz_log.txt."""
import os,sys,json,re,urllib.request,urllib.parse,datetime
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,"data","biz.json"); LOG=os.path.join(ROOT,"data","biz_log.txt")
log=[]
def say(*a): s=" ".join(str(x) for x in a); log.append(s); print(s)
def get(url,timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))
def ym_now(): k=datetime.datetime.utcnow()+datetime.timedelta(hours=9); return f"{k.year}{k.month:02d}"
def nospace(s): return re.sub(r"\s+","",str(s))
def to_f(v):
    try: return float(str(v).replace(",",""))
    except: return None

# ---------- KOSIS: 동행지수 순환변동치 ----------
def kosis(key):
    base="https://kosis.kr/openapi/"
    cands=[]
    for t in ("DT_1C8015","DT_1C8014","DT_1C8016"): cands.append(t)
    try:   # 표 이름으로도 찾아 봄
        q=urllib.parse.urlencode(dict(method="getList",apiKey=key,vwCd="MT_ZTITLE",searchNm="경기종합지수",orgId="101",format="json",jsonVD="Y",sortOrd="RANK",startCount=1,resultCount=30))
        for r in get(base+"statisticsSearch.do?"+q):
            if "경기종합지수" in r.get("TBL_NM","") and r.get("TBL_ID") not in cands: cands.append(r["TBL_ID"]); say("KOSIS 검색 표:",r.get("TBL_ID"),r.get("TBL_NM"))
    except Exception as e: say("KOSIS 표 검색 실패:",e)
    end=ym_now()
    for tbl in cands:
        got={}; ok=False
        for y0 in range(2000,int(end[:4])+1,6):
            s=f"{y0}01"; e=f"{min(y0+5,int(end[:4]))}12"
            q=urllib.parse.urlencode(dict(method="getList",apiKey=key,itmId="ALL",objL1="ALL",format="json",jsonVD="Y",prdSe="M",startPrdDe=s,endPrdDe=e,orgId="101",tblId=tbl))
            try: rows=get(base+"Param/statisticsParameterData.do?"+q)
            except Exception as ex: say("KOSIS",tbl,s,"호출 실패:",ex); rows=[]
            if isinstance(rows,dict): say("KOSIS",tbl,s,"응답:",str(rows)[:200]); rows=[]
            for r in rows:
                nm=nospace(" ".join(str(r.get(k,"")) for k in r if k.endswith("_NM")))
                if "동행" in nm and "순환변동치" in nm:
                    v=to_f(r.get("DT")); 
                    if v is not None: got[r["PRD_DE"]]=v; ok=True
        if ok: say("KOSIS 사용 표:",tbl,"개월수",len(got)); return got
    say("KOSIS: 동행지수 순환변동치를 찾지 못했습니다"); return {}

# ---------- ECOS ----------
def ecos_rows(key,stat,cycle,s,e,item=""):
    url=f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/{stat}/{cycle}/{s}/{e}/{item}"
    d=get(url)
    if "StatisticSearch" not in d: say("ECOS",stat,item,"응답:",str(d)[:200]); return []
    return d["StatisticSearch"].get("row",[])
def ecos_rate(key):
    rows=ecos_rows(key,"722Y001","M","200001",ym_now(),"0101000")
    r={x["TIME"]:to_f(x["DATA_VALUE"]) for x in rows if to_f(x["DATA_VALUE"]) is not None}
    say("기준금리 개월수",len(r)); return r
def ecos_lf(key):
    # 통계표 목록에서 '유동성' 표를 찾고, 그 안에서 Lf 항목을 찾음
    try: tl=get(f"https://ecos.bok.or.kr/api/StatisticTableList/{key}/json/kr/1/10000/")["StatisticTableList"]["row"]
    except Exception as e: say("ECOS 표목록 실패:",e); return {}
    tabs=[t for t in tl if "유동성" in t.get("STAT_NAME","") and t.get("CYCLE","")!="" and "M" in t.get("CYCLE","")]
    for t in tabs: say("ECOS 유동성 표:",t.get("STAT_CODE"),t.get("STAT_NAME"))
    for t in tabs:
        code=t["STAT_CODE"]
        try: items=get(f"https://ecos.bok.or.kr/api/StatisticItemList/{key}/json/kr/1/1000/{code}")["StatisticItemList"]["row"]
        except Exception as e: say("항목목록 실패",code,e); continue
        lf=[i for i in items if re.search(r"Lf|광의유동성",i.get("ITEM_NAME","")) and i.get("CYCLE","M")=="M"]
        for i in lf: say("  Lf 후보:",code,i.get("ITEM_CODE1"),i.get("ITEM_NAME"))
        # 증가율 항목이 있으면 우선, 없으면 수준값에서 직접 계산
        def pick(pred):
            for i in lf:
                if pred(i.get("ITEM_NAME","")): return i
        inc=pick(lambda n:"증감률" in n or "증가율" in n)
        if inc:
            rows=ecos_rows(key,code,"M","200001",ym_now(),inc["ITEM_CODE1"])
            r={x["TIME"]:to_f(x["DATA_VALUE"]) for x in rows if to_f(x["DATA_VALUE"]) is not None}
            if r: say("Lf 증가율 항목 사용:",inc["ITEM_NAME"],len(r)); return r
        lev=pick(lambda n:"평잔" in n and "계절" not in n) or pick(lambda n:"계절" not in n) or (lf[0] if lf else None)
        if lev:
            rows=ecos_rows(key,code,"M","199901",ym_now(),lev["ITEM_CODE1"])
            lv={x["TIME"]:to_f(x["DATA_VALUE"]) for x in rows if to_f(x["DATA_VALUE"]) is not None}
            r={}
            for m,v in lv.items():
                p=f"{int(m[:4])-1}{m[4:]}"
                if p in lv and lv[p]: r[m]=round((v/lv[p]-1)*100,2)
            if r: say("Lf 수준값에서 전년동월 증가율 계산:",lev["ITEM_NAME"],len(r)); return r
    say("Lf 시리즈를 찾지 못했습니다"); return {}

def main():
    old={}
    if os.path.exists(OUT):
        try: old=json.load(open(OUT,encoding="utf-8"))
        except Exception: old={}
    new=dict(old); new.setdefault("coin",{}); new.setdefault("rate",{}); new.setdefault("lf",{})
    kk,ek=os.environ.get("KOSIS_API_KEY","").strip(),os.environ.get("ECOS_API_KEY","").strip()
    for name,fn,key in (("coin",kosis,kk),("rate",ecos_rate,ek),("lf",ecos_lf,ek)):
        if not key: say(name,": API 키가 없어 건너뜁니다"); continue
        try: r=fn(key)
        except Exception as e: say(name,"수집 실패:",e); r={}
        if r: new[name]=dict(sorted(r.items()))
    new["updated"]=(datetime.datetime.utcnow()+datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    json.dump(new,open(OUT,"w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
    open(LOG,"w",encoding="utf-8").write("\n".join(log)+"\n")
    say("저장:",{k:len(v) for k,v in new.items() if isinstance(v,dict)})
if __name__=="__main__":
    try: main()
    except Exception as e: print("경기지표 수집 오류(무시하고 계속):",e)
