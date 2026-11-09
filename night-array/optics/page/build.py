"""Builds page/light-ribbon.html: template.html with the subset of results/results.json the page needs."""
import json
from pathlib import Path

HERE = Path(__file__).parent
res = json.loads((HERE.parent / "results" / "results.json").read_text())


def lay(v, extra=()):
    keep = ("metrics", "nits", "contrast", "box", "size", "geometry", "rays", "emit_angle") + tuple(extra)
    return {k: v[k] for k in keep if k in v}


def r3(v):
    if isinstance(v, list):
        return [r3(x) for x in v]
    if isinstance(v, dict):
        return {k: r3(x) for k, x in v.items()}
    return float(f"{v:.3g}") if isinstance(v, float) else v


data = dict(panel=res["panel"], eye=res["eye"], rooms=res["rooms"], colours=res["colours"], view=res["view"],
            layouts={k: lay(v) for k, v in res["layouts"].items()},
            presets=res["presets"], finishes=res["finishes"],
            variants={k: lay(v, ("params", "hidden_rows", "hidden_mm", "feed_rows", "sill_proud", "eyebox")) | {"stations": r3(v["stations"])}
                      for k, v in res["variants"].items()},
            sweeps=res["sweeps"], shortcut_check=res["shortcut_check"])
html = (HERE / "template.html").read_text().replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
(HERE / "light-ribbon.html").write_text(html)
print(f"wrote page/light-ribbon.html, {len(html) / 1024:.0f} KB")
