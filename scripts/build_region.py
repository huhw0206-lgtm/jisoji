# -*- coding: utf-8 -*-
"""지역 폴더(apt_list/apt_bass/trades/rents CSV 4개) -> 단소지수 탭용 행(JSON)
사용: python3 build_region.py <폴더> <지역이름> <출력.json>"""
import pandas as pd, numpy as np, re, json, os, sys
from datetime import datetime, timedelta

def _asof():
    """기준월(YYYYMM). 환경변수 ASOF_YM 이 있으면 그 값, 없으면 오늘(한국시간)."""
    v=os.environ.get("ASOF_YM","").strip()
    if v: return v
    k=datetime.utcnow()+timedelta(hours=9); return f"{k.year}{k.month:02d}"
def mm(cur,k):
    """기준월 cur 에서 k개월 이동한 YYYYMM"""
    n=int(cur[:4])*12+int(cur[4:])-1+k; return f"{n//12}{n%12+1:02d}"

def build(folder, region):
    rd=lambda n:pd.read_csv(os.path.join(folder,n),dtype=str)
    t=rd("trades.csv"); b=rd("apt_bass.csv"); rr=rd("rents.csv")
    tcan=t[t.cdealType.fillna("")=="O"].drop_duplicates().copy()   # 해제(취소) 신고 건: 표는 거래량에 포함
    t=t[t.cdealType.fillna("")!="O"].drop_duplicates()
    t["amt"]=t.dealAmount.str.replace(",","").astype(float); t["ar"]=t.excluUseAr.astype(float)
    t["ym"]=t.dealYear+t.dealMonth.str.zfill(2)
    tcan["ar"]=tcan.excluUseAr.astype(float); tcan["ym"]=tcan.dealYear+tcan.dealMonth.str.zfill(2)
    norm=lambda s:re.sub(r"[\s\(\)\-·,./]|아파트|단지","",str(s))
    loc=lambda s:re.search(r"(\S+(?:동|읍|면|가|리))\s+(\d+(?:-\d+)?)",str(s))
    b["nm"]=b.kaptName.map(norm)
    b["dg"]=b.kaptAddr.map(lambda s:loc(s).group(1) if loc(s) else None)
    b["jb"]=b.kaptAddr.map(lambda s:loc(s).group(2) if loc(s) else None)
    try:                                                   # 주소에 번지가 없어 동을 못 읽은 단지는 단지목록의 동 정보로 채움
        _al=rd("apt_list.csv"); _dm=dict(zip(_al.kaptCode,_al.as3)); b["dg"]=b.apply(lambda r_:r_.dg if isinstance(r_.dg,str) and r_.dg else _dm.get(r_.kaptCode),axis=1)
    except Exception: pass
    import pandas as _pd
    cx=_pd.concat([t[["aptSeq","aptNm","umdNm","jibun"]],rr[["aptSeq","aptNm","umdNm","jibun"]]]).groupby("aptSeq").agg(nm=("aptNm","first"),dong=("umdNm","first"),jb=("jibun","first")).reset_index()
    def _fz(cn,bn,ct):
        # 같은 번지에 여러 단지일 때: 숫자 토큰(차수·단지) 겹침 + 공통 글자로 가장 가까운 단지 고르기
        dg=lambda z:set(re.findall(r"\d+",z)); a=dg(cn); bb=dg(bn)
        cm=max((l for l in range(len(cn),1,-1) if any(cn[i:i+l] in bn for i in range(len(cn)-l+1))),default=0)
        return (len(a&bb)-0.5*len(a^bb))+cm*0.1
    import difflib
    DONGS=set(b.dg.dropna())|(set(rd("apt_list.csv").as3.dropna()) if os.path.exists(os.path.join(folder,"apt_list.csv")) else set())
    def _dfix(z_):                                           # "공도읍 용두리" 같은 읍·면+리 표기 → 단지 주소의 동(리) 표기에 맞춤
        if not isinstance(z_,str) or z_ in DONGS or " " not in z_: return z_
        ps_=z_.split()
        for q_ in (ps_[-1],ps_[0]):
            if q_ in DONGS: return q_
        return z_
    cx["dong"]=cx.dong.map(_dfix)
    def n2(z,strip=True):
        z=str(z).lower()
        z=re.sub(r"\([^)]*\)","",z)                      # (701동) (874) 같은 괄호 표기 제거
        for a_,b_ in (("e-편한","e편한"),("이편한","e편한"),("이-편한","e편한"),("엘에이치","lh"),("엘지","lg"),("현대아이파크","아이파크"),("에이치","h"),("view","뷰"),("에스케이","sk"),("힐스테이트","힐스테이트")): z=z.replace(a_,b_)
        if strip:
            for d_ in DONGS: z=z.replace(str(d_).lower(),"")     # 동 이름이 들어간 표기는 동 이름 제거
        return re.sub(r"[\s\-·,./_]|아파트|단지|\d+동$","",z)
    def dgt(z):
        o=set()
        for m_ in re.findall(r"\d+",z):
            o.add(m_)
            if len(m_)>=3 and all(int(m_[i+1])==int(m_[i])+1 for i in range(len(m_)-1)): o|=set(m_)   # 3456단지 → 3,4,5,6단지
        return o
    def sim(a_,b_):
        a_,b_=n2(a_),n2(b_)
        if len(a_)<2 or len(b_)<2: return 0
        if a_==b_: return 1.0
        da,db=dgt(a_),dgt(b_)
        if da and db and not (da&db): return 0          # 차수·단지 숫자가 전혀 안 겹치면 다른 단지
        r_=difflib.SequenceMatcher(None,a_,b_).ratio()
        if min(len(a_),len(b_))>=4 and (a_ in b_ or b_ in a_) and min(len(a_),len(b_))/max(len(a_),len(b_))>=0.5: r_=max(r_,0.8)
        if bool(da)!=bool(db) and (da|db)!={"1"}: r_*=0.8   # 한쪽만 차수가 있으면 감점(1단지/1차는 기본값이라 제외)
        return r_
    try: al=rd("apt_list.csv")
    except Exception: al=None
    pool=b[["kaptCode","kaptName","dg","jb"]].copy()
    if al is not None:
        al2=al.rename(columns={"as3":"dg"}); al2["jb"]=None
        al2=al2[~al2.kaptCode.isin(pool.kaptCode)][["kaptCode","kaptName","dg","jb"]]
        pool=pd.concat([pool,al2])
    pool["has"]=pool.kaptCode.isin(b.kaptCode)
    main=lambda j:str(j).split("-")[0] if j is not None else None
    missing_bass={}
    mp={}
    for _,c in cx.iterrows():
        cn=norm(c.nm); s=b[(b.dg==c.dong)&(b.jb==c.jb)]
        if len(s)==1:
            if sim(c.nm,s.iloc[0].kaptName)<0.9:                    # 번지는 같지만 이름이 다름 → 같은 동에 이름이 거의 똑같은 단지가 있으면 그쪽으로
                alt=b[(b.dg==c.dong)&(b.kaptCode!=s.iloc[0].kaptCode)]
                alt=alt[alt.kaptName.map(lambda z:sim(c.nm,z)>=0.97).astype(bool)]
                if len(alt)==1: mp[c.aptSeq]=alt.iloc[0].kaptCode; continue
            mp[c.aptSeq]=s.iloc[0].kaptCode; continue
        if len(s)>1:
            s2=s[s.nm.map(lambda x:x==cn or x in cn or cn in x)]
            if len(s2)>=1: mp[c.aptSeq]=s2.iloc[0].kaptCode; continue
            sc=[(_fz(cn,r_.nm,None)+(5 if ("임대" in str(c.nm))==(r_.codeSaleNm=="임대") else 0),r_.kaptCode,r_.nm) for _,r_ in s.iterrows()]
            sc=[z for z in sc if any(cn[i:i+2] in z[2] for i in range(len(cn)-1))]
            sc.sort(reverse=True)
            if sc and (len(sc)==1 or sc[0][0]>sc[1][0]): mp[c.aptSeq]=sc[0][1]; continue
        s=b[(b.dg==c.dong)&(b.nm==cn)]
        if len(s)==1: mp[c.aptSeq]=s.iloc[0].kaptCode; continue
        s=b[(b.dg==c.dong)&b.nm.map(lambda x:len(x)>=2 and (x in cn or cn in x))]
        if len(s)==1: mp[c.aptSeq]=s.iloc[0].kaptCode
        if c.aptSeq in mp: continue
        # 보정 단계: 같은 동(또는 같은 본번) 안에서 이름 유사도로 고름
        cand=pool[(pool.dg==c.dong)]
        short=len(n2(c.nm,False))<4                               # 이름이 너무 짧으면(한솔, 롯데…) 같은 번지일 때만 인정
        if short:                                          # 짧은 이름: 같은 번지이거나, 같은 동에서 이름을 포함하는 단지가 딱 하나일 때만
            key=n2(c.nm)
            cj=cand[cand.jb.map(lambda j:j is not None and main(j)==main(c.jb)).astype(bool)]
            ck=cand[cand.kaptName.map(lambda z:len(key)>=2 and key in n2(z) and sim(c.nm,z)>0).astype(bool)]
            cand=cj if len(cj) else (ck if len(ck)==1 else cand.iloc[0:0])
        if not short:                                      # 이름에서 차수를 뺀 핵심어가 같은 동 단지 이름에 포함되고 그런 단지가 하나뿐이면 인정
            key2=re.sub(r"\d+(단지|차)?$","",n2(c.nm))
            allk=cand[cand.kaptName.map(lambda z:len(key2)>=4 and key2 in n2(z)).astype(bool)]
            ck2=(allk[allk.kaptName.map(lambda z:sim(c.nm,z)>0).astype(bool)] if len(allk)==1 else allk[allk.kaptName.map(lambda z:sim(c.nm,z)>0 and bool(dgt(n2(z)))).astype(bool)])   # 같은 이름 단지가 여럿이면 차수가 맞는 것만
            if len(ck2)==1:
                r_=ck2.iloc[0]
                if r_.has: mp[c.aptSeq]=r_.kaptCode
                else: missing_bass[c.aptSeq]=r_.kaptCode
                continue
        sc=sorted([(sim(c.nm,r_.kaptName)+(0.15 if main(r_.jb)==main(c.jb) and r_.jb is not None else 0),r_.kaptCode,r_.has) for _,r_ in cand.iterrows()],key=lambda x:(x[0],str(x[1])),reverse=True)
        if short and (not sc or sc[0][0]<0.5): continue
        if not sc or sc[0][0]<0.7:
            sc=sorted([(sim(c.nm,r_.kaptName),r_.kaptCode,r_.has) for _,r_ in pool.iterrows()],key=lambda x:(x[0],str(x[1])),reverse=True)   # 동 표기가 다른 경우
            if short or not sc or sc[0][0]<0.85: continue
        if len(sc)>1 and sc[0][0]-sc[1][0]<0.05 and sc[0][0]<0.95: continue
        if sc[0][2]: mp[c.aptSeq]=sc[0][1]
        else: missing_bass[c.aptSeq]=sc[0][1]
    t["kc"]=t.aptSeq.map(mp)
    tcan["kc"]=tcan.aptSeq.map(mp)
    rr["mr"]=rr.monthlyRent.str.replace(",","").astype(float); rr["dep"]=rr.deposit.str.replace(",","").astype(float)
    rr["ar"]=rr.excluUseAr.astype(float); rr["ym"]=rr.dealYear+rr.dealMonth.str.zfill(2); rr["kc"]=rr.aptSeq.map(mp)
    rr=rr[(rr.mr==0)&rr.kc.notna()].drop_duplicates()
    band=lambda a:0 if a<=60 else 1 if a<=85 else 2 if a<=135 else 3
    t["dgn"]=t.umdNm.map(_dfix)
    t["bd"]=t.ar.map(band); t["pyeong"]=t.ar/3.3058; rr["bd"]=rr.ar.map(band)
    pb=lambda p:10 if p<20 else 20 if p<30 else 30 if p<40 else 40
    CUR=_asof(); CY,CM=int(CUR[:4]),int(CUR[4:])
    # W6 = 표 기준: 6개월 전 달부터 당월까지
    W6=[mm(CUR,k) for k in range(-6,1)]; R3=[mm(CUR,k) for k in (-3,-2,-1)]; O3=[mm(CUR,k) for k in (-8,-7,-6)]; M12S=mm(CUR,-11); M13S=mm(CUR,-12)
    w6=t[t.ym.isin(W6)]
    dist={k:g.amt.sum()/g.pyeong.sum() for k,g in w6.groupby("bd")}
    allp=w6.amt.sum()/w6.pyeong.sum(); c=0.704
    rows=[]
    # K-apt 면적정보: 단지코드별 전용면적별 세대수 (data/kapt_area.csv). 없으면 기존 4개 구간 방식.
    KA={}
    _kp=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data","kapt_area.csv")
    if os.path.exists(_kp):
        for _c,_g in pd.read_csv(_kp,dtype={"kaptCode":str}).groupby("kaptCode"): KA[_c]=list(zip(_g.ar.astype(float),_g.ho.astype(int)))
    for _,x in b.iterrows():
        try: tot=int(float(x.hoCnt)) if float(x.hoCnt or 0)>0 else int(float(x.kaptdaCnt))
        except: continue
        if tot<100 or not isinstance(x.kaptUsedate,str) or len(x.kaptUsedate)<6: continue
        u=x.kaptUsedate; ym=f"{u[:4]}-{u[4:6]}"; age=(CY*12+CM-(int(u[:4])*12+int(u[4:6])))//12
        hh=[int(float(x[k] or 0)) for k in ["kaptMparea60","kaptMparea85","kaptMparea135","kaptMparea136"]]
        g=t[t.kc==x.kaptCode]; gr=rr[rr.kc==x.kaptCode]
        tys=sorted(set(g[g.ym>=M12S].ar.round(2))|set(gr[gr.ym>=M12S].ar.round(2)))
        kt=KA.get(x.kaptCode)
        def _tk(a_):
            if not kt: return None
            k_=min(kt,key=lambda z:abs(z[0]-a_))
            return k_ if abs(k_[0]-a_)<=0.5 else None
        units=[(band(a_),(hh[band(a_)] if hh[band(a_)]>0 else tot),a_) for a_ in tys]
        if kt:
            units=[(band(a_),(_tk(a_)[1] if _tk(a_) else (hh[band(a_)] if hh[band(a_)]>0 else tot)),a_) for a_ in tys]
        if not units: units=[(None,tot,None)]
        for bd,hv,ar0 in units:
            gb=g if bd is None else g[g.bd==bd]; g6=gb[gb.ym.isin(W6)]; v6=len(g6)
            if kt and ar0 is not None and _tk(ar0) is not None:           # 타입(전용면적)별 거래량: 같은 K-apt 타입에 배정되는 거래만
                _t0=_tk(ar0); v6=int(sum(1 for a_,m_ in zip(g.ar,g.ym) if m_ in W6 and _tk(a_)==_t0))
                _gc=tcan[tcan.kc==x.kaptCode]; v6+=int(sum(1 for a_,m_ in zip(_gc.ar,_gc.ym) if m_ in W6 and _tk(a_)==_t0))
            src=g6 if v6 else gb[gb.ym>=M13S]
            pp=src.amt.sum()/src.pyeong.sum() if len(src) else None
            py=round((gb.ar.median() if len(gb) else (84 if bd is None else [50,72,100,150][bd]))*1.3/3.3058)
            PB=pb(py); BASE=allp if bd is None else dist.get(bd)
            if BASE is None: BASE=allp
            pr=round(pp/BASE*100) if pp else None
            tr=round(v6/hv*100,1)
            gp=gb.assign(pp=gb.amt/gb.pyeong)
            a=gp[gp.ym.isin(R3)].pp; o=gp[gp.ym.isin(O3)].pp
            N=round(a.median()) if len(a) else None; O=round(o.median()) if len(o) else None
            dr=round((N/O-1)*100) if N and O else None
            s=[(1 if tot<200 else 2 if tot<=500 else 3 if tot<=1000 else 4 if tot<2000 else 5),
               5 if age<=5 else 4 if age<=10 else 3 if age<=15 else 2 if age<=25 else 1,
               1 if pr is None or pr<=70 else 2 if pr<=100 else 3 if pr<=130 else 4 if pr<160 else 5,
               1 if tr<=0.6 else 2 if tr<=1.2 else 3 if tr<=1.8 else 4 if tr<=2.4 else 5,
               1 if dr is None or dr<=1 else 2 if dr<=7 else 3 if dr<=12 else 4 if dr<=19 else 5]
            # 매매·전세 시세: 같은 평형(전용면적 묶음) 거래만, 가장 최근 거래 1건 기준. 평형마다 한 행.
            keep=[(ar0,ar0,int((g.ar.round(2)==ar0).sum()))] if ar0 is not None else [(None,None,0)]
            split=True
            def latest(df,c_):
                if c_[0] is None or not len(df): return None,0
                q=df[(df.ar.round(2)==c_[0])&(df.ym>=M12S)]
                n=len(q)
                if not n: return None,0
                q=q.assign(dd=q.dealDay.astype(int))
                return q.sort_values(["ym","dd"]).iloc[-1],n
            for c_ in keep:
                rp,pn=latest(gb,c_); rj,jn=latest(gr if bd is None else gr[gr.bd==bd],c_)
                P=float(rp.amt) if rp is not None else None; J=float(rj.dep) if rj is not None else None
                gap=round(P-J) if P and J else None; jr=round(J/P*100,1) if P and J else None
                pyx=round(((c_[0]+c_[1])/2)*1.3/3.3058) if c_[0] is not None else py
                # 평당가: 그 평형의 가장 최근 매매가 ÷ 공급평(전용×1.3÷3.3058). 평당가율은 같은 구간 시군구 평균과 같은 전용평 기준으로 비교(배율 무관).
                recent=[]
                if ar0 is not None and len(gb):
                    q_=gb[(gb.ar.round(2)==ar0)&(gb.ym>=M12S)]
                    if len(q_): q_=q_.assign(dd=q_.dealDay.astype(int)).sort_values(["ym","dd"]); recent=list(q_.amt.tail(3))   # 이 평형 최근 거래 최대 3건
                if recent and BASE:
                    used=len(recent); mp_=float(np.median(recent)); ppd=round(mp_/pyx); pr_r=round((mp_/(ar0/3.3058))/BASE*100)
                else:
                    used=0; ppd=round(pp/1.3) if pp else None; pr_r=pr
                # 실거래가율: 같은 평형(평수) 거래의 직전월 평균 매매가 ÷ 6개월 전 달 평균 매매가 − 1 (표 기준과 동일)
                if kt and ar0 is not None and _tk(ar0) is not None:       # 같은 K-apt 타입에 배정되는 거래만 (타입별 평균)
                    _t0=_tk(ar0); _gp=g[g.ar.map(lambda z_:_tk(z_)==_t0).astype(bool)]
                else: _gp=gb[(gb.ar*1.3/3.3058).round()==pyx]
                # N: 직전월까지 중 거래가 있는 가장 최근 달의 평균, O: 6개월 전 달(없으면 그 이전 가장 가까운 달)의 평균
                _ym_n=sorted(m_ for m_ in set(_gp.ym) if m_<=mm(CUR,-1) and m_>=M13S)
                _ym_o=sorted(m_ for m_ in set(_gp.ym) if m_<=mm(CUR,-6) and m_>=M13S)
                _a=_gp[_gp.ym==_ym_n[-1]].amt if _ym_n else _gp.iloc[0:0].amt
                _o=_gp[_gp.ym==_ym_o[-1]].amt if _ym_o else _gp.iloc[0:0].amt
                N_=round(_a.mean()) if len(_a) else None; O_=round(_o.mean()) if len(_o) else None
                dr_=round((N_/O_-1)*100) if N_ and O_ else None
                s_r=list(s); s_r[4]=1 if dr_ is None or dr_<=1 else 2 if dr_<=7 else 3 if dr_<=12 else 4 if dr_<=19 else 5; s_r[2]=1 if pr_r is None or pr_r<=70 else 2 if pr_r<=100 else 3 if pr_r<=130 else 4 if pr_r<160 else 5
                # 선정 조건: 단지 평당가 > 동 평당가 > 구 평당가 (모두 최근 6개월 중위 전용평당가, 같은 전용 구간끼리)
                def _med(df_): return float((df_.amt/df_.pyeong).median()) if len(df_) else None
                _dp=_med(_gp[_gp.ym.isin(W6)]); _dn=0; _dw=6; _ddp=None; _gg=None
                if bd is not None:
                    _tb=t[t.bd==bd]; _gg=_med(_tb[_tb.ym.isin(W6)])
                    _td=_tb[_tb.dgn==x.dg]; _x6=_td[_td.ym.isin(W6)]
                    if len(_x6)>=5: _ddp=_med(_x6); _dn=len(_x6)
                    else:
                        _x12=_td[_td.ym>=M13S]; _dw=12
                        if len(_x12)>=5: _ddp=_med(_x12); _dn=len(_x12)
                _ok=None if (_dp is None or _ddp is None or _gg is None) else int(_dp>_ddp>_gg)
                cond=[_dp and round(_dp),_ddp and round(_ddp),_gg and round(_gg),_ok,_dn,_dw]
                ex=[None]*5
                if rp is not None: ex[0]=float(rp.ar); ex[1]=f"{rp.ym[:4]}-{rp.ym[4:]}-{int(rp.dealDay):02d}"; ex[3]=str(rp.floor)
                if rj is not None: ex[2]=f"{rj.ym[:4]}-{rj.ym[4:]}-{int(rj.dealDay):02d}"; ex[4]=str(rj.floor)+"층"+(" · "+rj.contractType if isinstance(rj.contractType,str) else "")
                bl0='전체(최근 12개월 거래 없음)' if bd is None else ['전용 60㎡ 이하','전용 60~85㎡','전용 85~135㎡','전용 135㎡ 초과'][bd]
                bl=bl0+(f" · {ar0:g}㎡형" if ar0 is not None else "")
                row=[region,x.dg,x.kaptName,tot,pyx,hv,ym,age,ppd,round(BASE/1.3),pr_r,v6,tr,N_,O_,dr_]+s_r+[sum(s_r)]+[None]*12+[v6,None,None,None,None]
                row[22]=gap; row[23]=jr; row[24:29]=ex; row[29]=used
                row+=[round(P) if P else None, round(J) if J else None, pn, jn, bl,
                      {10:'10평형대',20:'20평형대',30:'30평형대',40:'40평형대 이상'}[pb(pyx)], len(_a), len(_o)]+cond
                rows.append(row)
    build.share=round(t.kc.notna().mean(),3)
    build.mp=mp; build.mb=missing_bass; build.cx=cx; build.b=b; build.t=t
    return rows, len(mp), t.aptSeq.nunique()

if __name__=="__main__":
    rows,m,n=build(sys.argv[1],sys.argv[2]); json.dump(rows,open(sys.argv[3],"w"),ensure_ascii=False,separators=(",",":"))
    print(f"{sys.argv[2]}: {len(rows)}행, 단지 {len({r[2] for r in rows})}곳, 거래 단지 연결 {m}/{n} (거래 건수 기준 {build.share*100:.1f}%)")
