import sys,json,pathlib,re,collections
sys.path.insert(0,'/home/wkolbe/MX/PDFDRILL/src')
from pdfdrill import report_tex as rt
LIB=pathlib.Path.home()/"pdfdrill-library"
SP=pathlib.Path("/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da/scratchpad")

# TeX's standard \right delimiters (TeXbook ch.17 + amssymb extensions that
# are declared \delimiter). Anything else after \right is non-standard.
STD = {")","]","}",".","|","/","\\|","\\}","\\]","\\)",
       "\\rangle","\\rceil","\\rfloor","\\rbrace","\\rbrack","\\rparen",
       "\\vert","\\Vert","\\rvert","\\rVert","\\backslash",
       "\\rgroup","\\rmoustache","\\arrowvert","\\Arrowvert","\\bracevert",
       "\\uparrow","\\downarrow","\\updownarrow",
       "\\Uparrow","\\Downarrow","\\Updownarrow"}
CORNER = {"\\lrcorner","\\llcorner","\\ulcorner","\\urcorner"}
ARROWS = {"\\uparrow","\\downarrow","\\updownarrow",
          "\\Uparrow","\\Downarrow","\\Updownarrow"}
RIGHT = re.compile(r"\\right(?![a-zA-Z])\s*(\\[a-zA-Z]+|\\.|[^\s\\])")

tot_docs=tot_rows=refused=0
r_any=r_ns=0                      # rows with \right / with a non-standard one
ref_ns=0                          # REFUSED rows with a non-standard one
pass_ns=0                         # rows that PASS with a non-standard one
byd=collections.Counter(); bysym_ref=collections.Counter()
bysym_pass=collections.Counter(); examples=[]
for d in sorted(LIB.iterdir()):
    if not d.is_dir(): continue
    tids=list(d.glob("*.tiddlers.json"))
    if not tids: continue
    try: t=json.loads(tids[0].read_text(encoding="utf-8",errors="replace"))
    except Exception: continue
    if isinstance(t,dict): t=t.get("tiddlers",t)
    if not isinstance(t,list): continue
    tot_docs+=1
    for x in t:
        if not isinstance(x,dict): continue
        ti=x.get("title","")
        if not rt.TYPED_TITLE.search(ti): continue
        lx=x.get("latex")
        if not lx: continue
        tot_rows+=1
        ok = rt.renderable(lx)
        if not ok: refused+=1
        syms=[m.group(1) for m in RIGHT.finditer(lx)]
        if not syms: continue
        r_any+=1
        ns=[s for s in syms if s not in STD]
        if not ns: continue
        r_ns+=1
        if not ok:
            ref_ns+=1; byd[d.name]+=1
            for s in ns: bysym_ref[s]+=1
            if len(examples)<12: examples.append((ti,ns,repr(lx)[:110]))
        else:
            pass_ns+=1
            for s in ns: bysym_pass[s]+=1
json.dump({"docs":tot_docs,"rows":tot_rows,"refused":refused,
           "rows_with_right":r_any,"rows_with_nonstd":r_ns,
           "refused_with_nonstd":ref_ns,"passing_with_nonstd":pass_ns,
           "by_doc":byd.most_common(15),
           "sym_refused":bysym_ref.most_common(25),
           "sym_passing":bysym_pass.most_common(25),
           "corner":sorted(CORNER),"arrows":sorted(ARROWS),
           "examples":examples},
          open(SP/"517scan2.json","w"),indent=1)
print("DONE docs=%d rows=%d refused=%d right=%d nonstd=%d refused_nonstd=%d pass_nonstd=%d"
      % (tot_docs,tot_rows,refused,r_any,r_ns,ref_ns,pass_ns))
