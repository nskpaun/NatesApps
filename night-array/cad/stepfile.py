"""Night Array -- make OCC-written STEP files byte-reproducible.

OpenCASCADE's STEPCAFControl_Writer emits the geometry deterministically, but
the trailing presentation block (one MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_
REPRESENTATION per coloured shape, each followed by its STYLED_ITEMs, style
entities and COLOUR_RGB) comes out in the iteration order of a pointer-hashed
map, so two identical builds can differ in the order of those blocks.

canonicalise() rewrites only that tail:
  * the item list of each presentation representation is a SET in AP214/AP242,
    so it is sorted by a structural key;
  * the representations are sorted by the same key;
  * the tail entities are renumbered depth-first from the sorted roots, starting
    at the tail's first id, and re-wrapped deterministically.
The geometry entities and every reference into them are untouched, so the file
is the same model; it is just written in one canonical order.  The FILE_NAME
timestamp is fixed as well.
"""

import os
import re

REF = re.compile(r"#(\d+)")
MDGPR = "MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION"
FIXED_STAMP = "2026-11-07T00:00:00"


def _split_entities(data):
    """Split the DATA section body into entity strings (';' terminator outside string literals)."""
    out, cur, in_str = [], [], False
    for ch in data:
        cur.append(ch)
        if ch == "'":
            in_str = not in_str
        elif ch == ";" and not in_str:
            out.append("".join(cur[:-1]).strip())   # without the terminator
            cur = []
    if "".join(cur).strip():
        raise ValueError("unterminated STEP entity")
    return out


def _outside_strings(text, fn):
    """Apply fn to the parts of text outside '...' literals ('' escapes keep the parity right)."""
    parts = text.split("'")
    for i in range(0, len(parts), 2):
        parts[i] = fn(parts[i])
    return "'".join(parts)


def _map_refs(text, fn):
    return _outside_strings(text, lambda s: REF.sub(lambda m: fn(int(m.group(1))), s))


def _refs(text):
    out = []
    _map_refs(text, lambda n: out.append(n) or "#%d" % n)
    return out


def _unwrap(text):
    return _outside_strings(text, lambda s: re.sub(r"\s*\n\s*", "", s))


def _wrap(line, width=76):
    """Re-wrap after commas (continuation lines indented by 4, like OCC's writer)."""
    if len(line) <= width or any("," in s for s in line.split("'")[1::2]):
        return line
    out, cur = [], ""
    for tok in re.split(r"(?<=,)", line):
        if cur and len(cur) + len(tok) > (width if not out else width - 4):
            out.append(cur)
            cur = tok
        else:
            cur += tok
    out.append(cur)
    return "\n    ".join(out)


def canonicalise(txt, file_name=None):
    if file_name:
        txt = re.sub(r"FILE_NAME\('[^']*','[^']*'", "FILE_NAME('%s','%s'" % (file_name, FIXED_STAMP), txt, count=1)
    head, rest = txt.split("\nDATA;\n", 1)
    data, end = rest.split("\nENDSEC;\nEND-ISO-10303-21;", 1)
    parsed = []
    for e in _split_entities(data):
        m = re.match(r"#(\d+)\s*=\s*(.*)$", e, re.S)
        parsed.append((int(m.group(1)), m.group(2)))
    first = next((k for k, (_, b) in enumerate(parsed) if b.startswith(MDGPR)), None)
    if first is None:
        return txt
    head_ents, tail = parsed[:first], parsed[first:]
    tail_ids = {i for i, _ in tail}
    for _, b in head_ents:
        if set(_refs(b)) & tail_ids:
            raise ValueError("STEP geometry references the presentation tail; refusing to reorder")
    body = {i: _unwrap(b) for i, b in tail}
    memo = {}

    def key(i):
        if i not in memo:
            memo[i] = _map_refs(body[i], lambda n: "{" + key(n) + "}" if n in tail_ids else "#%d" % n)
        return memo[i]

    roots = [i for i, _ in tail if body[i].startswith(MDGPR)]
    for r in roots:
        m = re.match(re.escape(MDGPR) + r"(\('[^']*',\()([^)]*)(\),.*)$", body[r], re.S)
        items = sorted((int(x) for x in REF.findall(m.group(2))), key=key)
        body[r] = MDGPR + m.group(1) + ",".join("#%d" % x for x in items) + m.group(3)
    memo.clear()
    roots.sort(key=key)

    new_id, order = {}, []
    nxt = [tail[0][0]]

    def visit(i):
        stack = [i]
        while stack:
            j = stack.pop()
            if j in new_id:
                continue
            new_id[j] = nxt[0]
            nxt[0] += 1
            order.append(j)
            stack.extend(reversed([n for n in _refs(body[j]) if n in tail_ids]))

    for r in roots:
        visit(r)
    for i, _ in tail:  # anything not reachable from a representation (not expected)
        visit(i)

    lines = [f"#{i} = {b};" for i, b in head_ents]
    if not data.startswith("\n".join(lines) + "\n"):
        raise ValueError("STEP geometry section would change; refusing to rewrite")
    for i in order:
        b = _map_refs(body[i], lambda n: "#%d" % new_id[n] if n in tail_ids else "#%d" % n)
        lines.append(_wrap(f"#{new_id[i]} = {b};"))
    return head + "\nDATA;\n" + "\n".join(lines) + "\nENDSEC;\nEND-ISO-10303-21;" + end


def canonicalise_file(path):
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    out = canonicalise(txt, os.path.basename(path))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
