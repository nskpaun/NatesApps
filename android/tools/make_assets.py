#!/usr/bin/env python3
"""Convert the web guide content + PDFs into JSON assets for the Android app."""
import json, re, subprocess, sys, pathlib, shutil
from html.parser import HTMLParser
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "chain-theory" / "src"))
import build as web  # reuse text extraction
TPL = (ROOT / "chain-theory" / "src" / "template.html").read_text(encoding="utf-8")
ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

SKIP_CLASSES = {"toc-mini", "next", "levels", "btnrow"}
VOID = {"br", "img", "input", "hr", "meta", "link"}

class Conv(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []; self.stack = []  # container stack: list of (blocks list)
        self.cur = None  # current inline: dict(kind, spans)
        self.style = []; self.link = []
        self.skip = 0; self.svg = 0
        self.table = None; self.row = None; self.cell = None
        self.ol = []; self.dt = None
    def out(self):
        return self.stack[-1]["blocks"] if self.stack else self.blocks
    def start_inline(self, kind, **kw):
        self.cur = {"k": kind, "s": [], **kw}
    def end_inline(self):
        c = self.cur; self.cur = None
        if not c: return
        # trim
        sp = [s for s in c["s"] if s[0]]
        if sp:
            sp[0][0] = sp[0][0].lstrip(); sp[-1][0] = sp[-1][0].rstrip()
        c["s"] = [s for s in sp if s[0]]
        if not c["s"]: return
        if self.cell is not None:
            self.cell.extend(c["s"]); return
        self.out().append(c)
    def handle_starttag(self, tag, a):
        a = dict(a); cls = set((a.get("class") or "").split())
        if self.skip:
            if tag not in VOID: self.skip += 1
            return
        if tag == "svg":
            self.skip = 1; return
        if cls & SKIP_CLASSES or "hide" in cls and tag != "section":
            if tag not in VOID: self.skip = 1
            return
        if tag in ("h1", "h2", "h3"):
            self.start_inline(tag, id=a.get("id"))
        elif tag == "p":
            if self.cur is None: self.start_inline("p")
        elif tag == "div" and "kicker" in cls:
            self.start_inline("kicker")
        elif tag == "div" and "axiom" in cls:
            self.start_inline("axiom")
        elif tag == "div" and "number" in cls:
            self.start_inline("number")
        elif tag == "small" and self.cur and self.cur["k"] == "number":
            self.end_inline(); self.start_inline("numsmall")
        elif tag == "div" and "callout" in cls:
            kind = "warn" if "warn" in cls else "good" if "good" in cls else "note"
            self.stack.append({"k": "callout", "kind": kind, "blocks": []})
            self.start_inline("p")
        elif tag == "div" and "card" in cls:
            self.stack.append({"k": "card", "blocks": []})
        elif tag in ("ul", "ol"):
            self.ol.append(0 if tag == "ol" else -1)
        elif tag == "li":
            n = None
            if self.ol and self.ol[-1] >= 0:
                self.ol[-1] += 1; n = self.ol[-1]
            self.start_inline("li", n=n)
        elif tag == "table":
            self.table = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []; self.row.append({"h": tag == "th", "s": self.cell})
        elif tag == "dt":
            self.start_inline("dt")
        elif tag == "dd":
            self.start_inline("dd")
        elif tag in ("strong", "b"):
            self.style.append("b")
        elif tag == "em":
            self.style.append("i")
        elif tag in ("code",) or "mono" in cls:
            self.style.append("c")
        elif tag == "span" and "pill" in cls:
            self.style.append("b")
        elif tag == "span":
            self.style.append("")
        elif tag == "sub" or tag == "sup":
            self.style.append("")
        elif tag == "a":
            self.link.append(a.get("href", ""))
        elif tag == "br":
            self.text("\n")
    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1; return
        if tag in ("h1", "h2", "h3", "li", "dt", "dd"):
            self.end_inline()
        elif tag == "p":
            if self.cur and self.cur["k"] == "p": self.end_inline()
        elif tag == "div":
            if self.cur and self.cur["k"] in ("kicker", "axiom", "number", "numsmall"):
                self.end_inline()
            elif self.stack and self.cur is not None and self.cur["k"] == "p" and self.stack[-1]["k"] == "callout":
                self.end_inline(); c = self.stack.pop(); self.out().append(c)
            elif self.stack:
                self.end_inline()
                c = self.stack.pop()
                if c["blocks"]: self.out().append(c)
        elif tag in ("ul", "ol"):
            self.ol.pop()
        elif tag in ("strong", "b", "em", "code", "span", "sub", "sup"):
            if self.style: self.style.pop()
        elif tag == "a":
            if self.link: self.link.pop()
        elif tag in ("td", "th"):
            for s in self.cell: pass
            self.cell = None
        elif tag == "tr":
            if self.row: self.table.append(self.row)
            self.row = None
        elif tag == "table":
            rows = [[{"h": c["h"], "s": norm(c["s"])} for c in r] for r in self.table]
            self.out().append({"k": "table", "rows": rows}); self.table = None
    def text(self, t):
        if self.skip: return
        if self.cell is not None and self.cur is None:
            tgt = self.cell
        elif self.cur is not None:
            tgt = self.cur["s"]
        else:
            if not t.strip(): return
            # bare text inside a callout/card
            self.start_inline("p"); tgt = self.cur["s"]
        st = "".join(sorted(set("".join(self.style))))
        ln = self.link[-1] if self.link else ""
        t = re.sub(r"\s+", " ", t) if t != "\n" else t
        if tgt and tgt[-1][1] == st and tgt[-1][2] == ln:
            tgt[-1][0] += t
        else:
            tgt.append([t, st, ln])
    def handle_data(self, d):
        self.text(d)

def norm(spans):
    sp = [list(s) for s in spans if s[0]]
    if sp:
        sp[0][0] = sp[0][0].lstrip(); sp[-1][0] = sp[-1][0].rstrip()
    return [s for s in sp if s[0]]

def section(route):
    m = re.search(r'<section data-route="%s"[^>]*>(.*?)</section>' % route, TPL, re.S)
    c = Conv(); c.feed(m.group(1)); c.end_inline()
    return c.blocks

content = {}
for r in ("l1", "l2", "primer", "l3", "l4", "calc"):
    content[r] = section(r)
gl = section("glossary")
content["glossary"] = []
it = iter([b for b in gl if b.get("k") in ("dt", "dd")])
for dt in it:
    dd = next(it)
    content["glossary"].append({"t": "".join(s[0] for s in dt["s"]), "d": "".join(s[0] for s in dd["s"])})
# JS data via node
js = re.search(r"(const PARTS = \[.*?\n\];)", TPL, re.S).group(1) + "\n" + re.search(r"(const DECKS=\[.*?\n\];)", TPL, re.S).group(1)
js += "\nconsole.log(JSON.stringify({parts:PARTS,decks:DECKS}));"
data = json.loads(subprocess.run(["node", "-e", js], capture_output=True, check=True, text=True).stdout)
content["parts"] = data["parts"]; content["decks"] = data["decks"]
(ASSETS / "content.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

for key, (fn, title, short) in web.DOCS.items():
    p = ROOT / "chain-theory" / "pdfs" / fn
    d = {"title": title, "short": short, "pages": web.pages(p, slides=(key == "talk")), "outline": web.outline(p)}
    (ASSETS / f"{key}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    shutil.copy(p, ASSETS / f"{key}.pdf")
print("ok", {k: len(v) for k, v in content.items()})
