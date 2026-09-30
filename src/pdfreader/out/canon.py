#!/usr/bin/env python3
r"""Split the "same symbols, different string" cases into the two that matter:

  DIALECT   the reading is CORRECT and spelled differently -- {\cal L} for
            \mathcal{L}, {1\over4} for \frac{1}{4}, \left( for \bigl(,
            \varepsilon for \epsilon, X^b_a for X_a^b. A reader marks these
            right; a string comparison marks them wrong.

  ARRANGED  every symbol was read and the ARRANGEMENT is wrong -- rows run
            together, a script on the wrong base, a fraction flattened.
            This is the class 009's three-row display was in before 732:
            content perfect, structure discarded at the last step.
"""
import re, sys, importlib.util
from collections import Counter
from pathlib import Path
import os
sys.path.insert(0, os.environ.get('PDFDRILL_SRC',
                                  str(Path.home() / 'MX/PDFDRILL/src')))
_here = Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("eq", _here / "eqtable_716.py")
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
LIB=Path(os.environ.get('PDF2MMD_LIBRARY', Path.home() / 'pdfdrill-library'))

SYN={r'\varepsilon':r'\epsilon',r'\varphi':r'\phi',r'\vartheta':r'\theta',
     r'\varrho':r'\rho',r'\leqslant':r'\le',r'\geqslant':r'\ge',r'\leq':r'\le',
     r'\geq':r'\ge',r'\neq':r'\ne',r'\longrightarrow':r'\to',r'\rightarrow':r'\to',
     r'\widehat':r'\hat',r'\widetilde':r'\tilde',r'\overline':r'\bar',
     r'\cdots':r'\ldots',r'\dots':r'\ldots',r'\ast':'*',r'\prime':"'",
     # 734: `\mid` and `|` set the SAME character -- `\mid` only adds relation
     # spacing. Gold writes `|` for "given that", this reader writes `\mid`,
     # and every conditional expectation in wzlxjtu-043 differed on nothing
     # else. Dialect, which is what this table is for.
     r'\mid':'|', r'\vert':'|', r'\Vert':r'\|', r'\parallel':r'\|'}
FONT=re.compile(r'\\(mathcal|mathrm|mathbb|mathbf|mathit|mathsf|mathds|boldsymbol|bm|text|cal|bf|rm|it)\s*')
SIZE=re.compile(r'\\(left|right|bigg?|Bigg?)(l|r|m)?(?![A-Za-z])')
SPACE=re.compile(r'\\[,;:!>]|\\quad|\\qquad|\\hspace\{[^}]*\}|~|\\ ')
NOISE=re.compile(r'\\label\{[^}]*\}|\\notag|\\nonumber|\\displaystyle|\\limits|\\!'
                 # 739: `\tag{3}` is the equation NUMBER. The gold
                 # numbers implicitly, so a reader that states the
                 # number must not be marked wrong for it.
                 r'|\\tag\*?\{[^}]*\}')
ENVW=re.compile(r'\\(begin|end)\{(aligned|gathered|array|split)\}(\{[^}]*\})?')
OVER=re.compile(r'\{\s*([^{}]*?)\s*\\over\s*([^{}]*?)\s*\}')
SCR=re.compile(r'\^\{([^{}]*)\}_\{([^{}]*)\}')

def canon(x, keep_rows=True):
    x=NOISE.sub('',x); x=ENVW.sub('',x); x=SIZE.sub('',x)
    x=SPACE.sub('',x); x=FONT.sub('',x)
    for _ in range(4): x=OVER.sub(r'\\frac{\1}{\2}',x)
    for a,b in SYN.items(): x=x.replace(a,b)
    x=re.sub(r'\\frac\s*','\\\\frac',x)
    x=SCR.sub(r'_{\2}^{\1}',x)              # one spelling for a sup/sub pair
    x=re.sub(r'([_^])([A-Za-z0-9])',r'\1{\2}',x)
    x=SCR.sub(r'_{\2}^{\1}',x)
    if keep_rows:
        x=x.replace('\\\\','\x01')          # row breaks survive brace removal
    x=re.sub(r'[{}\s&]','',x)
    return x

def rows(x):
    return [r for r in canon(x).split('\x01') if r]

cls=Counter(); ex={}
for d in sorted(x for x in LIB.glob('wzlxjtu-*') if x.is_dir()):
    gt=next(iter(d.glob('golden/*_gt.tex')),None)
    if not gt: continue
    import os
    _o=os.environ.get('P2M_DIR')
    blocks=m.md_blocks((d/(d.name+'.md')) if _o=='MATHPIX' else (Path(_o)/d.name/(d.name+'.md')) if _o else d/'pdf2mmd'/'page.md')
    cg=[canon(b) for b in blocks]
    for env,g in m.gold_equations(gt):
        G=canon(g)
        if len(G)<4: continue
        if G in cg:
            cls['A CORRECT (exact, or dialect only)']+=1; continue
        # same content, different arrangement?
        gcnt=Counter(re.findall(r'\\[A-Za-z]+|\S', canon(g).replace('\x01','')))
        hit=None
        for i,b in enumerate(blocks):
            bc=Counter(re.findall(r'\\[A-Za-z]+|\S', cg[i].replace('\x01','')))
            if bc==gcnt: hit=i; break
        if hit is not None:
            same_rows = len(rows(g))==len(rows(blocks[hit]))
            k='B ARRANGED wrong, rows differ' if not same_rows else 'C ARRANGED wrong, same rows'
            cls[k]+=1
            if len(ex.setdefault(k,[]))<5: ex[k].append((d.name,g,blocks[hit]))
            continue
        cls['D symbols missing or wrong']+=1
tot=sum(cls.values())
print("   %d gold display equations\n" % tot)
for k in sorted(cls):
    print("   %-38s %4d   %5.1f%%" % (k,cls[k],100.0*cls[k]/tot))
print()
for k in sorted(ex):
    print("--- %s" % k)
    for n,g,b in ex[k][:3]:
        print("  %s" % n)
        print("    GOLD %s" % ' '.join(g.split())[:140])
        print("    P2M  %s" % ' '.join(b.split())[:140])
