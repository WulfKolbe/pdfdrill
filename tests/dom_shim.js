/* A DOM small enough to run docinspect's page script in node, and real enough
 * that "what does the reflow actually show" is a question with an answer.
 *
 * Three rounds of this feature were debugged from fragments — grepping the
 * emitted HTML, or running one extracted function against inputs I chose by
 * hand. Both agreed with me and both were wrong about what a reader sees. This
 * runs the SHIPPED script end to end and reads the resulting text out of the
 * tree, so the assertion is about the page, not about my model of it.
 *
 * Deliberately not jsdom: no dependency, and the surface docinspect uses is
 * small. Anything the script touches that is missing here throws, which is the
 * correct outcome — a silent stub would hide the next bug like the last one.
 */
class _ShimClassList {
  constructor(node){ this.node = node; this._s = new Set(); }
  add(...c){ c.forEach(x => x && this._s.add(x)); }
  remove(...c){ c.forEach(x => this._s.delete(x)); }
  toggle(c, on){ if (on === undefined) on = !this._s.has(c);
                 on ? this._s.add(c) : this._s.delete(c); return on; }
  contains(c){ return this._s.has(c); }
}

class _ShimNode {
  constructor(tag){
    this.tagName = String(tag || "div").toUpperCase();
    this.children = []; this.parentNode = null;
    this.classList = new _ShimClassList(this);
    this.style = {}; this.dataset = {}; this.attributes = {};
    this._text = ""; this._html = ""; this._listeners = {};
    this.value = ""; this.title = ""; this.src = "";
    this.isConnected = false;
    this.offsetHeight = 20;
    this.scrollTop = 0; this.offsetTop = 0;
    this._top = 0;                       // viewport y, set by tests
  }
  get className(){ return [...this.classList._s].join(" "); }
  set className(v){ this.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get textContent(){
    if (this._text) return this._text;
    return this.children.map(c => c.textContent).join("");
  }
  set textContent(v){ this._text = v == null ? "" : String(v); this.children = []; }
  get innerHTML(){ return this._html; }
  /* Parsed into real child nodes, not stored as a string: docinspect writes a
   * row with innerHTML and then immediately does `prow.querySelector('.tw')`
   * to wire its twisty. A shim that keeps markup as text has no '.tw' to find,
   * so the page dies at boot — and a shim that swallowed that would be back to
   * testing my model of the page instead of the page. */
  set innerHTML(v){
    this._html = v == null ? "" : String(v);
    this._text = "";
    this.children = _shimParse(this._html, this);
  }
  appendChild(c){
    if (c.tagName === "#FRAGMENT"){            // a fragment splices, like the real DOM
      c.children.slice().forEach(k => this.appendChild(k));
      c.children = []; return c;
    }
    c.parentNode = this; c.isConnected = this.isConnected;
    this.children.push(c); if (this.isConnected) _shimMarkConnected(c); return c; }
  removeChild(c){ this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; }
  remove(){ if (this.parentNode) this.parentNode.removeChild(this); }
  insertBefore(c, ref){ const i = this.children.indexOf(ref);
    c.parentNode = this; this.children.splice(i < 0 ? this.children.length : i, 0, c); return c; }
  setAttribute(k, v){ this.attributes[k] = String(v); }
  getAttribute(k){ return k in this.attributes ? this.attributes[k] : null; }
  addEventListener(ev, fn){ (this._listeners[ev] = this._listeners[ev] || []).push(fn); }
  dispatch(ev, arg){ (this._listeners[ev] || []).forEach(f => f(arg || {target: this,
    preventDefault(){}, stopPropagation(){}})); }
  scrollIntoView(){ this._scrolledIntoView = true; }
  /* Enough of a box model to tell "scrolled the stage" from "scrolled the
   * document": the reported bug is that the second one carried the topbar
   * off-screen, and a shim without geometry cannot see the difference. */
  getBoundingClientRect(){
    return {top: this._top, left: 0, bottom: this._top + this.offsetHeight,
            right: 0, width: 0, height: this.offsetHeight};
  }
  querySelector(sel){ return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel){
    const out = [];
    const want = (n) => {
      if (sel.startsWith(".")) return n.classList.contains(sel.slice(1));
      if (sel.startsWith("#")) return n.attributes.id === sel.slice(1);
      if (sel.startsWith("[")) { const k = sel.slice(1, -1).split("=")[0]; return k in n.attributes; }
      return n.tagName === sel.toUpperCase();
    };
    const walk = (n) => { n.children.forEach(c => { if (want(c)) out.push(c); walk(c); }); };
    walk(this);
    return out;
  }
  /* every text node under here, in document order — what a reader sees */
  allText(){
    const parts = [];
    const walk = (n) => {
      if (n._text) parts.push(n._text);
      if (n._html && n.children.length === 0) parts.push(n._html);
      n.children.forEach(walk);
    };
    walk(this);
    return parts.join("\n");
  }
}


/* Enough HTML for the fragments docinspect builds: nested tags, attributes,
 * entities, text. Unknown/self-closing tags become childless nodes. */
function _shimParse(html, parent){
  const out = [];
  const stack = [{node: null, kids: out}];
  const re = /<\/?([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>|([^<]+)/g;
  let m;
  while ((m = re.exec(html)) !== null){
    const [all, tag, attrs, text] = m;
    if (text !== undefined){
      if (text.trim()){
        const t = new _ShimNode("#text");
        t._text = _shimEntities(text);
        t.parentNode = stack[stack.length - 1].node || parent;
        stack[stack.length - 1].kids.push(t);
      }
      continue;
    }
    if (all.startsWith("</")){
      if (stack.length > 1) stack.pop();
      continue;
    }
    const n = new _ShimNode(tag);
    n.parentNode = stack[stack.length - 1].node || parent;
    const am = /class\s*=\s*"([^"]*)"/.exec(attrs || "");
    if (am) n.className = am[1];
    const idm = /\sid\s*=\s*"([^"]*)"/.exec(attrs || "");
    if (idm) n.attributes.id = idm[1];
    const sm = /\sstyle\s*=\s*"([^"]*)"/.exec(attrs || "");
    if (sm) sm[1].split(";").forEach(d => { const [k, v] = d.split(":");
      if (k && v) n.style[k.trim().replace(/-(\w)/g, (_, c) => c.toUpperCase())] = v.trim(); });
    n.isConnected = (stack[stack.length - 1].node || parent).isConnected;
    stack[stack.length - 1].kids.push(n);
    if (!all.endsWith("/>") && !/^(br|img|input|hr|meta|link)$/i.test(tag)){
      stack.push({node: n, kids: n.children});
    }
  }
  return out;
}
function _shimEntities(s){
  return s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
          .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ");
}

function _shimMarkConnected(n){ n.isConnected = true; n.children.forEach(_shimMarkConnected); }

const _SHIM_REG = {};
function _shimMkDoc(bodyHtml){
  const body = new _ShimNode("body");
  body.isConnected = true;
  _shimParse(String(bodyHtml || ""), body).forEach(n => body.appendChild(n));
  (function index(n){ if (n.attributes.id) _SHIM_REG[n.attributes.id] = n;
                      n.children.forEach(index); })(body);
  return {
    body,
    /* The registry is built once at parse time, so a node CREATED by the page
     * and given an id was invisible here while a real browser finds it —
     * `inkPanel` is built by inkRender(), and the panel tests died on null
     * before asserting anything. Fall back to a live walk, which is what the
     * DOM does. */
    getElementById(id){
      if (_SHIM_REG[id] && _SHIM_REG[id].isConnected !== false) return _SHIM_REG[id];
      let found = null;
      const walk = (n) => { if (found) return;
        if (n.attributes && n.attributes.id === id) { found = n; return; }
        n.children.forEach(walk); };
      walk(body);
      return found || _SHIM_REG[id] || null;
    },
    createElement: (t) => new _ShimNode(t),
    createDocumentFragment: () => new _ShimNode("#fragment"),
    createTextNode: (t) => { const n = new _ShimNode("#text"); n._text = String(t); return n; },
    querySelector: (s) => body.querySelector(s),
    querySelectorAll: (s) => body.querySelectorAll(s),
    addEventListener(){},
  };
}

/* The DOM is built by PARSING the document under test's own <body>
 * (globalThis.__SHIM_BODY), not synthesised from a list of ids kept here. A
 * hand-kept list lags the template — `pageTool` was added to the page and the
 * shim died on an id the real browser has — and, worse, a synthetic node loses
 * the markup's own attributes: `<div id="langTool" style="display:none">` came
 * up visible, so "is the selector hidden?" could not be asked at all. */

globalThis.document = _shimMkDoc(globalThis.__SHIM_BODY);
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.getComputedStyle = () => ({});
globalThis.innerWidth = 1400; globalThis.innerHeight = 900;
globalThis.isSecureContext = false;
globalThis.localStorage = (() => { const s = {};
  return {getItem: k => (k in s ? s[k] : null), setItem: (k, v) => { s[k] = String(v); }}; })();
globalThis.IntersectionObserver = class {
  constructor(cb){ this.cb = cb; this.seen = []; }
  observe(t){ this.seen.push(t); this.cb([{target: t, isIntersecting: true}]); }
  disconnect(){ this.seen = []; }
};
globalThis.requestAnimationFrame = (f) => f();
globalThis.Image = class { set src(v){ this._src = v; } get src(){ return this._src; } };
globalThis.katex = null;
globalThis.__noKatex = 1;

/* loaded by concatenation, not import — the repo is ESM. */
