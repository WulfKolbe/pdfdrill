#!/usr/bin/env python3
"""
tsv_gcn.py — layout-element layer for pdfdrill, in pure NumPy.

A geometric-attention GNN over Tesseract TSV word boxes that isolates structured
layout elements (postal addresses, BOM line items) the same way the MathPix layer
isolates equations as LaTeX: each found element is given a content-addressed
identity and written back as a TiddlyWiki tiddler with data fields + a projection
vector, ready to transclude (e.g. via the FO template) and to feed tw2graph /
pgvector.

Pipeline layers, MathPix-analogous:
    raw OCR  ->  TSV word boxes  ->  [this] per-word label + element grouping
             ->  cross-check vs extract_addresses heuristics + libpostal
             ->  tiddlers ($Bibkey_$type_$serial) with fields & projection

Model (edge-feature geometric attention; corrects the plain-GCN sketch):
  * Each TSV level-5 word is a node; directed edges (+ self-loops) join geometric
    neighbours. Every edge carries RELATIVE features — dx, dy, |dx|, |dy|,
    distance, same-line, is-right, is-below, is-self, h/v overlap, bias.
  * A learned vector scores edge features; a per-TARGET softmax turns scores into
    attention weights, so a token aggregates neighbours by geometric relation
    rather than by a fixed normalised adjacency. This is what separates three
    identically-formatted numbers into qty / unit-price / line-total by column.
  * Output layer emits raw logits (softmax once, outside). Weighted cross-entropy
    (inverse frequency) handles 'O' dominance.
  * `gradcheck` validates the attention+scatter backward against finite
    differences before any training is trusted.

Subcommands:
  gradcheck                          analytic vs numerical gradient self-test
  synth   OUTDIR -n N                emit N synthetic labelled pages (.tsv/.labels.json)
  label   FILE.tsv [-o J]           weak bootstrap labels (address schema) -> sidecar
  train   FILES... --labels-dir D -o model.npz
  predict FILE.tsv --model M [--json]
  crosscheck FILE.tsv [--model M]   reconcile GNN elements with extract_addresses
  tiddlers   FILE.tsv --model M --bibkey BK [--source S] [-o J]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

try:
    from extract_addresses import (DEFAULT_POSTCODE, read_tsv, find_candidates)
    _HAVE_EA = True
except Exception:
    DEFAULT_POSTCODE = r"(?<!\d)\d{5}(?!\d)\s*,?\s*[A-Za-zÄÖÜäöüß]"
    _HAVE_EA = False

try:
    from blake3 import blake3 as _blake3
    def content_hash(s: str) -> str:
        return "blake3:" + _blake3(s.encode("utf-8")).hexdigest()[:32]
except Exception:
    import hashlib
    def content_hash(s: str) -> str:
        return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]

STREET = re.compile(r"(?:stra(?:ß|ss)e|str\.?|weg|allee|platz|gasse|ring|damm)$", re.I)
RE_POSTCODE = re.compile(r"^\d{5}$")
RE_INT = re.compile(r"^\d+$")
RE_AMOUNT = re.compile(r"^\d{1,3}(?:[.\s]\d{3})*[.,]\d{2}$|^\d+[.,]\d{2}$")
RE_HOUSENO = re.compile(r"^\d+[a-z]?$", re.I)
RE_CODE = re.compile(r"^(?=.*\d)[A-Za-z0-9]+[-/.][A-Za-z0-9/.\-]+$")
CURRENCY = set("€$£") | {"EUR", "USD", "GBP"}

ALPHABET = "abcdefghijklmnopqrstuvwxyzäöüß0123456789.,-/€%"
ALPHA_IDX = {c: i for i, c in enumerate(ALPHABET)}
FLAG_NAMES = ["is_alpha", "is_upper", "is_digit_run", "is_postcode", "is_amount",
              "is_int", "has_currency", "has_pct", "is_code_like", "has_dot",
              "has_comma", "norm_len", "digit_ratio", "starts_upper"]
FEAT_DIM = 8 + len(FLAG_NAMES) + len(ALPHABET)
EDGE_DIM = 12
TYPE_CODE = {"address": "AD", "bom-line": "BM"}
ADDR_LABELS = {"ROAD", "HOUSE_NUMBER", "POSTCODE", "CITY"}
BOM_LABELS = {"ITEM_NO", "QTY", "UNIT_PRICE", "LINE_TOTAL"}


# ===========================================================================
# TSV parsing
# ===========================================================================
def parse_tsv_words(raw: str):
    nodes, page_dims = [], {}
    for row in raw.splitlines():
        if not row.strip():
            continue
        f = row.split("\t")
        if f[0] == "level":
            continue
        if len(f) < 12:
            f = f + [""] * (12 - len(f))
        try:
            level = int(f[0]); page = int(f[1]); block = int(f[2])
            par = int(f[3]); ln = int(f[4])
            left, top, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
            conf = float(f[10])
        except ValueError:
            continue
        if level == 1:
            page_dims[page] = (max(w, 1), max(h, 1)); continue
        if level != 5:
            continue
        text = f[11].strip()
        if not text:
            continue
        nodes.append(dict(id=len(nodes), text=text, page=page, block=block,
                          par=par, line=ln, x0=left, y0=top, x1=left + w,
                          y1=top + h, conf=conf))
    for p in {n["page"] for n in nodes}:
        if p not in page_dims:
            xs = [n["x1"] for n in nodes if n["page"] == p]
            ys = [n["y1"] for n in nodes if n["page"] == p]
            page_dims[p] = (max(xs) if xs else 1, max(ys) if ys else 1)
    return nodes, page_dims


def line_key(n):
    return (n["page"], n["block"], n["par"], n["line"])


# ===========================================================================
# Node features
# ===========================================================================
def _char_bag(text):
    v = np.zeros(len(ALPHABET)); t = text.lower()
    for c in t:
        j = ALPHA_IDX.get(c)
        if j is not None:
            v[j] += 1.0
    return v / (len(t) or 1)


def _flags(text):
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    n = len(text) or 1
    return np.array([
        float(text.isalpha()),
        float(text.isupper() and letters > 0),
        float(RE_INT.match(text) is not None),
        float(RE_POSTCODE.match(text) is not None),
        float(RE_AMOUNT.match(text) is not None),
        float(RE_INT.match(text) is not None),
        float(any(c in CURRENCY for c in text) or text in CURRENCY),
        float("%" in text),
        float(RE_CODE.match(text) is not None),
        float("." in text), float("," in text),
        min(n, 20) / 20.0, digits / n, float(text[:1].isupper())])


def build_features(nodes, page_dims):
    rows = []
    for nd in nodes:
        W, H = page_dims[nd["page"]]
        x0, y0, x1, y1 = nd["x0"] / W, nd["y0"] / H, nd["x1"] / W, nd["y1"] / H
        geom = np.array([x0, y0, x1, y1, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0])
        rows.append(np.concatenate([geom, _flags(nd["text"]), _char_bag(nd["text"])]))
    return np.asarray(rows, dtype=np.float64) if rows else np.zeros((0, FEAT_DIM))


# ===========================================================================
# Graph: neighbour pairs + directed edges with relative geometric features
# ===========================================================================
def neighbour_pairs(nodes):
    pairs = set()
    lines = {}
    for nd in nodes:
        lines.setdefault(line_key(nd), []).append(nd["id"])
    widths = []
    for ids in lines.values():
        ids.sort(key=lambda i: nodes[i]["x0"])
        for a, b in zip(ids, ids[1:]):
            pairs.add((a, b))
        widths += [nodes[i]["x1"] - nodes[i]["x0"] for i in ids]
    avg_w = float(np.median(widths)) if widths else 1.0
    by_block = {}
    for key, ids in lines.items():
        by_block.setdefault(key[:2], []).append((key[3], ids))
    for group in by_block.values():
        group.sort(key=lambda t: t[0])
        for (_, up), (_, lo) in zip(group, group[1:]):
            for i in up:
                ci = (nodes[i]["x0"] + nodes[i]["x1"]) / 2
                for j in lo:
                    cj = (nodes[j]["x0"] + nodes[j]["x1"]) / 2
                    if abs(ci - cj) <= 1.5 * avg_w:
                        pairs.add((min(i, j), max(i, j)))
    return pairs


def build_edges(nodes, page_dims):
    """Return (tgt, dst, E): for each directed edge target<-src, E row holds
    features of src RELATIVE to target. Includes self-loops."""
    N = len(nodes)
    if N == 0:
        return np.zeros(0, int), np.zeros(0, int), np.zeros((0, EDGE_DIM))
    Wd = np.array([page_dims[nd["page"]][0] for nd in nodes], float)
    Hd = np.array([page_dims[nd["page"]][1] for nd in nodes], float)
    x0 = np.array([nd["x0"] for nd in nodes]) / Wd
    x1 = np.array([nd["x1"] for nd in nodes]) / Wd
    y0 = np.array([nd["y0"] for nd in nodes]) / Hd
    y1 = np.array([nd["y1"] for nd in nodes]) / Hd
    xc, yc, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    lid = {}
    line_id = np.array([lid.setdefault(line_key(nd), len(lid)) for nd in nodes])

    tgt, dst = list(range(N)), list(range(N))            # self-loops
    for (i, j) in neighbour_pairs(nodes):
        tgt += [i, j]; dst += [j, i]
    tgt = np.array(tgt); dst = np.array(dst)

    dx = xc[dst] - xc[tgt]; dy = yc[dst] - yc[tgt]
    ox = np.maximum(0, np.minimum(x1[tgt], x1[dst]) - np.maximum(x0[tgt], x0[dst]))
    oy = np.maximum(0, np.minimum(y1[tgt], y1[dst]) - np.maximum(y0[tgt], y0[dst]))
    hov = ox / (np.minimum(w[tgt], w[dst]) + 1e-9)
    vov = oy / (np.minimum(h[tgt], h[dst]) + 1e-9)
    E = np.stack([dx, dy, np.abs(dx), np.abs(dy), np.sqrt(dx * dx + dy * dy),
                  (line_id[tgt] == line_id[dst]).astype(float),
                  (dx > 0).astype(float), (dy > 0).astype(float),
                  (tgt == dst).astype(float),
                  np.clip(hov, 0, 1), np.clip(vov, 0, 1),
                  np.ones_like(dx)], axis=1)
    return tgt, dst, E


# ===========================================================================
# Geometric-attention layer
# ===========================================================================
def _glorot(fi, fo, rng):
    lim = np.sqrt(6.0 / (fi + fo))
    return rng.uniform(-lim, lim, (fi, fo))


class EdgeAttn:
    def __init__(self, d_in, d_out, d_edge, activation="relu", seed=0):
        rng = np.random.default_rng(seed)
        self.W = _glorot(d_in, d_out, rng)
        self.b = np.zeros(d_out)
        self.a = np.zeros(d_edge)                 # edge-feature attention scorer
        self.act = activation

    def params(self):
        return {"W": self.W, "b": self.b, "a": self.a}

    def set_params(self, W, b, a):
        self.W, self.b, self.a = W, b, a

    def forward(self, H, edges):
        tgt, dst, E = edges
        N = H.shape[0]
        Hw = H @ self.W
        msg = Hw[dst]
        s = E @ self.a
        seg_max = np.full(N, -np.inf)
        np.maximum.at(seg_max, tgt, s)
        u = np.exp(s - seg_max[tgt])
        Z = np.bincount(tgt, weights=u, minlength=N)
        alpha = u / Z[tgt]
        out = np.zeros((N, self.W.shape[1]))
        np.add.at(out, tgt, alpha[:, None] * msg)
        pre = out + self.b
        Y = np.maximum(0.0, pre) if self.act == "relu" else pre
        self._c = (H, Hw, msg, alpha, tgt, dst, E, pre, N)
        return Y

    def backward(self, dY):
        H, Hw, msg, alpha, tgt, dst, E, pre, N = self._c
        dpre = dY * (pre > 0) if self.act == "relu" else dY
        db = dpre.sum(0)
        dout_t = dpre[tgt]                                  # (M,dout)
        d_alpha = (dout_t * msg).sum(1)                     # (M,)
        d_msg = alpha[:, None] * dout_t                     # (M,dout)
        dHw = np.zeros_like(Hw)
        np.add.at(dHw, dst, d_msg)
        dW = H.T @ dHw
        dH = dHw @ self.W.T
        weighted = alpha * d_alpha                          # softmax backward
        sps = np.bincount(tgt, weights=weighted, minlength=N)
        ds = alpha * (d_alpha - sps[tgt])
        da = E.T @ ds
        self.grads = {"W": dW, "b": db, "a": da}
        return dH


class EdgeGNN:
    def __init__(self, d_in, d_h, d_out, d_edge=EDGE_DIM, seed=0):
        self.l1 = EdgeAttn(d_in, d_h, d_edge, "relu", seed)
        self.l2 = EdgeAttn(d_h, d_out, d_edge, None, seed + 1)
        self.d_h = d_h

    def forward(self, X, edges):
        self.H1 = self.l1.forward(X, edges)
        return self.l2.forward(self.H1, edges)

    def embed(self, X, edges):
        self.forward(X, edges)
        return self.H1

    def grads(self):
        return {"W1": self.l1.grads["W"], "b1": self.l1.grads["b"], "a1": self.l1.grads["a"],
                "W2": self.l2.grads["W"], "b2": self.l2.grads["b"], "a2": self.l2.grads["a"]}

    def params(self):
        return {"W1": self.l1.W, "b1": self.l1.b, "a1": self.l1.a,
                "W2": self.l2.W, "b2": self.l2.b, "a2": self.l2.a}

    def backward_chain(self, dZ2):
        dH1 = self.l2.backward(dZ2)
        self.l1.backward(dH1)


def softmax(Z):
    Z = Z - Z.max(1, keepdims=True); e = np.exp(Z)
    return e / e.sum(1, keepdims=True)


def loss_and_dZ(Z2, y, mask, class_w):
    P = softmax(Z2)
    idx = np.where(mask)[0]; yi = y[idx]; w = class_w[yi]
    S = w.sum() + 1e-12
    loss = float((w * -np.log(P[idx, yi] + 1e-12)).sum() / S)
    dZ = np.zeros_like(Z2)
    G = P[idx].copy(); G[np.arange(len(idx)), yi] -= 1.0
    dZ[idx] = (w[:, None] * G) / S
    return loss, dZ, P


# ===========================================================================
# Gradient check (attention + scatter backward)
# ===========================================================================
def gradcheck(seed=0):
    rng = np.random.default_rng(seed)
    N, d_in, d_h, C = 10, 7, 6, 4
    X = rng.standard_normal((N, d_in))
    pairs = set()
    for _ in range(14):
        i, j = rng.integers(0, N, 2)
        if i != j:
            pairs.add((min(i, j), max(i, j)))
    tgt, dst = list(range(N)), list(range(N))
    for (i, j) in pairs:
        tgt += [i, j]; dst += [j, i]
    tgt, dst = np.array(tgt), np.array(dst)
    E = rng.standard_normal((len(tgt), EDGE_DIM))
    edges = (tgt, dst, E)
    y = rng.integers(0, C, N); mask = rng.random(N) < 0.8
    cw = rng.uniform(0.5, 2.0, C)
    m = EdgeGNN(d_in, d_h, C, EDGE_DIM, seed=3)
    # randomise 'a' so attention isn't uniform
    m.l1.a = rng.standard_normal(EDGE_DIM); m.l2.a = rng.standard_normal(EDGE_DIM)

    def loss_only():
        return loss_and_dZ(m.forward(X, edges), y, mask, cw)[0]

    Z2 = m.forward(X, edges)
    _, dZ2, _ = loss_and_dZ(Z2, y, mask, cw)
    m.backward_chain(dZ2)
    grads = m.grads()
    pmap = {"W1": m.l1.W, "b1": m.l1.b, "a1": m.l1.a,
            "W2": m.l2.W, "b2": m.l2.b, "a2": m.l2.a}
    eps, worst = 1e-6, 0.0
    for name, P in pmap.items():
        flat = P.ravel(); gf = grads[name].ravel()
        for k in rng.choice(flat.size, min(flat.size, 15), replace=False):
            o = flat[k]
            flat[k] = o + eps; lp = loss_only()
            flat[k] = o - eps; lm = loss_only()
            flat[k] = o
            num = (lp - lm) / (2 * eps)
            worst = max(worst, abs(num - gf[k]) / max(1.0, abs(num) + abs(gf[k])))
    return worst


# ===========================================================================
# Dataset / training
# ===========================================================================
def graph_of(nodes, page_dims):
    return build_features(nodes, page_dims), build_edges(nodes, page_dims)


def make_schema(label_sets):
    labels = set()
    for s in label_sets:
        labels |= set(s)
    labels.discard("O")
    return ["O"] + sorted(labels)


def load_dataset(tsv_paths, labels_dir):
    raw = []
    for p in tsv_paths:
        nodes, dims = parse_tsv_words(Path(p).read_text(encoding="utf-8"))
        lab = json.loads((Path(labels_dir) / (Path(p).stem + ".labels.json")
                          ).read_text(encoding="utf-8"))["labels"]
        raw.append((p, nodes, dims, lab))
    schema = make_schema(set(l.values()) for _, _, _, l in raw)
    cls = {c: i for i, c in enumerate(schema)}
    out = []
    for p, nodes, dims, lab in raw:
        X, edges = graph_of(nodes, dims)
        y = np.zeros(len(nodes), int); mask = np.zeros(len(nodes), bool)
        for nd in nodes:
            k = str(nd["id"])
            if k in lab:
                y[nd["id"]] = cls[lab[k]]; mask[nd["id"]] = True
        out.append((p, X, edges, y, mask))
    return out, schema


def class_weights(dataset, C):
    counts = np.zeros(C)
    for _, _, _, y, mask in dataset:
        for c in y[mask]:
            counts[c] += 1
    counts = np.maximum(counts, 1.0)
    return np.clip(counts.sum() / (C * counts), 0.2, 5.0)


class Adam:
    def __init__(self, params, lr=0.01, b1=0.9, b2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def step(self, params, grads):
        self.t += 1
        for k in params:
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * grads[k]
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * grads[k] ** 2
            mh = self.m[k] / (1 - self.b1 ** self.t)
            vh = self.v[k] / (1 - self.b2 ** self.t)
            params[k] -= self.lr * mh / (np.sqrt(vh) + self.eps)


def train(dataset, schema, epochs=300, d_h=48, lr=0.01, seed=0, verbose=True):
    C = len(schema)
    model = EdgeGNN(FEAT_DIM, d_h, C, EDGE_DIM, seed=seed)
    params = model.params()
    opt = Adam(params, lr=lr)
    cw = class_weights(dataset, C)
    for ep in range(1, epochs + 1):
        tot = {k: np.zeros_like(v) for k, v in params.items()}
        nloss = 0.0
        for _, X, edges, y, mask in dataset:
            Z2 = model.forward(X, edges)
            loss, dZ2, _ = loss_and_dZ(Z2, y, mask, cw)
            model.backward_chain(dZ2)
            g = model.grads()
            for k in tot:
                tot[k] += g[k]
            nloss += loss
        for k in tot:
            tot[k] /= len(dataset)
        opt.step(params, tot)
        if verbose and (ep % max(1, epochs // 10) == 0 or ep == 1):
            print(f"  epoch {ep:4d}  loss {nloss/len(dataset):.4f}  "
                  f"train_acc {evaluate(model, dataset)['acc']:.3f}")
    return model, cw


def evaluate(model, dataset):
    correct = total = 0; per = {}
    for _, X, edges, y, mask in dataset:
        pred = model.forward(X, edges).argmax(1)
        for i in np.where(mask)[0]:
            total += 1; ok = int(pred[i] == y[i]); correct += ok
            d = per.setdefault(int(y[i]), [0, 0]); d[0] += ok; d[1] += 1
    return {"acc": correct / max(total, 1), "per_class": per}


# ===========================================================================
# Element extraction from predictions (+ embeddings for projections)
# ===========================================================================
def _bbox_union(nodes, ids):
    return [min(nodes[i]["x0"] for i in ids), min(nodes[i]["y0"] for i in ids),
            max(nodes[i]["x1"] for i in ids), max(nodes[i]["y1"] for i in ids)]


def extract_elements(nodes, schema, pred, probs=None, embed=None):
    """Group predicted words into address / bom-line elements with provenance.
    Addresses are clustered by vertical line adjacency (a real address is a few
    consecutive lines) rather than by the unstable Tesseract block number."""
    elems = []
    # ---- addresses: cluster ADDR-labelled words across adjacent lines ----
    addr_ids = [nd["id"] for nd in nodes if schema[pred[nd["id"]]] in ADDR_LABELS]
    if addr_ids:
        medh = float(np.median([nodes[i]["y1"] - nodes[i]["y0"] for i in addr_ids]))
        per_line = {}
        for i in addr_ids:
            per_line.setdefault(line_key(nodes[i]), []).append(i)
        ordered = sorted(per_line.items(),
                         key=lambda kv: (kv[0][0], min(nodes[i]["y0"] for i in kv[1])))
        clusters, cur, prev_bot, prev_pg = [], [], None, None
        for key, ids in ordered:
            top = min(nodes[i]["y0"] for i in ids)
            bot = max(nodes[i]["y1"] for i in ids)
            if cur and (key[0] != prev_pg or top - prev_bot > 2.0 * medh):
                clusters.append(cur); cur = []
            cur += ids; prev_bot, prev_pg = bot, key[0]
        if cur:
            clusters.append(cur)
        for ids in clusters:
            comp = {}
            for i in sorted(ids, key=lambda i: (nodes[i]["y0"], nodes[i]["x0"])):
                comp.setdefault(schema[pred[i]].lower(), []).append(nodes[i]["text"])
            if "postcode" in comp:
                conf = (float(np.mean([probs[i, pred[i]] for i in ids]))
                        if probs is not None else None)
                elems.append({"kind": "address", "page": nodes[ids[0]]["page"],
                              "components": {k: " ".join(v) for k, v in comp.items()},
                              "word_ids": ids, "bbox": _bbox_union(nodes, ids),
                              "conf": conf})
    # ---- bom-lines: per line ----
    lines = {}
    for nd in nodes:
        lines.setdefault(line_key(nd), []).append(nd["id"])
    for key, ids in lines.items():
        comp = {}; used = []
        for i in sorted(ids, key=lambda i: nodes[i]["x0"]):
            lbl = schema[pred[i]]
            if lbl in BOM_LABELS:
                comp[lbl.lower()] = nodes[i]["text"]; used.append(i)
        if used and ("line_total" in comp or "qty" in comp):
            conf = (float(np.mean([probs[i, pred[i]] for i in used]))
                    if probs is not None else None)
            elems.append({"kind": "bom-line", "page": key[0], "components": comp,
                          "word_ids": used, "bbox": _bbox_union(nodes, used),
                          "conf": conf})
    if embed is not None:
        for e in elems:
            e["embedding"] = embed[e["word_ids"]].mean(0)
    return elems


# ===========================================================================
# Cross-check vs extract_addresses
# ===========================================================================
def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def crosscheck(tsv_path, model_path=None, iou_thr=0.3):
    raw = Path(tsv_path).read_text(encoding="utf-8")
    nodes, dims = parse_tsv_words(raw)

    gnn_addr = []
    if model_path:
        model, schema = load_model(model_path)
        X, edges = graph_of(nodes, dims)
        logits = model.forward(X, edges)
        pred = logits.argmax(1); probs = softmax(logits)
        emb = model.H1
        gnn_addr = [e for e in extract_elements(nodes, schema, pred, probs, emb)
                    if e["kind"] == "address"]

    heur = []
    if _HAVE_EA:
        segs = read_tsv(raw)
        for c in find_candidates(segs, re.compile(DEFAULT_POSTCODE), 3, 50):
            if c.bbox:
                heur.append({"text": c.text, "bbox": list(c.bbox), "conf": c.conf})

    reconciled = []
    used_h = set()
    for g in gnn_addr:
        best, bi = 0.0, None
        for k, h in enumerate(heur):
            j = _iou(g["bbox"], h["bbox"])
            pc = g["components"].get("postcode", "")
            if pc and pc in h["text"]:
                j = max(j, 1.0)
            if j > best:
                best, bi = j, k
        if bi is not None and best >= iou_thr:
            used_h.add(bi)
            reconciled.append({**g, "source": "gnn+heuristic",
                               "agreement": round(best, 3),
                               "heuristic_text": heur[bi]["text"]})
        else:
            reconciled.append({**g, "source": "gnn-only", "agreement": 0.0})
    for k, h in enumerate(heur):
        if k not in used_h:
            reconciled.append({"kind": "address", "source": "heuristic-only",
                               "agreement": 0.0, "bbox": h["bbox"],
                               "text": h["text"], "components": {}, "word_ids": []})
    return reconciled, nodes


# ===========================================================================
# pdfdrill / TiddlyWiki tiddler emission
# ===========================================================================
def _slug_field(k):
    return k.replace("_", "-")


def element_to_tiddler(e, bibkey, serial, source_name):
    kind = e["kind"]
    code = TYPE_CODE.get(kind, "LO")
    comp = e.get("components", {})
    if kind == "address":
        text = (f"{comp.get('road','')} {comp.get('house_number','')}".strip()
                + "\n" + f"{comp.get('postcode','')} {comp.get('city','')}".strip()).strip()
        if not text:
            text = e.get("text", "")
    else:
        text = "  ".join(f"{k}={v}" for k, v in comp.items())
    h = content_hash(f"{kind}|{source_name}|" + "|".join(f"{k}={comp[k]}" for k in sorted(comp)))
    bbox = e.get("bbox")
    tid = {
        "title": f"{bibkey}_{code}_{serial:04d}",
        "tags": f"pdfdrill layoutElement {kind} {bibkey}",
        "kind": kind,
        "page": str(e.get("page", "")),
        "bbox": " ".join(map(str, bbox)) if bbox else "",
        "source": e.get("source", "gnn"),
        "agreement": str(e.get("agreement", "")),
        "conf": "" if e.get("conf") is None else f"{e['conf']:.3f}",
        "hash": h,
        "drill-source": source_name,
        "text": text,
    }
    for k, v in comp.items():
        tid[_slug_field(k)] = v
    # geometric projection (normalised bbox centre + size) — always available
    if bbox and e.get("page") is not None:
        tid["geo-projection"] = " ".join(
            f"{x:.4f}" for x in [(bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2,
                                 bbox[2]-bbox[0], bbox[3]-bbox[1]])
    # learned projection (pooled GNN embedding) for tw2graph / pgvector
    if "embedding" in e:
        tid["projection"] = " ".join(f"{x:.5f}" for x in e["embedding"])
        tid["projection-dim"] = str(len(e["embedding"]))
    return tid


def emit_tiddlers(tsv_path, model_path, bibkey, source_name=None):
    model, schema = load_model(model_path)
    nodes, dims = parse_tsv_words(Path(tsv_path).read_text(encoding="utf-8"))
    X, edges = graph_of(nodes, dims)
    logits = model.forward(X, edges)
    pred = logits.argmax(1); probs = softmax(logits); emb = model.H1
    bom = [e for e in extract_elements(nodes, schema, pred, probs, emb)
           if e["kind"] == "bom-line"]
    # addresses come from the cross-check so each tiddler records its provenance
    addrs, _ = crosscheck(tsv_path, model_path)
    elems = addrs + bom
    source_name = source_name or Path(tsv_path).name
    serials, tiddlers = {}, []
    for e in elems:
        code = TYPE_CODE.get(e["kind"], "LO")
        serials[code] = serials.get(code, 0) + 1
        tiddlers.append(element_to_tiddler(e, bibkey, serials[code], source_name))
    return tiddlers


# ===========================================================================
# Weak labeller (address schema)
# ===========================================================================
ADDR_SCHEMA = ["O", "ROAD", "HOUSE_NUMBER", "POSTCODE", "CITY"]


def weak_labels(nodes):
    lab = {str(n["id"]): "O" for n in nodes}
    lines = {}
    for nd in nodes:
        lines.setdefault(line_key(nd), []).append(nd["id"])
    for ids in lines.values():
        ids.sort(key=lambda i: nodes[i]["x0"])
    ll = sorted(lines.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][3]))
    for pos, (key, ids) in enumerate(ll):
        texts = [nodes[i]["text"] for i in ids]
        pc = next((k for k, t in enumerate(texts) if RE_POSTCODE.match(t)), None)
        if pc is None:
            continue
        if pc + 1 < len(ids) and nodes[ids[pc + 1]]["text"][:1].isupper():
            lab[str(ids[pc])] = "POSTCODE"
            for j in range(pc + 1, len(ids)):
                if nodes[ids[j]]["text"][:1].isalpha():
                    lab[str(ids[j])] = "CITY"
        for up in (pos - 1, pos - 2):
            if up < 0 or ll[up][0][:2] != key[:2]:
                continue
            uids = ll[up][1]
            si = next((k for k, i in enumerate(uids) if STREET.search(nodes[i]["text"])), None)
            if si is None:
                continue
            for k in range(si + 1):
                lab[str(uids[k])] = "ROAD"
            if si + 1 < len(uids) and RE_HOUSENO.match(nodes[uids[si + 1]]["text"]):
                lab[str(uids[si + 1])] = "HOUSE_NUMBER"
            break
    return lab


# ===========================================================================
# Synthetic data generator
# ===========================================================================
STREETS = ["Rotkäppchenweg", "Kürtener Straße", "Hauptstraße", "Lindenallee",
           "Bahnhofstraße", "Am Markt", "Hans-Böckler-Str.", "Gartenweg"]
CITIES = ["Kürten", "Bergisch Gladbach", "Köln", "Düsseldorf", "Wermelskirchen"]
NAMES = ["Familie Kolbe", "Herr Schmitz", "Firma Müller GmbH", "Frau Becker"]
DESCS = ["Brennerdichtung", "Kundendienst Monteur", "Anfahrtspauschale",
         "Ersatzteil Pumpe", "Wartung Heizung"]


def _row(l, p, bl, pa, ln, wd, x, y, w, h, c, t):
    return f"{l}\t{p}\t{bl}\t{pa}\t{ln}\t{wd}\t{x}\t{y}\t{w}\t{h}\t{c}\t{t}"


def synth_page(rng):
    W, H = 2480, 3508
    rows = [_row(1, 1, 0, 0, 0, 0, 0, 0, W, H, -1, "")]
    labels = {}; wid = 0; block = 1

    def emit(tokens, x0, y, step, line):
        nonlocal wid
        x = x0
        for t, role in tokens:
            w = max(30, len(t) * 22 + int(rng.integers(-6, 6)))
            rows.append(_row(5, 1, block, 1, line, 1, int(x), int(y), int(w), 40, 92, t))
            if role:
                labels[str(wid)] = role
            wid += 1; x += w + step

    by = 600 + int(rng.integers(-40, 40))
    emit([(w, None) for w in rng.choice(NAMES).split()], 300, by, 14, 1)
    st = rng.choice(STREETS); hno = f"{rng.integers(1,99)}{rng.choice(['','a','f'])}"
    emit([(w, "ROAD") for w in st.split()] + [(hno, "HOUSE_NUMBER")], 300, by+70, 14, 2)
    plz = f"{rng.integers(10000,99999)}"; city = rng.choice(CITIES).split()
    emit([(plz, "POSTCODE")] + [(c, "CITY") for c in city], 300, by+140, 14, 3)

    block = 2                                       # table is its own block
    hy = 1400 + int(rng.integers(-30, 30))
    for col, x in [("Pos", 300), ("Menge", 540), ("Bezeichnung", 800),
                   ("Einzelpreis", 1900), ("Gesamtpreis", 2250)]:
        emit([(col, None)], x, hy, 0, 10)
    for r in range(int(rng.integers(2, 5))):
        ry = hy + 90 * (r + 1)
        emit([(str(r+1), "ITEM_NO")], 300, ry, 0, 20+r)
        emit([(f"{rng.integers(1,30)},{rng.integers(0,99):02d}", "QTY")], 540, ry, 0, 20+r)
        emit([(w, None) for w in rng.choice(DESCS).split()], 800, ry, 14, 20+r)
        emit([(f"{rng.integers(1,99)},{rng.integers(0,99):02d}", "UNIT_PRICE")], 1900, ry, 0, 20+r)
        emit([(f"{rng.integers(10,990)},{rng.integers(0,99):02d}", "LINE_TOTAL")], 2250, ry, 0, 20+r)
    return "\n".join(rows) + "\n", labels


# ===========================================================================
# Model save / load
# ===========================================================================
def save_model(path, model, schema, cw, d_h):
    np.savez(path, W1=model.l1.W, b1=model.l1.b, a1=model.l1.a,
             W2=model.l2.W, b2=model.l2.b, a2=model.l2.a,
             schema=np.array(schema), class_w=cw,
             meta=np.array([str(FEAT_DIM), str(d_h), str(EDGE_DIM), ALPHABET]))


def load_model(path):
    z = np.load(path, allow_pickle=True)
    schema = [str(s) for s in z["schema"]]
    d_h = z["W1"].shape[1]
    m = EdgeGNN(z["W1"].shape[0], d_h, z["W2"].shape[1], z["a1"].shape[0])
    m.l1.set_params(z["W1"], z["b1"], z["a1"])
    m.l2.set_params(z["W2"], z["b2"], z["a2"])
    return m, schema


# ===========================================================================
# CLI
# ===========================================================================
def cmd_gradcheck(args):
    w = gradcheck()
    print(f"max relative gradient error: {w:.2e}")
    print("PASS" if w < 1e-5 else "FAIL")
    return 0 if w < 1e-5 else 1


def cmd_synth(args):
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    for k in range(args.n):
        tsv, labels = synth_page(rng); stem = f"page{k:03d}"
        (out / f"{stem}.tsv").write_text(tsv, encoding="utf-8")
        (out / f"{stem}.labels.json").write_text(
            json.dumps({"source": f"{stem}.tsv", "labels": labels}, ensure_ascii=False),
            encoding="utf-8")
    print(f"wrote {args.n} synthetic pages to {out}")


def cmd_label(args):
    nodes, _ = parse_tsv_words(Path(args.file).read_text(encoding="utf-8"))
    payload = {"source": Path(args.file).name, "schema": ADDR_SCHEMA,
               "labels": weak_labels(nodes),
               "nodes": [{"id": n["id"], "text": n["text"],
                          "bbox": [n["x0"], n["y0"], n["x1"], n["y1"]],
                          "line": list(line_key(n))} for n in nodes]}
    txt = json.dumps(payload, ensure_ascii=False, indent=2)
    (Path(args.out).write_text(txt, encoding="utf-8"), print(f"wrote {args.out}")) \
        if args.out else print(txt)


def cmd_train(args):
    dataset, schema = load_dataset(args.files, args.labels_dir)
    print(f"schema ({len(schema)}): {schema}\npages: {len(dataset)}")
    model, cw = train(dataset, schema, epochs=args.epochs, d_h=args.hidden,
                      lr=args.lr, seed=args.seed)
    ev = evaluate(model, dataset)
    print(f"final train acc {ev['acc']:.3f}")
    for ci in sorted(ev["per_class"]):
        ok, tot = ev["per_class"][ci]
        print(f"    {schema[ci]:<13} {ok}/{tot}")
    save_model(args.out, model, schema, cw, args.hidden)
    print(f"saved {args.out}")


def cmd_predict(args):
    model, schema = load_model(args.model)
    nodes, dims = parse_tsv_words(Path(args.file).read_text(encoding="utf-8"))
    X, edges = graph_of(nodes, dims)
    logits = model.forward(X, edges)
    pred = logits.argmax(1); probs = softmax(logits)
    elems = extract_elements(nodes, schema, pred, probs, model.H1)
    if args.json:
        for e in elems:
            e.pop("embedding", None)
        print(json.dumps({"source": Path(args.file).name, "elements": elems},
                         ensure_ascii=False, indent=2))
    else:
        for nd in nodes:
            lbl = schema[pred[nd["id"]]]
            if lbl != "O":
                print(f"  {lbl:<13} {nd['text']}")


def cmd_crosscheck(args):
    rec, _ = crosscheck(args.file, args.model)
    for r in rec:
        r.pop("embedding", None); r.pop("word_ids", None)
    print(json.dumps({"source": Path(args.file).name, "addresses": rec},
                     ensure_ascii=False, indent=2))


def cmd_tiddlers(args):
    tiddlers = emit_tiddlers(args.file, args.model, args.bibkey, args.source)
    txt = json.dumps(tiddlers, ensure_ascii=False, indent=2)
    (Path(args.out).write_text(txt, encoding="utf-8"), print(f"wrote {args.out}")) \
        if args.out else print(txt)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gradcheck").set_defaults(fn=cmd_gradcheck)
    s = sub.add_parser("synth"); s.add_argument("outdir"); s.add_argument("-n", type=int, default=20)
    s.add_argument("--seed", type=int, default=0); s.set_defaults(fn=cmd_synth)
    s = sub.add_parser("label"); s.add_argument("file"); s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_label)
    s = sub.add_parser("train"); s.add_argument("files", nargs="+")
    s.add_argument("--labels-dir", required=True); s.add_argument("-o", "--out", required=True)
    s.add_argument("--epochs", type=int, default=300); s.add_argument("--hidden", type=int, default=48)
    s.add_argument("--lr", type=float, default=0.01); s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_train)
    s = sub.add_parser("predict"); s.add_argument("file"); s.add_argument("--model", required=True)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_predict)
    s = sub.add_parser("crosscheck"); s.add_argument("file"); s.add_argument("--model")
    s.set_defaults(fn=cmd_crosscheck)
    s = sub.add_parser("tiddlers"); s.add_argument("file"); s.add_argument("--model", required=True)
    s.add_argument("--bibkey", required=True); s.add_argument("--source")
    s.add_argument("-o", "--out"); s.set_defaults(fn=cmd_tiddlers)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
