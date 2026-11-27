import re,sys,json,os
# 지역분석 표 지역유형·인구감소지역 열 포함 (2026-11-25 재배포, 게시 전 대기 추가)
from datetime import datetime,timedelta
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J=lambda *p:os.path.join(ROOT,*p)
SITE=open(J("templates","tpl15.html"),encoding="utf-8").read()
DAN=open(J("templates","tpl_dan3.html"),encoding="utf-8").read()
# ---- 기준일·분석기간 문구를 오늘 날짜에 맞게 바꿈 (build_region.py 의 창 계산과 같은 규칙)
_k=datetime.utcnow()+timedelta(hours=9)
CUR=os.environ.get("ASOF_YM") or f"{_k.year}{_k.month:02d}"
def _mm(c,k):
    n=int(c[:4])*12+int(c[4:])-1+k; return f"{n//12}{n%12+1:02d}"
def _lab(a,b):
    a,b=_mm(CUR,a),_mm(CUR,b)
    return f"{a[:4]}-{a[4:]}~{b[4:]}" if a[:4]==b[:4] else f"{a[:4]}-{a[4:]}~{b[:4]}-{b[4:]}"
def _one(k):
    z=_mm(CUR,k); return f"{z[:4]}-{z[4:]}"
for old,new in (("@@V@@",_lab(-6,0)),("@@N@@",_one(-1)),("@@O@@",_one(-6)),("2026-08~10",_lab(-3,-1)),("2026-03~05",_lab(-8,-6))):
    DAN=DAN.replace(old,new)
assert 'const ASOF="2026-11-14";' in DAN
DAN=DAN.replace('const ASOF="2026-11-14";','const ASOF="%s";'%_k.strftime("%Y-%m-%d"))
NAMES="pinfo bar fld row chk file tab rg badge spacer panel bk gr meta count msg err tbl nm chip g1 g2 g3 g4 g5 sum up dn notes rules empty lab on rwrap rbtn rpop rcol rli".split()
def cls_attr(m):
    out=[]
    for t in m.group(1).split():
        base=re.sub(r"\$\{[^}]*\}","",t)
        if t in NAMES or t.startswith("g${"): out.append("dn-"+t)
        else:
            out.append(t)
    return 'class="'+" ".join(out)+'"'
# ---- split dan template
style=re.search(r"<style>(.*?)</style>",DAN,re.S).group(1)
body=DAN.split("</style>",1)[1]
html=re.search(r'<div class="wrap">\n(.*?)\n</div>\n\n<script>',body,re.S).group(1)
js=re.search(r"<script>\n(.*)</script>\s*$",body,re.S).group(1)
assert "__DATA__" in js
# ---- CSS
lines=style.split("\n")
start=[i for i,l in enumerate(lines) if l.startswith("h2{")][0]
keep=[l for l in lines[start:] if l.strip() and not l.startswith(".sub{") and not l.startswith("@media (max-width:640px)")]
sel_re=re.compile(r"\.("+"|".join(NAMES)+r")(?![\w-])")
out=[]
for l in keep:
    m=re.match(r"^(.*?)\{(.*)\}$",l)
    assert m,l
    sels=[ "#viewDan "+sel_re.sub(r".dn-\1",s.strip()) for s in m.group(1).split(",")]
    out.append(",".join(sels)+"{"+m.group(2)+"}")
css="\n".join(out)
css="/* ===== 단소지수 탭 ===== */\n#viewDan{--panel:var(--card);--ink:var(--fg);--muted:var(--mute);--soft:var(--accent-soft);--accent-ink:var(--on-accent);--good:var(--buy);--bad:var(--up);--warn:var(--sell);--warnbg:var(--accent-soft);--font:var(--f-body)}\n"+\
":root{--g1:#eceff4;--g2:#d3e1f5;--g3:#a9c6ee;--g4:#6c9fe0;--g5:#1f5fbf;--g1i:#5d6676;--g2i:#1b3a66;--g3i:#12315c;--g4i:#0b2447;--g5i:#ffffff}\n"+\
"@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--g1:#252c3a;--g2:#2a3b5c;--g3:#34528a;--g4:#4a78c4;--g5:#78a8f2;--g1i:#9aa4b5;--g2i:#cfe0fa;--g3i:#e6efff;--g4i:#ffffff;--g5i:#0b1426}}\n"+\
":root[data-theme=\"dark\"]{--g1:#252c3a;--g2:#2a3b5c;--g3:#34528a;--g4:#4a78c4;--g5:#78a8f2;--g1i:#9aa4b5;--g2i:#cfe0fa;--g3i:#e6efff;--g4i:#ffffff;--g5i:#0b1426}\n"+\
"#viewDan{font-family:var(--f-body);font-size:14px;line-height:1.5}\n#viewDan [hidden]{display:none!important}\n"+css+"\n"
# ---- HTML
html=re.sub(r'(\sid=")([^"]*)"',lambda m:m.group(1)+"dn_"+m.group(2)+'"',html)
html=re.sub(r'aria-controls="([^"]*)"',lambda m:'aria-controls="dn_'+m.group(1)+'"',html)
html=re.sub(r'class="([^"]*)"',cls_attr,html)
view='  <div class="view" id="viewDan" hidden>\n'+html+'\n  </div>\n'
# ---- JS
js=js.replace("const $=id=>document.getElementById(id);",'const V=document.getElementById("viewDan");\nconst $=id=>document.getElementById("dn_"+id);')
js=js.replace("document.querySelectorAll(","V.querySelectorAll(").replace('document.addEventListener(','V.addEventListener(')
js=js.replace('V.querySelectorAll(".rg")','V.querySelectorAll(".dn-rg")').replace('".panel input[type=checkbox]"','".dn-panel input[type=checkbox]"').replace('".panel input[type=number]"','".dn-panel input[type=number]"')
js=js.replace('"#t th"','"#dn_t th"').replace('classList.toggle("on"','classList.toggle("dn-on"')
js=js.replace('className="msg err"','className="dn-msg dn-err"').replace('className="msg"','className="dn-msg"')
js=re.sub(r'(\sid=")([^"]*)"',lambda m:m.group(1)+"dn_"+m.group(2)+'"',js)
js=re.sub(r'class="([^"]*)"',cls_attr,js)
js=js.replace("const BASE=__DATA__;","const BASE=__DANDATA__;")
js="<script>\n(function(){\n"+js.rstrip()+"\n})();\n</script>\n"
# ---- site patches
def rep(s,a,b,n=1):
    assert s.count(a)==n,(s.count(a),a[:70]); return s.replace(a,b)
S=SITE
S=rep(S,"</style>",css+"</style>")
S=rep(S,'<a href="#compare" id="tabCmp">지역비교</a></nav>','<a href="#compare" id="tabCmp">지역비교</a><a href="#dan" id="tabDan">단소지수</a></nav>')
S=rep(S,"</main>",view+"</main>")
S=rep(S,'const flow=location.hash==="#flow",cmp=location.hash==="#compare";','const flow=location.hash==="#flow",cmp=location.hash==="#compare",dan=location.hash==="#dan";')
S=rep(S,'Q("#viewFlow").hidden=!flow;Q("#viewAna").hidden=flow||cmp;Q("#viewCmp").hidden=!cmp;','Q("#viewFlow").hidden=!flow;Q("#viewAna").hidden=flow||cmp||dan;Q("#viewCmp").hidden=!cmp;Q("#viewDan").hidden=!dan;')
S=rep(S,'Q("#tabAna").setAttribute("aria-current",flow||cmp?"false":"page");','Q("#tabAna").setAttribute("aria-current",flow||cmp||dan?"false":"page");Q("#tabDan").setAttribute("aria-current",dan?"page":"false");')
assert S.rstrip().endswith("</script>")
S=S.rstrip()+"\n"+js
os.makedirs(J("build"),exist_ok=True)
seed=open(J("data","seed.json"),encoding="utf-8").read().strip()
dan=open(J("build","dan_all.json"),encoding="utf-8").read().strip()
assert S.count("__DATA__")==1 and S.count("__DANDATA__")==1
F=S.replace("__DATA__",seed).replace("__DANDATA__",dan)
# ---- 단독 사이트(GitHub Pages)용 문서 뼈대: 아티팩트에서는 자동으로 붙던 doctype·문자셋·모바일 viewport·기본 리셋
SKEL=('<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
      '<meta name="theme-color" content="#f3f5f8">'
      '<style>:root{color-scheme:light}body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n')
if not F.lstrip().lower().startswith("<!doctype"): F=SKEL+F+"\n</html>\n"
os.makedirs(J("docs"),exist_ok=True)
open(J("docs","index.html"),"w",encoding="utf-8").write(F)
print("tpl16",len(S)//1024,"KB site16",len(F)//1024,"KB")
# audit leftovers
print("class tokens still unprefixed in view:",set(re.findall(r'class="([^"]*)"',view))-set())
print(sorted(set(re.findall(r'class="([^"]*)"',html)))[:40])
