"""Night Array -- drawing sheets (SVG), top-view DXF and PNG rasters.

Views come from CadQuery's SVG exporter (cadquery.occ_impl.exporters.svg.getSVG,
exact HLR).  Each view's paths are re-scaled onto one A3 sheet at a common
standard scale (third-angle projection: top over front, right side view to the
right, plus an isometric), restyled to ivory / amber linework on a transparent
background so the sheet reads on the app's dark #15110F panel, and finished with
overall dimension lines, a parts list and a title block.
"""

import math
import os
import re
import subprocess

import cadquery as cq
from cadquery import Vector
from cadquery.occ_impl.exporters import svg as cqsvg

# coarser discretisation than CadQuery's 1e-3 mm default keeps the sheets small
cqsvg.DISCRETIZATION_TOLERANCE = 0.06

SHEET_W, SHEET_H = 420.0, 297.0          # A3 landscape, mm
MARGIN = 10.0
INK = "#F2EAE1"
MUTED = "#A39A90"
AMBER = "#F2A04A"
LINE = "#5A4E45"
FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"
SCALES = [(1, 1), (1, 2), (1, 2.5), (1, 4), (1, 5), (1, 8), (1, 10), (1, 15), (1, 20)]
ISO_DIR = (0.62, 0.52, 1.0)

HIDDEN = {"base", "dock", "stand", "display", "laptop", "mouse", "structure"}
# groups whose lofted B-spline shells defeat the exact HLR silhouette search -> polygonal HLR on a fine mesh
POLY_HLR = {"mouse"}
GROUP_ORDER = ["display", "stand", "base", "dock", "laptop", "keyboard", "mouse", "deskmat", "structure", "electronics"]


# ----------------------------------------------------------------------------
# projection
# ----------------------------------------------------------------------------

def _parse(svgtxt):
    hid = svgtxt.split("<!-- hidden lines -->")[1].split("<!-- solid lines -->")[0]
    vis = svgtxt.split("<!-- solid lines -->")[1]

    def paths(chunk):
        out = []
        for d in re.findall(r'd="([^"]*)"', chunk):
            pts = [(float(a), float(b)) for a, b in re.findall(r"[ML]\s*(-?[\d.eE+-]+),(-?[\d.eE+-]+)", d)]
            clean = []
            for p in pts:
                p = (round(p[0], 3), round(p[1], 3))
                if not clean or abs(p[0] - clean[-1][0]) > 1e-3 or abs(p[1] - clean[-1][1]) > 1e-3:
                    clean.append(p)
            clean = simplify(clean, 0.04)
            if len(clean) >= 2:
                out.append(clean)
        return out

    return paths(vis), paths(hid)


def _view_shape(shape, view):
    if view == "top":
        return shape.rotate(Vector(0, 0, 0), Vector(1, 0, 0), 90), (0, 0, 1)
    if view == "side":
        return shape.rotate(Vector(0, 0, 0), Vector(0, 1, 0), -90), (0, 0, 1)
    if view == "iso":
        return shape, ISO_DIR
    return shape, (0, 0, 1)


def _chain(segs):
    """Join 2-point segments that share endpoints into polylines."""
    from collections import defaultdict
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    adj = defaultdict(list)
    for i, (a, b) in enumerate(segs):
        adj[key(a)].append(i)
        adj[key(b)].append(i)
    used = [False] * len(segs)
    out = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        line = [segs[i][0], segs[i][1]]
        for end in (1, 0):
            while True:
                tip = line[-1] if end else line[0]
                nxt = [j for j in adj[key(tip)] if not used[j]]
                if not nxt:
                    break
                j = nxt[0]
                used[j] = True
                a, b = segs[j]
                q = b if key(a) == key(tip) else a
                if end:
                    line.append(q)
                else:
                    line.insert(0, q)
        out.append(simplify(line, 0.04))
    return out


def project_poly(shape, view):
    """Polygonal HLR (HLRBRep_PolyAlgo) -- used where exact HLR misses silhouettes of lofted shells."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_PolyAlgo, HLRBRep_PolyHLRToShape
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    s, d = _view_shape(shape, view)
    BRepTools.Clean_s(s.wrapped)
    BRepMesh_IncrementalMesh(s.wrapped, 0.03, False, 0.12, True)
    algo = HLRBRep_PolyAlgo()
    algo.Load(s.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*d))))
    algo.Update()
    h = HLRBRep_PolyHLRToShape()
    h.Update(algo)

    def segs(*comps):
        out = []
        for c in comps:
            if c.IsNull():
                continue
            for e in cq.Shape.cast(c).Edges():
                a, b = e.startPoint(), e.endPoint()
                out.append(((a.x, a.y), (b.x, b.y)))
        return out

    vis = _chain(segs(h.VCompound(), h.OutLineVCompound(), h.Rg1LineVCompound()))
    hid = _chain(segs(h.HCompound(), h.OutLineHCompound()))
    ax = gp_Ax2(gp_Pnt(), gp_Dir(*d))
    vis, hid = _promote_outline(s, ax, vis, hid)
    return _bridge(vis), _bridge(hid)


def _promote_outline(shape, ax, vis, hid, delta=0.25, samples=12):
    """PolyAlgo sometimes files short stretches of the outer silhouette under 'hidden'.

    Nothing can hide the outer outline of the group's own projection, so a hidden
    polyline whose points all have material on exactly one side (ray cast along the
    view direction, `delta` mm either side of the line) is moved to the visible set.
    """
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    X, Y, Z = ax.XDirection(), ax.YDirection(), ax.Direction()
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape.wrapped, 1e-4)

    def covered(u, v):
        p = gp_Pnt(u * X.X() + v * Y.X(), u * X.Y() + v * Y.Y(), u * X.Z() + v * Y.Z())
        inter.Perform(gp_Lin(p, gp_Dir(Z.X(), Z.Y(), Z.Z())), -1e5, 1e5)
        return inter.IsDone() and inter.NbPnt() > 0

    keep_hidden = []
    for pl in hid:
        if len(pl) < 2:
            continue
        L = sum(math.dist(pl[i], pl[i + 1]) for i in range(len(pl) - 1))
        if L < 0.3:
            keep_hidden.append(pl)
            continue
        # sample points along the polyline (with the local direction)
        pts, acc, k = [], 0.0, 0
        targets = [L * (i + 0.5) / samples for i in range(samples)]
        for i in range(len(pl) - 1):
            a, b = pl[i], pl[i + 1]
            seg = math.dist(a, b)
            while k < len(targets) and targets[k] <= acc + seg:
                t = (targets[k] - acc) / seg if seg else 0.0
                pts.append(((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), ((b[0] - a[0]) / (seg or 1), (b[1] - a[1]) / (seg or 1))))
                k += 1
            acc += seg
        outer = True
        for (u, v), (tx, ty) in pts:
            nx, ny = -ty, tx
            if covered(u + delta * nx, v + delta * ny) == covered(u - delta * nx, v - delta * ny):
                outer = False
                break
        (vis if outer else keep_hidden).append(pl)
    return vis, keep_hidden


def _bridge(polys, tol=1.3, cos_min=0.95):
    """Close the small breaks PolyAlgo leaves in smooth silhouettes.

    Two polyline ends are joined only if they are within `tol` mm, their outward
    tangents continue each other (cos >= cos_min) and the gap itself runs along
    that tangent -- so parallel features a fraction of a mm apart (button split,
    wheel slot) are never merged.
    """
    polys = [list(p) for p in polys if len(p) >= 2]
    closed = [False] * len(polys)

    def end(p, e):
        a, b = (p[-1], p[-2]) if e else (p[0], p[1])
        t = (a[0] - b[0], a[1] - b[1])
        n = math.hypot(*t) or 1.0
        return a, (t[0] / n, t[1] / n)

    while True:
        best = None
        for i, pi in enumerate(polys):
            if closed[i]:
                continue
            for ei in (0, 1):
                a, ta = end(pi, ei)
                for j in range(i, len(polys)):
                    if closed[j]:
                        continue
                    for ej in (0, 1):
                        if j == i and (ej <= ei or len(pi) < 4):
                            continue
                        b, tb = end(polys[j], ej)
                        d = math.dist(a, b)
                        if d > tol or -(ta[0] * tb[0] + ta[1] * tb[1]) < cos_min:
                            continue
                        if d > 1e-3:
                            g = ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
                            if g[0] * ta[0] + g[1] * ta[1] < cos_min or -(g[0] * tb[0] + g[1] * tb[1]) < cos_min:
                                continue
                        if best is None or d < best[0]:
                            best = (d, i, ei, j, ej)
        if best is None:
            return [simplify(p, 0.04) for p in polys]
        _, i, ei, j, ej = best
        if i == j:                      # closes a loop
            polys[i].append(polys[i][0])
            closed[i] = True
            continue
        pi = polys[i] if ei else polys[i][::-1]
        pj = polys[j] if not ej else polys[j][::-1]
        polys[i] = pi + pj
        del polys[j]
        del closed[j]


def project(shape, view, poly=False):
    """Return (visible, hidden) polylines in projected model mm (x right, y up)."""
    if poly:
        return project_poly(shape, view)
    s = shape
    if view == "top":
        s = s.rotate(Vector(0, 0, 0), Vector(1, 0, 0), 90)
        d = (0, 0, 1)
    elif view == "side":
        s = s.rotate(Vector(0, 0, 0), Vector(0, 1, 0), -90)
        d = (0, 0, 1)
    elif view == "iso":
        d = ISO_DIR
    else:
        d = (0, 0, 1)
    txt = cqsvg.getSVG(s, {"projectionDir": d, "showAxes": False, "showHidden": True, "width": 800, "height": 600})
    return _parse(txt)


def simplify(pts, eps):
    """Douglas-Peucker polyline simplification (model mm)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / L if L > 1e-12 else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if best > eps and bi > 0:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def bounds(polys):
    xs = [p[0] for pl in polys for p in pl]
    ys = [p[1] for pl in polys for p in pl]
    return min(xs), min(ys), max(xs), max(ys)


# ----------------------------------------------------------------------------
# SVG building blocks
# ----------------------------------------------------------------------------

def f2(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _num(h):
    """Hundredths of a mm -> shortest decimal text ("-.05", "1.2", "12")."""
    t = f"{abs(h) / 100:.2f}".rstrip("0").rstrip(".")
    if t.startswith("0."):
        t = t[1:]
    return ("-" if h < 0 else "") + (t or "0")


def path_d(polylines):
    """Compact SVG path data: absolute M per polyline, then relative l-steps.

    Points are snapped to a 0.01 mm grid first and the steps are exact differences
    of snapped points, so the relative form carries no rounding drift."""
    out = []
    for pl in polylines:
        q = [(round(x * 100), round(y * 100)) for x, y in pl]
        pts = [q[0]] + [p for i, p in enumerate(q[1:], 1) if p != q[i - 1]]
        if len(pts) < 2:
            continue
        toks = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            toks += [_num(x1 - x0), _num(y1 - y0)]
        body = toks[0]
        for t in toks[1:]:
            body += t if t.startswith("-") else " " + t
        out.append(f"M{_num(pts[0][0])} {_num(pts[0][1])}l{body}")
    return "".join(out)


class View:
    def __init__(self, name, vis, hid):
        self.name, self.vis, self.hid = name, vis, hid
        self.b = bounds(vis + hid) if (vis or hid) else (0, 0, 1, 1)

    def size(self, k):
        x0, y0, x1, y1 = self.b
        return (x1 - x0) * k, (y1 - y0) * k

    def place(self, ox, oy, k):
        self.ox, self.oy, self.k = ox, oy, k

    def to_sheet(self, x, y):
        x0, y0, x1, y1 = self.b
        return self.ox + (x - x0) * self.k, self.oy + (y1 - y) * self.k

    def svg(self, hidden=True, sw=0.28):
        out = []
        if hidden and self.hid:
            d = path_d([self.to_sheet(*p) for p in pl] for pl in self.hid)
            out.append(f'<path d="{d}" fill="none" stroke="{AMBER}" stroke-opacity="0.6" stroke-width="0.22" '
                       f'stroke-dasharray="1.2,0.9" stroke-linecap="round"/>')
        d = path_d([self.to_sheet(*p) for p in pl] for pl in self.vis)
        out.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')
        return "\n".join(out)

    def rect(self):
        w, h = self.size(self.k)
        return self.ox, self.oy, w, h


def text(x, y, s, size=3.0, fill=INK, anchor="start", weight=300, spacing=0.0, extra=""):
    s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<text x="{f2(x)}" y="{f2(y)}" font-family="{FONT}" font-size="{f2(size)}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{f2(spacing)}" {extra}>{s}</text>')


def arrow(x, y, ang, size=2.2):
    a1, a2 = ang + math.radians(160), ang - math.radians(160)
    p1 = (x + size * math.cos(a1), y + size * math.sin(a1))
    p2 = (x + size * math.cos(a2), y + size * math.sin(a2))
    return f'<path d="M{f2(x)},{f2(y)} L{f2(p1[0])},{f2(p1[1])} L{f2(p2[0])},{f2(p2[1])} Z" fill="{AMBER}"/>'


def dim_h(xa, xb, y_obj, y_line, label):
    """Horizontal dimension between sheet x positions xa, xb; extension lines from y_obj to y_line."""
    out = []
    sgn = 1 if y_line > y_obj else -1
    for x in (xa, xb):
        out.append(f'<line x1="{f2(x)}" y1="{f2(y_obj + sgn * 1.2)}" x2="{f2(x)}" y2="{f2(y_line + sgn * 1.8)}" '
                   f'stroke="{AMBER}" stroke-width="0.14" stroke-opacity="0.8"/>')
    out.append(f'<line x1="{f2(xa)}" y1="{f2(y_line)}" x2="{f2(xb)}" y2="{f2(y_line)}" stroke="{AMBER}" stroke-width="0.18"/>')
    out.append(arrow(xa, y_line, math.pi))
    out.append(arrow(xb, y_line, 0))
    ty = y_line - 1.3 if sgn < 0 or True else y_line + 3.6
    out.append(text((xa + xb) / 2, ty, label, 2.9, INK, "middle", 400, 0.2))
    return "\n".join(out)


def dim_v(ya, yb, x_obj, x_line, label):
    out = []
    sgn = 1 if x_line > x_obj else -1
    for y in (ya, yb):
        out.append(f'<line x1="{f2(x_obj + sgn * 1.2)}" y1="{f2(y)}" x2="{f2(x_line + sgn * 1.8)}" y2="{f2(y)}" '
                   f'stroke="{AMBER}" stroke-width="0.14" stroke-opacity="0.8"/>')
    out.append(f'<line x1="{f2(x_line)}" y1="{f2(ya)}" x2="{f2(x_line)}" y2="{f2(yb)}" stroke="{AMBER}" stroke-width="0.18"/>')
    out.append(arrow(x_line, ya, -math.pi / 2))
    out.append(arrow(x_line, yb, math.pi / 2))
    cx, cy = x_line - 1.3, (ya + yb) / 2
    out.append(text(cx, cy, label, 2.9, INK, "middle", 400, 0.2, f'transform="rotate(-90 {f2(cx)} {f2(cy)})"'))
    return "\n".join(out)


def fmt_len(v):
    v = round(v, 1)
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    if "." not in s and abs(v) >= 1000:
        s = f"{int(v):,}".replace(",", " ")
    return s


def fmt_mass(g):
    if g >= 1000:
        return f"{g / 1000:.2f} kg"
    if g >= 10:
        return f"{g:.0f} g"
    return f"{g:.1f} g" if g >= 0.1 else "<0.1 g"


# ----------------------------------------------------------------------------
# sheet
# ----------------------------------------------------------------------------

def projection_symbol(x, y):
    """Third-angle projection symbol."""
    return (f'<g stroke="{MUTED}" stroke-width="0.2" fill="none">'
            f'<path d="M{f2(x)},{f2(y + 1.2)} L{f2(x + 7)},{f2(y)} L{f2(x + 7)},{f2(y + 6)} L{f2(x)},{f2(y + 4.8)} Z"/>'
            f'<circle cx="{f2(x + 13)}" cy="{f2(y + 3)}" r="3"/><circle cx="{f2(x + 13)}" cy="{f2(y + 3)}" r="1.4"/>'
            f'<line x1="{f2(x - 1.5)}" y1="{f2(y + 3)}" x2="{f2(x + 17.5)}" y2="{f2(y + 3)}" stroke-dasharray="2,0.8,0.4,0.8"/></g>')


def layout(views, n_rows):
    """Choose scale + arrangement. Returns dict with positions, or None."""
    front, top, side, iso = views["front"], views["top"], views["side"], views["iso"]
    TB_W, TB_H = 168.0, 50.0
    table_h = 7.5 + 4.6 * n_rows
    inner_x0, inner_y0 = MARGIN + 6, MARGIN + 14
    inner_x1, inner_y1 = SHEET_W - MARGIN - 4, SHEET_H - MARGIN - 4
    gap = 16.0     # between views (room for dimensions)
    dimpad = 15.0  # dimension room left / below
    for num, den in SCALES:
        k = num / den
        fw, fh = front.size(k)
        tw, th = top.size(k)
        sw, sh = side.size(k)
        bw = dimpad + max(fw, tw) + gap + sw + 2
        bh = th + gap + fh + dimpad + 8
        # mode A: ortho block left, right column (iso, table, title block)
        col_w = TB_W
        if inner_x0 + bw + 4 <= inner_x1 - col_w and inner_y0 + bh <= inner_y1:
            right_free_h = (inner_y1 - inner_y0) - TB_H - table_h - 10
            if right_free_h > 50:
                return dict(k=k, scale=(num, den), mode="A", bw=bw, bh=bh, iso_box=(inner_x1 - col_w, inner_y0, col_w, right_free_h),
                            table=(inner_x1 - col_w, inner_y1 - TB_H - table_h - 4, col_w), tb=(inner_x1 - TB_W, inner_y1 - TB_H, TB_W, TB_H))
        # mode B: ortho block across the top, iso bottom-left, table + title block bottom-right
        if inner_x0 + bw <= inner_x1 and inner_y0 + bh + TB_H + table_h + 8 <= inner_y1 + 0.1:
            free_h = (inner_y1 - inner_y0) - bh - 4
            iso_w = (inner_x1 - inner_x0) - col_w - 10
            return dict(k=k, scale=(num, den), mode="B", bw=bw, bh=bh,
                        iso_box=(inner_x0, inner_y0 + bh + 4, iso_w, free_h),
                        table=(inner_x1 - col_w, inner_y1 - TB_H - table_h - 4, col_w), tb=(inner_x1 - TB_W, inner_y1 - TB_H, TB_W, TB_H))
    return None


def sheet_svg(gid, gname, views, info):
    L = layout(views, len(info["parts"]))
    assert L, gid
    k = L["k"]
    front, top, side, iso = views["front"], views["top"], views["side"], views["iso"]
    inner_x0, inner_y0 = MARGIN + 6, MARGIN + 14
    fw, fh = front.size(k)
    tw, th = top.size(k)
    sw, sh = side.size(k)
    gap = 16.0
    x_views = inner_x0 + 15.0
    top.place(x_views + (fw - tw) / 2 if tw < fw else x_views, inner_y0 + 4, k)
    front.place(x_views, inner_y0 + 4 + th + gap, k)
    side.place(x_views + max(fw, tw) + gap, inner_y0 + 4 + th + gap, k)

    # iso: at sheet scale when that fits its box; shrunk when it does not; on sparse sheets
    # enlarged (up to 1.6x) to fill the box.  Any scale other than the sheet's is labelled NOT TO SCALE.
    bx, by, bw_, bh_ = L["iso_box"]
    iw, ih = iso.size(1.0)
    fit = min((bw_ - 12) / iw, (bh_ - 14) / ih)
    ki = fit if fit < k else (k if fit < 1.3 * k else min(fit, 1.6 * k))
    iw, ih = iso.size(ki)
    iso.place(bx + (bw_ - iw) / 2, by + 6 + (bh_ - 14 - ih) / 2, ki)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W}mm" height="{SHEET_H}mm" '
           f'viewBox="0 0 {SHEET_W:g} {SHEET_H:g}">',
           f'<title>NIGHT ARRAY — {gname} — {info["number"]}</title>']
    # frame
    out.append(f'<rect x="{MARGIN}" y="{MARGIN}" width="{SHEET_W - 2 * MARGIN}" height="{SHEET_H - 2 * MARGIN}" '
               f'fill="none" stroke="{LINE}" stroke-width="0.35"/>')
    for i in range(1, 8):
        x = MARGIN + (SHEET_W - 2 * MARGIN) * i / 8
        out.append(f'<line x1="{f2(x)}" y1="{MARGIN}" x2="{f2(x)}" y2="{MARGIN + 2.5}" stroke="{LINE}" stroke-width="0.25"/>')
        out.append(f'<line x1="{f2(x)}" y1="{SHEET_H - MARGIN}" x2="{f2(x)}" y2="{SHEET_H - MARGIN - 2.5}" stroke="{LINE}" stroke-width="0.25"/>')
    # heading
    out.append(text(MARGIN + 6, MARGIN + 9, "NIGHT ARRAY", 5.2, INK, "start", 300, 2.2))
    out.append(text(MARGIN + 66, MARGIN + 9, "/  " + gname.upper(), 5.2, AMBER, "start", 300, 1.6))
    out.append(f'<line x1="{MARGIN + 6}" y1="{MARGIN + 11.5}" x2="{MARGIN + 18}" y2="{MARGIN + 11.5}" stroke="{AMBER}" stroke-width="0.5"/>')

    # views
    for v in (top, front, side):
        out.append(v.svg(hidden=info["hidden"]))
    out.append(iso.svg(hidden=False, sw=0.24))

    def label_under(v, s, dy=4.5):
        x, y, w, h = v.rect()
        return text(x, y + h + dy, s, 2.3, MUTED, "start", 400, 0.9)

    lab_dy = 11.5
    out.append(text(top.rect()[0], top.rect()[1] - 2.2, "TOP", 2.3, MUTED, "start", 400, 0.9))
    out.append(text(side.rect()[0], side.rect()[1] - 2.2, "RIGHT SIDE", 2.3, MUTED, "start", 400, 0.9))
    out.append(text(iso.rect()[0], iso.rect()[1] - 2.2,
                    "ISOMETRIC" + ("" if abs(ki - k) < 1e-9 else "  (NOT TO SCALE)"), 2.3, MUTED, "start", 400, 0.9))

    # overall dimensions
    W, H, D = info["dims"]
    fx, fy, fw_, fh_ = front.rect()
    out.append(dim_h(fx, fx + fw_, fy + fh_, fy + fh_ + 8.5, fmt_len(W)))
    out.append(dim_v(fy, fy + fh_, fx, fx - 7.5, fmt_len(H)))
    out.append(text(fx, fy - 2.2, "FRONT", 2.3, MUTED, "start", 400, 0.9))
    sx, sy, sw_, sh_ = side.rect()
    out.append(dim_h(sx, sx + sw_, sy + sh_, sy + sh_ + 8.5, fmt_len(D)))
    tx, ty, tw_, th_ = top.rect()
    if sx > tx + tw_ + 6:
        out.append(dim_v(ty, ty + th_, tx + tw_, tx + tw_ + 7.5, fmt_len(D)))

    # parts list
    tbx, tby, tbw = L["table"]
    out.append(text(tbx, tby + 3.2, "PARTS", 2.3, MUTED, "start", 500, 1.0))
    out.append(text(tbx + tbw, tby + 3.2, "MATERIAL · MASS", 2.3, MUTED, "end", 500, 0.6))
    out.append(f'<line x1="{f2(tbx)}" y1="{f2(tby + 4.8)}" x2="{f2(tbx + tbw)}" y2="{f2(tby + 4.8)}" stroke="{LINE}" stroke-width="0.25"/>')
    for i, (pid, pname, mlabel, mass, internal) in enumerate(info["parts"]):
        yy = tby + 9.0 + i * 4.6
        out.append(text(tbx, yy, f"{i + 1:02d}", 2.4, AMBER, "start", 400, 0.3))
        out.append(text(tbx + 7, yy, pname + (" · internal" if internal else ""), 2.5, INK, "start", 300, 0.15))
        out.append(text(tbx + tbw, yy, f"{mlabel} · {fmt_mass(mass)}", 2.4, MUTED, "end", 300, 0.15))

    # title block
    x, y, w, h = L["tb"]
    hl = lambda yy: f'<line x1="{f2(x)}" y1="{f2(yy)}" x2="{f2(x + w)}" y2="{f2(yy)}" stroke="{LINE}" stroke-width="0.25"/>'
    vl = lambda xx, y0, y1: f'<line x1="{f2(xx)}" y1="{f2(y0)}" x2="{f2(xx)}" y2="{f2(y1)}" stroke="{LINE}" stroke-width="0.25"/>'
    out.append(f'<rect x="{f2(x)}" y="{f2(y)}" width="{f2(w)}" height="{f2(h)}" fill="none" stroke="{LINE}" stroke-width="0.35"/>')
    out += [hl(y + 13), hl(y + 27), hl(y + 43), vl(x + w * 0.62, y + 13, y + 27), vl(x + w * 0.50, y + 27, y + 43),
            vl(x + w * 0.74, y + 27, y + 43)]
    out.append(text(x + 4, y + 8.8, "NIGHT ARRAY", 6.0, INK, "start", 300, 2.6))
    out.append(text(x + w - 4, y + 8.6, "Your hardware. Your OS.", 3.4, AMBER, "end", 400, 0.1,
                    'font-family="Georgia, \'DejaVu Serif\', serif" font-style="italic"'))

    def field(fx_, fy_, lab, val, size=3.1):
        return text(fx_, fy_, lab, 1.9, MUTED, "start", 500, 0.7) + "\n" + text(fx_, fy_ + 4.8, val, size, INK, "start", 400, 0.15)

    out.append(field(x + 4, y + 17.6, "PART", gname.upper(), 3.2))
    out.append(field(x + w * 0.62 + 3, y + 17.6, "DRAWING NO.", info["number"], 3.2))
    # material list, wrapped onto up to two lines
    words, lines, cur = info["materials"].split(", "), [], ""
    for wd in words:
        cand = (cur + ", " + wd) if cur else wd
        if len(cand) > 34 and cur:
            lines.append(cur + ",")
            cur = wd
        else:
            cur = cand
    lines.append(cur)
    out.append(text(x + 4, y + 31.4, "MATERIAL", 1.9, MUTED, "start", 500, 0.7))
    for i, ln in enumerate(lines[:3]):
        out.append(text(x + 4, y + 35.4 + i * 3.3, ln, 2.45, INK, "start", 400, 0.1))
    out.append(field(x + w * 0.50 + 3, y + 31.4, "MASS (EST.)", fmt_mass(info["mass_g"]), 3.0))
    out.append(field(x + w * 0.74 + 3, y + 31.4, "SCALE \u00b7 SHEET", f"{L['scale'][0]}:{L['scale'][1]:g} \u00b7 A3", 3.0))
    out.append(text(x + 4, y + 47.6, f"OVERALL {fmt_len(W)} \u00d7 {fmt_len(H)} \u00d7 {fmt_len(D)} mm (W \u00d7 H \u00d7 D)  \u00b7  "
                    "UNITS mm  \u00b7  THIRD-ANGLE  \u00b7  REV A", 2.2, MUTED, "start", 400, 0.3))
    out.append(projection_symbol(SHEET_W - MARGIN - 26, MARGIN + 3.2))
    out.append("</svg>")
    return "\n".join(out), L


def write_dxf(path, top_view):
    import ezdxf
    # ezdxf stamps the save time, a random $VERSIONGUID and an "ezdxf @ <now>" marker into every file;
    # its fixed-metadata mode writes constants instead, so rebuilds are byte-identical.
    prev = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        doc = ezdxf.new("R2010", setup=False)
        doc.header["$INSUNITS"] = 4       # mm
        doc.header["$MEASUREMENT"] = 1
        for k_ in ("$TDINDWG", "$TDUSRTIMER"):
            doc.header[k_] = 0.0
        doc.layers.add("OUTLINE", color=7)
        msp = doc.modelspace()
        for pl in top_view.vis:
            msp.add_lwpolyline([(round(a, 3), round(b, 3)) for a, b in pl], dxfattribs={"layer": "OUTLINE"})
        doc.saveas(path)
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = prev


def rasterise(svg_paths, png_paths, width=2000):
    """Rasterise SVG sheets with headless Chromium (transparent background)."""
    import json
    js = r"""
const { chromium } = require('playwright');
const fs = require('fs');
const jobs = JSON.parse(process.argv[1]);
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: %(W)d, height: %(H)d }, deviceScaleFactor: 1 });
  for (const [svg, png] of jobs) {
    const src = fs.readFileSync(svg, 'utf8').replace(/^<\?xml[^>]*>/, '');
    await p.setContent('<html><head><style>html,body{margin:0;background:transparent}' +
      'svg{display:block;width:%(W)dpx;height:%(H)dpx}</style></head><body>' + src + '</body></html>');
    await p.evaluate(() => document.fonts.ready.then(() => true));
    await p.screenshot({ path: png, omitBackground: true, clip: { x: 0, y: 0, width: %(W)d, height: %(H)d } });
  }
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
""" % {"W": width, "H": round(width * SHEET_H / SHEET_W)}
    jobs = [[os.path.abspath(s), os.path.abspath(p)] for s, p in zip(svg_paths, png_paths)]
    env = dict(os.environ)
    node_path = env.get("NODE_PATH", "")
    if "/usr/local/lib/node_modules_global" not in node_path:
        env["NODE_PATH"] = (node_path + ":" if node_path else "") + "/usr/local/lib/node_modules_global:/opt/node22/lib/node_modules"
    subprocess.run(["node", "-e", js, "--", json.dumps(jobs)], check=True, env=env)
    try:  # palette-quantise (Pillow ships with cadquery via vtk/matplotlib); keeps alpha
        from PIL import Image
        for png in png_paths:
            im = Image.open(png).convert("RGBA")
            im.quantize(colors=96, method=Image.Quantize.FASTOCTREE).save(png, optimize=True)
    except ImportError:
        pass


def export_all(parts, part_info, group_text, materials, part_mass, export_dir, groups=None, group_order=None):
    import time
    sdir = os.path.join(export_dir, "files", "drawings")
    pdir = os.path.join(export_dir, "drawings")
    os.makedirs(sdir, exist_ok=True)
    os.makedirs(pdir, exist_ok=True)
    svgs, pngs = [], []
    for gi, gid in enumerate(group_order or GROUP_ORDER):
        if groups and gid not in groups:
            continue
        t = time.time()
        pids = [p for p in parts if part_info[p]["group"] == gid]
        comp = cq.Compound.makeCompound([parts[p] for p in pids])
        views = {}
        for v in ("front", "top", "side", "iso"):
            vis, hid = project(comp, v, poly=gid in POLY_HLR)
            views[v] = View(v, vis, hid)
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        bnd = Bnd_Box()
        BRepBndLib.AddOptimal_s(comp.wrapped, bnd, False, False)
        x0_, y0_, z0_, x1_, y1_, z1_ = bnd.Get()
        mats, plist, mass = [], [], 0.0
        for p in pids:
            m = part_info[p]["material"]
            if materials[m][0] not in mats:
                mats.append(materials[m][0])
            g = part_mass(p, parts[p].Volume())[0]
            mass += g
            plist.append((p, part_info[p]["name"], materials[m][0], g, part_info[p]["internal"]))
        info = dict(number=f"NA-{110 + 10 * gi}-{gid.upper()}", dims=(x1_ - x0_, y1_ - y0_, z1_ - z0_),
                    materials=", ".join(mats), mass_g=mass, parts=plist, hidden=gid in HIDDEN)
        svg, L = sheet_svg(gid, group_text[gid]["name"], views, info)
        sp = os.path.join(sdir, gid + ".svg")
        with open(sp, "w") as f:
            f.write(svg)
        write_dxf(os.path.join(sdir, gid + "-top.dxf"), views["top"])
        svgs.append(sp)
        pngs.append(os.path.join(pdir, gid + ".png"))
        print(f"  drawing {gid:10s} scale {L['scale'][0]}:{L['scale'][1]:g} mode {L['mode']}  {time.time() - t:5.1f}s", flush=True)
    rasterise(svgs, pngs)
