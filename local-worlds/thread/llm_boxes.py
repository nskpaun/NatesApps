"""Sentence -> local LLM picks pieces and placements -> code expands them into boxes."""
import json, sys, urllib.request
ROOM = 4.0
SIZES = {  # width along wall, depth out from wall
    "sofa": (2.0, 0.9), "armchair": (0.85, 0.85), "coffee_table": (1.0, 0.6), "bookshelf": (1.2, 0.35),
    "floor_lamp": (0.35, 0.35), "window": (1.6, 0.06), "desk": (1.4, 0.7), "side_table": (0.45, 0.45),
    "bed": (1.6, 2.0), "chair": (0.45, 0.5), "plant": (0.5, 0.5), "cabinet": (1.0, 0.45), "dining_table": (1.6, 0.9),
}

def local_boxes(kind, w, d):
    """Boxes in local frame: u along wall [0,w], v out from wall [0,d], y up."""
    if kind in ("sofa", "armchair"):
        return [((0, 0, 0), (w, 0.45, d)), ((0, 0.45, 0), (w, 0.95, 0.25)),
                ((0, 0, 0), (0.18, 0.65, d)), ((w - 0.18, 0, 0), (w, 0.65, d))]
    if kind == "bed":
        return [((0, 0, 0), (w, 0.5, d)), ((0, 0.5, 0), (w, 1.1, 0.12))]
    if kind == "chair":
        return [((0, 0, 0), (w, 0.45, d)), ((0, 0.45, 0), (w, 0.9, 0.08))]
    if kind == "plant":
        return [((0.1, 0, 0.1), (w - 0.1, 0.4, d - 0.1)), ((0, 0.4, 0), (w, 1.4, d))]
    if kind == "cabinet":
        return [((0, 0, 0), (w, 0.9, d))]
    if kind in ("coffee_table", "desk", "side_table", "dining_table"):
        h = {"coffee_table": 0.42, "desk": 0.75, "side_table": 0.55, "dining_table": 0.75}[kind]
        L = 0.06
        return [((0, h - 0.06, 0), (w, h, d))] + [((u, 0, v), (u + L, h - 0.06, v + L))
                                                   for u in (0.02, w - L - 0.02) for v in (0.02, d - L - 0.02)]
    if kind == "bookshelf":
        return [((0, 0, 0), (w, 2.0, d))]
    if kind == "floor_lamp":
        return [((0.15, 0, 0.15), (0.2, 1.5, 0.2)), ((0, 1.5, 0), (w, 1.82, d))]
    if kind == "window":
        return [((0, 0.9, 0), (w, 2.1, d))]
    raise ValueError(kind)

def place(kind, wall, along, gap=0.0):
    w, d = SIZES[kind]
    if wall == "center":
        u0, v0 = (ROOM - w) / 2, (ROOM - d) / 2 - 0.2
        return [{"min": [u0 + a[0], a[1], v0 + a[2]], "max": [u0 + b[0], b[1], v0 + b[2]]} for a, b in local_boxes(kind, w, d)]
    u0 = min(max(along * ROOM - w / 2, 0.05), ROOM - w - 0.05)
    out = []
    for a, b in local_boxes(kind, w, d):
        us, vs = (u0 + a[0], u0 + b[0]), (gap + a[2], gap + b[2])
        if wall == "back":   lo, hi = (us[0], a[1], ROOM - vs[1]), (us[1], b[1], ROOM - vs[0])
        elif wall == "front": lo, hi = (us[0], a[1], vs[0]), (us[1], b[1], vs[1])
        elif wall == "left":  lo, hi = (vs[0], a[1], us[0]), (vs[1], b[1], us[1])
        elif wall == "right": lo, hi = (ROOM - vs[1], a[1], us[0]), (ROOM - vs[0], b[1], us[1])
        out.append({"min": [round(x, 3) for x in lo], "max": [round(x, 3) for x in hi]})
    return out

if __name__ == "__main__":
    req, path = sys.argv[1], sys.argv[2]
    prompt = f"""Lay out a square room. Choose pieces from: {', '.join(SIZES)}.
For each piece give "wall": one of back, left, right, front, center; and "along": a number 0..1 for position along that wall
(for back/front walls 0 = left end, 1 = right end; for left/right walls 0 = front end, 1 = back end). A corner is a wall with along 0 or 1.
Use along 0.5 (centred on the wall) unless the request says a corner or an end. "In the middle of the room" means wall "center".
A piece "by a window" goes on the same wall as the window, with the same along, and you must also add the window.
Do not put two pieces at the same place on the same wall (except a seat by its window).
Return JSON only: {{"pieces":[{{"type":str,"wall":str,"along":number}}]}}
Request: {req}"""
    body = json.dumps({"model": "qwen3.5:9b", "stream": False, "think": False, "keep_alive": 0, "options": {"temperature": 0.1, "num_ctx": 4096}, "prompt": prompt}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate", body)))
    txt = r["response"]; pieces = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])["pieces"]
    walls_with_window = {(p["wall"], round(p["along"], 1)) for p in pieces if p["type"] == "window"}
    objs = []
    for p in pieces:
        if p["type"] not in SIZES: continue
        gap = 0.25 if p["type"] != "window" and (p["wall"], round(p["along"], 1)) in walls_with_window else 0.0
        objs.append({"name": p["type"], "wall": p["wall"], "along": p["along"], "boxes": place(p["type"], p["wall"], float(p["along"]), gap)})
        print(p)
    if not objs: raise SystemExit("The layout model returned no usable pieces")
    json.dump({"request": req, "objects": objs}, open(path, "w"), indent=1)
    print("secs", round(r["total_duration"] / 1e9, 1))
