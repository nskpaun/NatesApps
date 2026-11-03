#!/usr/bin/env python3
"""Build the single-file offline Chain Theory Explorer.

Usage: python3 chain-theory/web/build.py
Reads PDFs from chain-theory/pdfs/, writes chain-theory/web/chain-theory.html.
Requires: pdftotext (poppler-utils), pypdf.
"""
import base64, json, re, subprocess, pathlib
import pypdf

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PDFS = ROOT / "pdfs"

DOCS = {
    "talk":  ("ChainTheoryTalk.pdf", "An Introduction to Chain Theory (talk)", "Talk"),
    "alpha": ("ChainTheoryAlpha.pdf", "A Parameter-Free Candidate for the Fine-Structure Constant", "Letter"),
    "comp":  ("ChainTheoryCompendium.pdf", "Chain Theory: A Compendium of Preliminary Findings", "Compendium"),
}


def outline(path):
    r = pypdf.PdfReader(str(path))
    out = []

    def walk(items, depth):
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
            else:
                try:
                    p = r.get_destination_page_number(it)
                except Exception:
                    continue
                out.append({"t": str(it.title).strip(), "d": depth, "p": p})
    walk(r.outline, 0)
    return out


def reflow(page):
    lines = [l.rstrip() for l in page.split("\n")]
    paras, buf = [], []
    for l in lines:
        s = l.strip()
        if not s:
            if buf:
                paras.append(buf); buf = []
            continue
        buf.append(s)
    if buf:
        paras.append(buf)
    # split blocks into paragraphs: a short line ending a sentence ends a paragraph
    widths = sorted(len(s) for b in paras for s in b)
    full = widths[int(len(widths) * 0.8)] if widths else 80
    split = []
    for b in paras:
        cur = []
        for s in b:
            cur.append(s)
            if len(s) < 0.82 * full and re.search(r"[.:?!)]$", s):
                split.append(cur); cur = []
        if cur:
            split.append(cur)
    paras = split
    out = []
    for p in paras:
        txt = ""
        for s in p:
            if not txt:
                txt = s
            elif txt.endswith("-") and len(txt) > 1 and txt[-2].isalpha() and s[:1].islower():
                txt = txt[:-1] + s
            else:
                txt += " " + s
        txt = re.sub(r"[ \t]+", " ", txt)
        out.append(txt)
    # drop running header
    out = [p for p in out if p not in ("Chain Theory", "Working Draft", "Chain Theory Working Draft")]
    return "\n\n".join(out).strip()


def slide(page):
    lines = [re.sub(r"\s+", " ", l).strip() for l in page.split("\n")]
    out, prev_blank = [], False
    for l in lines:
        if not l:
            if not prev_blank and out:
                out.append("")
            prev_blank = True
        else:
            out.append(l); prev_blank = False
    return "\n".join(out).strip()


def pages(path, slides=False):
    raw = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")
    pg = raw.split("\f")
    n = len(pypdf.PdfReader(str(path)).pages)
    pg = pg[:n] + [""] * (n - len(pg))
    return [slide(p) if slides else reflow(p) for p in pg]


def main():
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    data = {}
    for key, (fn, title, short) in DOCS.items():
        p = PDFS / fn
        data[key] = {"file": fn, "title": title, "short": short, "pages": pages(p, slides=(key == "talk")), "outline": outline(p)}
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        tpl = tpl.replace(f"__PDF_{key.upper()}__", b64)
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = tpl.replace("__DOCS_JSON__", js)
    out = HERE / "chain-theory.html"
    out.write_text(tpl, encoding="utf-8")
    print(out, round(out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
