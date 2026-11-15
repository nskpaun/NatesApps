"""Checks of the layout code with canned layouts: no model is asked.
  .venv/bin/python -m unittest tests.test_layout        (from the thread folder; under a minute, most of it depth maps)
"""
import os, sys, json, math, hashlib, shutil, subprocess, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); THREAD = os.path.dirname(HERE)
sys.path.insert(0, THREAD)
os.environ.pop("WORLD_SETTING", None)
import llm_boxes as L

# layouts as the model wrote them before motion existed, and the checksum of what the code made of each then
# (json.dumps([room, objects, info], sort_keys=True) with llm_boxes.py as of commit 1288b2c)
OLD = {
 "chapel": ({"room": {"width": 8, "depth": 12, "height": 5}, "pieces": [
    {"label": "altar", "shape": "box", "size": [2, 1, 0.8], "base": 0, "place": {"wall": "back", "along": 0.5}},
    {"label": "pew", "shape": "box", "size": [2.6, 0.9, 0.5], "base": 0, "place": {"at": [0.28, 0.35]}},
    {"label": "pew", "shape": "box", "size": [2.6, 0.9, 0.5], "base": 0, "place": {"at": [0.72, 0.35]}},
    {"label": "column", "shape": "cylinder", "size": [0.25, 5], "base": 0, "place": {"corners": True}}]}, "9b42d9e54c43f2527096cb567bf08e20"),
 "chamber": ({"room": {"width": 12, "depth": 12, "height": 5}, "pieces": [
    {"label": "platform", "shape": "cylinder", "size": [1.5, 0.5], "base": 0, "place": {"at": [0.5, 0.5]}},
    {"label": "seat", "shape": "box", "size": [1.6, 0.5, 0.5], "base": 0, "place": {"ring": {"centre": [0.5, 0.5], "radius": 3, "count": 6, "from": 200, "to": 340}}},
    {"label": "seat", "shape": "box", "size": [1.6, 0.5, 0.5], "base": 0, "place": {"ring": {"centre": [0.5, 0.5], "radius": 4.2, "count": 8, "from": 200, "to": 340}}},
    {"label": "pillar", "shape": "cylinder", "size": [0.3, 5], "base": 0, "place": {"ring": {"centre": [0.5, 0.5], "radius": 5.4, "count": 8, "from": 0, "to": 360}}}]}, "5223c6c7685576fbd43bb7a657442e2f"),
 "reading": ({"room": {"width": 4, "depth": 4, "height": 2.6}, "pieces": [
    {"label": "sofa", "shape": "sofa", "place": {"wall": "back", "along": 0.5}},
    {"label": "window", "shape": "window", "place": {"wall": "left", "along": 0.5}},
    {"label": "armchair", "shape": "armchair", "place": {"wall": "left", "along": 0.5}},
    {"label": "coffee table", "shape": "coffee_table", "place": {"at": [0.5, 0.5]}}]}, "b01931e9df4993649832dc0cae5f802f"),
 "messy": ({"room": {"width": "wide", "depth": 99, "height": 1}, "pieces": [
    "junk", {"label": "no place", "shape": "box"}, {"label": "lantern", "shape": "box", "size": [1, 1, 1], "place": {"at": [0.2, 0.2]}},
    {"label": "stage", "shape": "box", "size": [40, 0.8, 3], "base": 2, "place": {"wall": "back"}},
    {"label": "crate", "shape": "box", "size": 1.5, "base": 1.2, "place": {"at": [2, -1]}},
    {"label": "thing", "shape": "blob", "place": {"at": [0.5, 0.5]}},
    {"label": "bench", "shape": "box", "size": [2, 0.5, 0.5], "place": {"ring": {"centre": [0.5, 0.9], "radius": 5, "count": 9, "from": 180, "to": 360}}},
    {"label": "post", "shape": "cylinder", "size": [0.2, 30], "place": {"wall": "north"}},
    {"label": "desk", "shape": "desk", "place": {"wall": "right", "along": 0.1}}]}, "a0e45f4d34ff894f81c57dd017104fe0"),
}

def made(layout, **kw):
    info = {}; room, objs = L.expand(layout, info, **kw)
    return room, objs, info
piece = lambda **kw: {"label": "thing", "shape": "box", "size": [1, 1, 1], "base": 0, "place": {"at": [0.5, 0.5]}, **kw}
park = lambda *pieces, **kw: {"setting": "outdoor", "room": {"width": 14, "depth": 12, "height": 6}, "pieces": list(pieces), **kw}
def one(mo, out=True, **kw):
    """The checked motion of a single piece (None when it was dropped), and that piece."""
    room, objs, info = made((park if out else lambda *p: {"room": {"width": 6, "depth": 6, "height": 3}, "pieces": list(p)})(piece(motion=mo, **kw)))
    return (info.get("motions") or [None])[0], objs[0]

class Old(unittest.TestCase):
    def test_old_layouts_unchanged(self):
        for name, (layout, want) in OLD.items():
            room, objs, info = made(layout)
            self.assertEqual(hashlib.md5(json.dumps([room, objs, info], sort_keys=True).encode()).hexdigest(), want, name)
            self.assertLessEqual(set(info), {"focus"}, name)
    def test_mood_alone_adds_only_mood(self):
        layout, _ = OLD["reading"]; a = made(layout); b = made({**layout, "setting": "indoor", "mood": {"feel": "warm", "energy": 7, "time": "noon"}, "wind": {"strength": 1}})
        self.assertEqual(a[:2], b[:2]); self.assertEqual(b[2], {"mood": {"feel": "warm", "energy": 1}})
    def test_stamp_ignores_motion(self):
        import shapes
        room, objs, info = made(park(piece(motion={"type": "sway"})))
        self.assertIn("motions", info)
        self.assertEqual(shapes.stamp({"room": room, "objects": objs}), shapes.stamp({"room": room, "objects": objs, **info}))

class Motion(unittest.TestCase):
    def test_sway_clamps(self):
        m, o = one({"type": "sway", "amount": 5, "stiff": -2}, base=3)
        self.assertEqual((m["i"], m["type"], m["amount"], m["stiff"], m["sound"]), (0, "sway", 1, 0, "rustle"))
        self.assertEqual(o["prims"][0]["c"][1], 3.5)                       # a swaying piece may be held up off the ground (a flag)
        m, _ = one({"type": "sway"}); self.assertEqual((m["amount"], m["stiff"]), (0.6, 0.35))
        m, _ = one("sway"); self.assertEqual(m["type"], "sway")
    def test_swing_clamps(self):
        m, o = one({"type": "swing", "pivot": 2.3, "axis": "depth", "angle": 90}, size=[0.5, 0.1, 0.25], base=0.5)
        self.assertEqual((m["pivot"], m["axis"], m["angle"], m["sound"]), (2.3, "depth", 30, "creak"))
        self.assertAlmostEqual(m["period"], 2 * math.pi * math.sqrt(1.75 / 9.8)); self.assertAlmostEqual(o["prims"][0]["c"][1], 0.55)
        m, _ = one({"type": "swing", "pivot": 99, "axis": "sideways", "angle": 1, "period": 0.2}, size=[0.5, 0.1, 0.25], base=0.5)
        self.assertEqual((m["pivot"], m["axis"], m["angle"], m["period"]), (6, "depth", 4, 1.5))      # pivot no higher than the room
        m, _ = one({"type": "swing", "pivot": 0.1, "period": 60}, size=[0.5, 0.1, 0.25], base=0.5)
        self.assertAlmostEqual(m["pivot"], 0.6); self.assertEqual(m["period"], 6)                      # nor below the piece's top
        m, o = one({"type": "swing"}, size=[0.5, 0.5, 0.5], base=50)
        self.assertAlmostEqual(o["prims"][0]["c"][1], 5.75)                # base is kept under the room's height
    def test_swing_stays_clear_of_ground(self):
        m, _ = one({"type": "swing", "pivot": 2, "axis": "width", "angle": 30}, size=[3, 0.1, 0.3], base=0.5)     # a long plank swung endways
        self.assertLess(m["angle"], 30); self.assertGreaterEqual(m["angle"], 4)
        a = math.radians(m["angle"]); self.assertGreaterEqual(2 - (1.5 * math.cos(a) + 1.5 * math.sin(a)), 0.1 - 1e-9)
        m, o = one({"type": "swing", "pivot": 2}, size=[1, 0.2, 1], base=0)                                         # on the ground: it cannot swing
        self.assertIsNone(m); self.assertEqual(o["name"], "thing")
    def test_spin_and_bob_clamp(self):
        m, o = one({"type": "spin", "axis": "x", "period": 0}, base=2); self.assertEqual((m["axis"], m["period"], m["sound"]), ("up", 1, "none"))
        self.assertEqual(o["prims"][0]["c"][1], 2.5)
        m, _ = one({"type": "spin", "axis": "width", "period": 600}); self.assertEqual((m["axis"], m["period"]), ("width", 60))
        m, _ = one({"type": "spin"}); self.assertEqual(m["period"], 8)
        m, _ = one({"type": "bob", "height": 9, "period": 0.1}); self.assertEqual((m["height"], m["period"]), (0.3, 1.5))
        m, _ = one({"type": "bob", "height": 0, "period": 99}); self.assertEqual((m["height"], m["period"]), (0.02, 8))
        m, _ = one({"type": "bob"}); self.assertEqual((m["height"], m["period"]), (0.1, 3))
    def test_path_clamps(self):
        m, _ = one({"type": "path", "points": [[0.1, 0.1], [0.9, 0.1]], "speed": 100, "mode": "round", "pause": 99}, size=[1.8, 1.5, 4.5])
        self.assertEqual((m["mode"], m["pause"], m["sound"]), ("loop", 30, "rumble")); self.assertAlmostEqual(m["speed"], 9.5 / 5)      # no faster than 5 s over its 9.5 m
        m, _ = one({"type": "path", "points": [[0.1, 0.1], [0.9, 0.1]], "speed": 0, "mode": "back", "pause": -5}); self.assertEqual((m["speed"], m["mode"], m["pause"]), (0.2, "back", 0))
        m, _ = one({"type": "path", "points": [[0.1, 0.5], [0.9, 0.5]], "mode": "loop"}, out=False); self.assertEqual((m["mode"], m["pause"]), ("back", 4)); self.assertAlmostEqual(m["speed"], 4.8 / 5)   # indoors: there and back
        big = {"setting": "outdoor", "room": {"width": 24, "depth": 24, "height": 6}, "pieces": [piece(motion={"type": "path", "points": [[0, 0.5], [1, 0.5]], **kw}) for kw in ({}, {"speed": 99})]}
        self.assertEqual([m["speed"] for m in made(big)[2]["motions"]], [2, 4])                          # 2 m/s unless told, and never over 4
        m, _ = one({"type": "path", "points": [[0.4, 0.5], [0.5, 0.5]], "speed": 3}); self.assertAlmostEqual(m["speed"], 1.4 / 5)
        m, _ = one({"type": "path", "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.9, 0.5], [0.9, 0.9], [0.1, 0.9]]}); self.assertEqual(len(m["points"]), 4)
        m, o = one({"type": "path", "points": [[0.5, 0.5], [0.52, 0.5]]}); self.assertIsNone(m); self.assertEqual(o["prims"][0]["c"], [7, 0.5, 6])   # under 1 m: no path
        m, _ = one({"type": "path", "points": [[0.5, 0.5]]}); self.assertIsNone(m)
    def test_path_yaw_and_start(self):
        for pts in ([[0.1, 0.1], [0.9, 0.1]], [[0.9, 0.2], [0.1, 0.2]], [[0.3, 0.1], [0.3, 0.9]], [[0.2, 0.9], [0.8, 0.2], [0.5, 0.5]], [[0, 0], [1, 1]]):
            m, o = one({"type": "path", "points": pts}, size=[1.8, 1.5, 4.5], place={"wall": "left", "along": 0.5})
            (x0, z0), (x1, z1) = m["points"][:2]; p = o["prims"][0]
            self.assertEqual(o["yaw"], math.atan2(x1 - x0, z1 - z0)); self.assertEqual(p["yaw"], o["yaw"])
            self.assertAlmostEqual(p["c"][0], x0); self.assertAlmostEqual(p["c"][2], z0)                # it stands at its first point
            self.assertAlmostEqual(math.sin(o["yaw"]) * (x1 - x0) + math.cos(o["yaw"]) * (z1 - z0), math.dist((x0, z0), (x1, z1)))   # its front (local +v) points along the way it goes
            cs, sn = abs(math.cos(p["yaw"])), abs(math.sin(p["yaw"])); ex, ez = cs * 0.9 + sn * 2.25, sn * 0.9 + cs * 2.25
            self.assertTrue(-1e-9 <= p["c"][0] - ex and p["c"][0] + ex <= 14 + 1e-9 and -1e-9 <= p["c"][2] - ez and p["c"][2] + ez <= 12 + 1e-9, pts)
        m, o = one({"type": "path", "points": [[0.1, 0.1], [0.9, 0.1]]}, size=[1.8, 1.5, 4.5]); self.assertAlmostEqual(o["yaw"], math.pi / 2)   # along +x: its length lies along x
        m, o = made(park({"label": "cart", "shape": "box", "size": [1, 1, 2], "motion": {"type": "path", "points": [[0.2, 0.5], [0.8, 0.5]]}}))[1:]   # no "place" at all
        self.assertEqual(len(m), 1); self.assertEqual(o["motions"][0]["type"], "path")
    def test_bent_path_stays_inside(self):
        hall = lambda *p: {"room": {"width": 8, "depth": 8, "height": 3}, "pieces": list(p)}
        for pts in ([[0.1, 0.1], [0.9, 0.1], [0.9, 0.95]], [[0, 0], [1, 0], [1, 1], [0, 1]], [[0.05, 0.5], [0.5, 0.02], [0.95, 0.5]]):
            room, objs, info = made(hall(piece(size=[1.9, 1.5, 4.8], motion={"type": "path", "points": pts})))
            P = info["motions"][0]["points"]; self.assertGreaterEqual(len(P), 3, pts)
            for k, (x, z) in enumerate(P):            # the piece turns to each leg it is on: both ends of a leg, at that leg's heading
                for (x0, z0), (x1, z1) in zip(P[max(k - 1, 0):k + 1], P[max(k, 1):k + 2]):
                    yaw = math.atan2(x1 - x0, z1 - z0); cs, sn = abs(math.cos(yaw)), abs(math.sin(yaw)); ex, ez = cs * 0.95 + sn * 2.4, sn * 0.95 + cs * 2.4
                    self.assertTrue(-1e-9 <= x - ex and x + ex <= 8 + 1e-9 and -1e-9 <= z - ez and z + ez <= 8 + 1e-9, (pts, k))
        m, o = one({"type": "path", "points": [[0.1, 0.1], [0.5, 0.1], [0.9, 0.1]]}, size=[1.8, 1.5, 4.5])      # straight through three points: only its width keeps it off the edge
        self.assertAlmostEqual(m["points"][0][1], 1.2); self.assertAlmostEqual(m["points"][0][0], 2.25)
    def test_spin_and_bob_clear_ground_and_walls(self):
        m, o = one({"type": "spin", "axis": "depth"}, size=[6, 6, 0.5]); r = math.hypot(3, 3)                     # a wheel on edge: raised until its corners clear the ground
        self.assertEqual(m["axis"], "depth"); self.assertAlmostEqual(o["prims"][0]["c"][1], r + 0.1)
        m, o = one({"type": "spin", "axis": "width"}, size=[1, 2.4, 2], out=False); self.assertIsNone(m); self.assertEqual(o["prims"][0]["c"][1], 1.2)   # no room for it under a 3 m ceiling: it stands still on the floor
        m, o = one({"type": "spin", "axis": "width"}, size=[1, 1, 1], base=0, out=False); r = math.hypot(0.5, 0.5)
        self.assertAlmostEqual(o["prims"][0]["c"][1], r + 0.1); self.assertLessEqual(o["prims"][0]["c"][1] + r, 3)
        m, o = one({"type": "bob", "height": 0.3}, size=[2, 0.4, 3]); self.assertAlmostEqual(o["prims"][0]["c"][1], 0.5)      # bottom at 0.3: it never dips into the ground
        m, o = one({"type": "bob", "height": 0.3}, size=[1, 1, 1], base=9, out=False); self.assertAlmostEqual(o["prims"][0]["c"][1] + 0.5 + 0.3, 3)   # nor into the ceiling
        m, o = one({"type": "bob"}, shape="chair"); self.assertIsNone(m)                                                      # furniture stands on the floor
        m, o = one({"type": "spin"}, shape="chair", out=False); self.assertEqual(m["axis"], "up")
        m, o = one({"type": "spin", "axis": "up"}, size=[2, 2, 0.2], place={"wall": "back", "along": 0.5}, out=False)         # flat on the back wall: pulled out by its half-diagonal
        self.assertAlmostEqual(o["prims"][0]["c"][2], 6 - math.hypot(1, 0.1)); self.assertEqual(o["prims"][0]["c"][0], 3)
        m, o = one({"type": "spin", "axis": "up"}, size=[2, 2, 0.2], place={"wall": "back", "along": 0.5}); self.assertAlmostEqual(o["prims"][0]["c"][2], 11.9)   # outdoors there is no wall
        m, o = one({"type": "spin", "axis": "up"}, size=[5, 1, 5], out=False); self.assertIsNone(m); self.assertEqual(o["prims"][0]["c"], [3, 0.5, 3])      # too big to turn in a 6 m room
        m, o = one({"type": "swing", "pivot": 3, "angle": 30}, shape="cylinder", size=[0.2, 1], base=1, place={"wall": "back", "along": 0.5}, out=False)
        far = 2 * math.sin(math.radians(30)) + 0.2 * math.cos(math.radians(30)); self.assertEqual(m["angle"], 30); self.assertAlmostEqual(o["prims"][0]["c"][2], 6 - far)
        m, o = one({"type": "swing", "pivot": 3, "angle": 30, "axis": "width"}, size=[0.4, 1, 0.4], base=1, place={"wall": "left", "along": 0.5}, out=False)   # on a side wall its width runs along the wall
        self.assertAlmostEqual(o["prims"][0]["c"][0], 0.2); self.assertAlmostEqual(o["prims"][0]["c"][2], 3)
    def test_only_tall_things_sway(self):
        room, objs, info = made({"room": {"width": 4, "depth": 4, "height": 2.6}, "pieces": [{"label": "table", "shape": "dining_table", "place": {"at": [0.5, 0.5]}, "motion": {"type": "sway", "amount": 1}}]})
        self.assertEqual(len(objs), 1); self.assertNotIn("motions", info); self.assertNotIn("wind", info)
        self.assertIsNone(one({"type": "sway"}, size=[1.6, 0.75, 0.9])[0]); self.assertIsNone(one({"type": "sway"}, shape="cylinder", size=[1.5, 0.5])[0])
        self.assertIsNotNone(one({"type": "sway"}, size=[10, 1.6, 1])[0]); self.assertIsNotNone(one({"type": "sway"}, shape="plant")[0])
    def test_frail_pieces_are_kept_only_while_they_move(self):
        frail = [piece(label="lantern", size=[0.3, 0.4, 0.3], base=2, place={"at": [0.2, 0.5]}, motion={"type": "swing", "pivot": 3}),
                 piece(label="flag", size=[1, 0.6, 0.05], place={"at": [0.5, 0.5]}, motion={"type": "sway"}),
                 piece(label="kite", size=[1, 1, 0.1], base=3, place={"at": [0.8, 0.5]}, motion={"type": "bob"})]
        room, objs, info = made(park(*frail)); self.assertEqual([o["name"] for o in objs], ["lantern", "flag", "kite"])
        self.assertEqual([(m["i"], m["type"]) for m in info["motions"]], [(0, "swing"), (1, "sway"), (2, "bob")])
        room, objs, info = made(park(*({**p, "motion": mo} for p, mo in zip(frail, ({"type": "fly"}, None, {"type": "path", "points": [[0.5, 0.5]]})))))
        self.assertEqual(objs, []); self.assertNotIn("motions", info)            # with no usable motion they are left to the painter, as before
        room, objs, info = made(park(piece(label="lantern", size=[0.3, 0.4, 0.3], base=0, motion={"type": "swing", "pivot": 0.4}), piece()))
        self.assertEqual([o["name"] for o in objs], ["thing"]); self.assertNotIn("motions", info)      # nor when the motion is dropped later (it cannot swing on the ground)
    def test_copies_have_distinct_phases(self):
        ring = piece(size=[0.6, 4, 0.6], place={"ring": {"centre": [0.5, 0.5], "radius": 4, "count": 8, "from": 0, "to": 360}}, motion={"type": "sway"})
        room, objs, info = made(park(ring, piece(shape="cylinder", size=[0.3, 3], place={"corners": True}, motion={"type": "spin"}, base=1), piece(motion={"type": "bob"})))
        ms = info["motions"]; self.assertEqual([m["i"] for m in ms], list(range(13))); self.assertEqual(len(objs), 13)
        self.assertEqual(len({m["phase"] for m in ms}), 13); self.assertTrue(all(0 <= m["phase"] < 1 for m in ms))
        self.assertEqual([m["type"] for m in ms], ["sway"] * 8 + ["spin"] * 4 + ["bob"])
        self.assertTrue(all(objs[m["i"]]["prims"][0]["c"][1] == 2.5 for m in ms[8:12]))
    def test_malformed_motion_dropped_piece_kept(self):
        bad = [7, None, [], {}, {"type": "fly"}, {"type": ["sway"]}, {"type": "path"}, {"type": "path", "points": "there"}, {"type": "path", "points": [["a", "b"], [None], 3]},
               {"type": "path", "points": [[float("nan"), 0.1], [0.9, 0.1]]}, "wobble"]
        room, objs, info = made(park(*(piece(motion=m, place={"at": [0.1 + 0.08 * k, 0.5]}) for k, m in enumerate(bad))))
        self.assertEqual(len(objs), len(bad)); self.assertNotIn("motions", info)
        plain = made(park(*(piece(place={"at": [0.1 + 0.08 * k, 0.5]}) for k in range(len(bad)))))
        self.assertEqual(objs, plain[1])
        m, o = one({"type": "swing", "pivot": "high", "angle": "wide", "period": None, "axis": 3}, size=[0.5, 0.1, 0.25], base=0.5, sound=["loud"])   # bad numbers fall back to defaults
        self.assertEqual((m["angle"], m["axis"], m["sound"]), (20, "depth", "creak")); self.assertAlmostEqual(m["pivot"], 2.1)
    def test_sound(self):
        self.assertEqual(one({"type": "sway"}, sound="chirp")[0]["sound"], "chirp")
        self.assertEqual(one({"type": "sway", "sound": "none"})[0]["sound"], "none")
        self.assertEqual(one({"type": "sway"}, sound="roar")[0]["sound"], "rustle")
    def test_caps(self):
        many = [piece(size=[0.3, 1, 0.3], place={"at": [0.05 + 0.018 * k, 0.3]}, motion={"type": "sway"}) for k in range(50)]
        room, objs, info = made(park(*many)); self.assertEqual(len(objs), 50); self.assertEqual(len(info["motions"]), 40)
        spins = [piece(size=[0.3, 1, 0.3], place={"at": [0.05 + 0.04 * k, 0.3]}, motion={"type": "spin"}) for k in range(20)]
        room, objs, info = made(park(*spins, piece(motion={"type": "sway"}), piece(motion={"type": "path", "points": [[0.1, 0.9], [0.9, 0.9]]}, place={"at": [0.5, 0.7]})))
        self.assertEqual([m["type"] for m in info["motions"]], ["spin"] * 12 + ["sway"]); self.assertEqual(len(objs), 22)
        self.assertAlmostEqual(objs[21]["prims"][0]["c"][2], 0.7 * 12); self.assertNotIn("yaw", objs[21])       # the path that did not fit the cap: placed as an ordinary piece
        ring = piece(size=[0.3, 1, 0.3], place={"ring": {"centre": [0.5, 0.5], "radius": 5, "count": 40}}, motion={"type": "sway"})
        room, objs, info = made(park(ring, ring, ring)); self.assertEqual(len(objs), 80); self.assertTrue(all(m["i"] < 80 for m in info["motions"]))

class Gate(unittest.TestCase):
    """What the layout gate added, from what the layout model actually wrote for a park, a street, a garden and a room."""
    def test_held_piece_goes_under_an_arch_or_on_the_front(self):
        frame = piece(label="frame", shape="arch", size=[2.5, 3, 0.3], place={"at": [0.5, 0.6]})
        seat = piece(label="seat", size=[0.8, 0.1, 0.4], base=2.5, place={"on": "Frame"}, motion={"type": "swing", "pivot": 2.5, "rope": 1.8})
        room, objs, info = made(park(frame, seat)); p = objs[1]["prims"][0]; m = info["motions"][0]
        self.assertEqual([round(v, 6) for v in p["c"][::2]], [7.0, 7.2]); self.assertAlmostEqual(p["c"][1] - p["h"][1], 0.6)      # the rope, not base, says how low it hangs
        self.assertNotIn("rope", m); self.assertEqual(m["pivot"], 2.5)
        _, objs, info = made(park(frame, {**seat, "motion": {"type": "swing", "pivot": 2.5}}))               # no rope: base as before
        self.assertAlmostEqual(objs[1]["prims"][0]["c"][1], 2.55)
        tower = piece(label="tower", shape="cylinder", size=[0.6, 3], place={"wall": "right", "along": 0.5})
        sails = piece(label="sails", size=[1.5, 1.5, 0.2], base=5, place={"on": "tower"}, motion={"type": "spin", "axis": "depth"})
        _, objs, info = made(park(tower, sails)); p = objs[1]["prims"][0]
        self.assertAlmostEqual(p["c"][0], 14 - 1.2 - 0.1); self.assertAlmostEqual(p["c"][2], 6.0)             # touching the tower's front
        self.assertLessEqual(p["c"][1] + p["h"][1], 3 + 1e-9); self.assertEqual(objs[1]["yaw"], objs[0]["yaw"])   # and no higher than it
        _, objs, _ = made(park({**sails, "place": {"on": "nothing"}})); self.assertEqual(objs[0]["prims"][0]["c"][::2], [7.0, 6.0])
    def test_ground_is_not_built_and_a_flag_floats(self):
        road = piece(label="road", shape="ground", size=[14, 2], place={"wall": "front", "along": 0.5})
        pole = piece(label="pole", shape="cylinder", size=[0.1, 4], place={"at": [0.5, 0.6]})
        flag = piece(label="flag", size=[1.2, 0.8, 0.05], base=3.9, place={"on": "pole"}, motion={"type": "sway"})
        _, objs, info = made(park(road, pole, flag)); p = objs[1]["prims"][0]
        self.assertEqual([o["name"] for o in objs], ["pole", "flag"]); self.assertEqual(info["motions"][0]["type"], "sway")
        self.assertAlmostEqual(p["c"][1] + p["h"][1], 4.0)
    def test_blocked_path_follows_the_road_or_moves_aside(self):
        road = piece(label="road", shape="ground", size=[14, 2], place={"wall": "front", "along": 0.5})
        tree = piece(label="tree", shape="cylinder", size=[2.5, 7], place={"wall": "back", "along": 0.5})
        car = piece(label="car", size=[1.8, 1.4, 4.2], place={"at": [0.5, 0.1]}, motion={"type": "path", "points": [[0.5, 0.1], [0.5, 0.9]]})
        _, objs, info = made(park(tree, road, car)); m = info["motions"][0]
        self.assertEqual(m["points"], [[2.1, 1.0], [11.9, 1.0]]); self.assertEqual(objs[1]["prims"][0]["c"][::2], [2.1, 1.0])
        self.assertAlmostEqual(objs[1]["yaw"], math.pi / 2); self.assertAlmostEqual(objs[1]["prims"][0]["yaw"], math.pi / 2)
        _, objs, info = made(park(tree, car)); self.assertNotIn("motions", info); self.assertEqual(len(objs), 2)        # no road, no way round: it stands still
        shop = piece(label="shop", size=[14, 3, 6], place={"wall": "back", "along": 0.5})
        car2 = piece(label="car", size=[2, 1.5, 4.5], place={"at": [0.8, 0.7]}, motion={"type": "path", "points": [[0.8, 0.7], [0.2, 0.7]]})
        _, objs, info = made({**park(shop, car2), "room": {"width": 14, "depth": 20, "height": 6}})
        self.assertLessEqual(info["motions"][0]["points"][0][1] + 1, 14 + 0.06)                                         # beside the shop, not in it
        arch = piece(label="gate", shape="arch", size=[3, 3, 0.3], place={"at": [0.5, 0.5]})
        through = piece(label="cart", size=[1.2, 1, 2], place={"at": [0.5, 0.1]}, motion={"type": "path", "points": [[0.5, 0.1], [0.5, 0.9]]})
        _, _, info = made(park(arch, through)); self.assertEqual([[round(v, 6) for v in q] for q in info["motions"][0]["points"]], [[7.0, 1.2], [7.0, 10.8]])   # under a beam is clear
    def test_two_travellers_get_a_strip_each(self):
        a = piece(label="a", size=[1.8, 1.5, 4], place={}, motion={"type": "path", "points": [[0.2, 0.3], [0.8, 0.3]]})
        b = piece(label="b", size=[1.8, 1.5, 4], place={}, motion={"type": "path", "points": [[0.7, 0.3], [0.2, 0.3]]})
        _, objs, info = made(park(a, b)); za, zb = (m["points"][0][1] for m in info["motions"])
        self.assertEqual(len(objs), 2); self.assertGreaterEqual(abs(za - zb), 1.8 + 0.3)
        self.assertEqual(info["motions"][1]["points"][0][1], info["motions"][1]["points"][1][1])
    def test_edge_taken_outdoors_and_cloth_flat_on_a_wall(self):
        shop = piece(label="shop", size=[14, 3, 6], place={"wall": "back", "along": 0.5})
        post = piece(label="post", shape="cylinder", size=[0.2, 6], place={"wall": "back", "along": 0.5})
        _, objs, _ = made(park(shop, post)); self.assertAlmostEqual(objs[1]["prims"][0]["c"][2], 12 - 6 - 0.2)
        indoor = {"room": {"width": 8, "depth": 8, "height": 3}, "pieces": [{**shop, "size": [6, 2, 2]}, post]}
        _, objs, _ = made(indoor); self.assertAlmostEqual(objs[1]["prims"][0]["c"][2], 8 - 0.2)                         # indoors as before
        cloth = piece(label="curtains", size=[0.2, 2.6, 1.8], place={"wall": "front", "along": 0.5}, motion={"type": "sway"})
        _, objs, info = made({"room": {"width": 4, "depth": 5, "height": 2.6}, "pieces": [cloth]})
        self.assertEqual(objs[0]["prims"][0]["h"][::2], [0.9, 0.1]); self.assertIn("motions", info)

class Ground(unittest.TestCase):
    """Flat stretches of ground: told to the painter, never built."""
    road = piece(label="road", shape="ground", size=[14, 3], place={"wall": "front", "along": 0.5})
    def test_grounds_are_listed_and_change_nothing_else(self):
        bed = piece(label="flower bed", shape="ground", size=[3, 4], place={"wall": "left", "along": 0.5})
        stones = piece(label="stone", shape="ground", size=[0.5, 0.5], place={"ring": {"centre": [0.5, 0.5], "radius": 3, "count": 12}})
        rest = [piece(label="tree", shape="cylinder", size=[2, 6], place={"wall": "back", "along": 0.3}), piece(motion={"type": "bob"})]
        a, b = made(park(self.road, rest[0], bed, rest[1], stones, piece(shape="ground", size="wide", place={"at": "x"}))), made(park(*rest))
        self.assertEqual(a[:2], b[:2]); self.assertEqual({k: v for k, v in a[2].items() if k != "grounds"}, b[2]); self.assertNotIn("grounds", b[2])
        g = a[2]["grounds"]; self.assertEqual(len(g), 8); self.assertEqual(g[0], {"name": "road", "c": [7.05, 1.5], "h": [7.0, 1.5], "yaw": 0.0})
        self.assertEqual((g[1]["name"], g[1]["c"], g[1]["h"]), ("flower bed", [2.0, 6.0], [1.5, 2.0])); self.assertAlmostEqual(g[1]["yaw"], math.pi / 2)
        import shapes
        self.assertEqual(shapes.stamp({"room": a[0], "objects": a[1], **a[2]}), shapes.stamp({"room": b[0], "objects": b[1]}))
    def test_a_path_beside_a_road_goes_onto_it(self):
        car = lambda v, **kw: piece(label="car", size=[1.8, 1.4, 4.2], place={}, motion={"type": "path", "points": [[0.1, v], [0.9, v]], **kw})
        for pieces in ((self.road, car(0.25)), (car(0.25), self.road)):                                   # in either order
            m = made(park(*pieces))[2]["motions"][0]; self.assertEqual([[round(v, 6) for v in q] for q in m["points"]], [[2.1, 2.1], [11.9, 2.1]])
        self.assertEqual([round(v, 6) for v in made(park(self.road, car(0.25)))[1][0]["prims"][0]["c"][::2]], [2.1, 2.1])
        m = made(park(self.road, car(0.1)))[2]["motions"][0]; self.assertAlmostEqual(m["points"][0][1], 1.2)        # on it already: left alone
        m = made(park(self.road, car(0.5)))[2]["motions"][0]; self.assertAlmostEqual(m["points"][0][1], 6.0)        # nowhere near it
        across = piece(label="dog", size=[0.4, 0.6, 1], place={}, motion={"type": "path", "points": [[0.5, 0.05], [0.5, 0.9]]})
        m = made(park(self.road, across))[2]["motions"][0]; self.assertEqual([round(q[0], 6) for q in m["points"]], [7.0, 7.0])   # it crosses the road: left alone
        lane = piece(label="lane", shape="ground", size=[14, 1], place={"wall": "front", "along": 0.5})
        m = made(park(lane, car(0.1)))[2]["motions"][0]; self.assertAlmostEqual(m["points"][0][1], 0.9)             # wider than the lane: along its middle, as far as the edge allows

GOOD = park(piece(label="tree left", shape="cylinder", size=[2.5, 7], place={"wall": "back", "along": 0.3}, motion={"type": "sway"}),
            piece(label="tree right", shape="cylinder", size=[2.5, 7], place={"wall": "back", "along": 0.7}, motion={"type": "sway"}),
            piece(label="swing frame", shape="arch", size=[2.5, 3, 0.3], place={"at": [0.5, 0.5]}),
            piece(label="swing seat", size=[0.6, 0.15, 0.3], place={"on": "swing frame"}, motion={"type": "swing", "pivot": 2.9, "rope": 2.2}),
            piece(label="flower bed", shape="ground", size=[3, 2], place={"wall": "left", "along": 0.5}),
            piece(label="bench", size=[2, 0.6, 0.8], place={"wall": "right", "along": 0.5}),
            piece(label="road", shape="ground", size=[14, 2], place={"wall": "front", "along": 0.5}),
            piece(label="car", size=[1.8, 1.4, 4.2], place={"at": [0.1, 0.08]}, motion={"type": "path", "points": [[0.1, 0.08], [0.9, 0.08]]}, sound="rumble"),
            effects=[{"type": "wander", "label": "bees", "at": [0.15, 0.5], "count": 24, "sound": "buzz"}, {"type": "drift", "label": "leaves", "at": [0.5, 0.8]}])
PARK = ("A small park on a breezy day: two big leafy trees at the back, a swing set in the middle with one seat hanging from it, a flower bed on the left with bees "
        "buzzing around it, leaves blowing down from the trees, a bench on the right, and a road along the front edge where a car drives past.")
def swap(layout, label, *new, **kw):
    """The layout with the pieces of that label replaced by `new`."""
    return {**layout, "pieces": [p for p in layout["pieces"] if p["label"] != label and not p["label"].startswith(label + " ")] + list(new), **kw}
weight = lambda fs: sum(w for w, _ in fs)

class Lottery(unittest.TestCase):
    """The layout model writes a clearly worse layout about one time in three: faults() tells, with no model, and choose() asks again."""
    merged = swap(GOOD, "tree", piece(label="back trees", shape="cylinder", size=[3, 7], place={"wall": "back", "along": 0.5}, motion={"type": "sway"}))      # as on 14 November
    swarm = {**GOOD, "pieces": GOOD["pieces"] + [piece(label="bee swarm", size=[0.6, 0.6, 0.6], base=0.8, place={"at": [0.15, 0.5]}, motion={"type": "path", "points": [[0.1, 0.4], [0.2, 0.6]], "mode": "back"}, sound="buzz")], "effects": GOOD["effects"][1:]}
    def test_named(self):
        self.assertEqual([(n, h, t) for n, h, _, t in L.named(PARK)], [(2, "tree", "big leafy trees"), (1, "set", "swing set"), (1, "hanging", "seat hanging"), (1, "bed", "flower bed"), (1, "bench", "bench"), (1, "road", "road"), (1, "drive", "car drives past")])
        self.assertEqual([(n, h, w) for n, h, w, _ in L.named("a small chapel with two rows of pews facing an altar at the back, 3 m high, in a ring")], [(2, "row", ["pew", "facing"]), (1, "altar", ["altar"])])
        self.assertEqual([(n, h) for n, h, _, _ in L.named("A quay: three fishing boats bobbing, a pair of crates, 12 gulls, the lighthouse, a breezy day")], [(3, "boat"), (2, "crate"), (12, "gull")])
        self.assertEqual(L.named(None), []); self.assertEqual(L.named("5"), [])
        self.assertEqual([L.stem(w) for w in ("trees", "benches", "leaves", "glass", "child's", "boxes", "bus", "daisies")], ["tree", "bench", "leave", "glass", "child", "box", "bus", "daisy"])
        self.assertTrue(all(L.same(L.stem(a), L.stem(b)) for a, b in (("leaves", "leaf"), ("shelves", "bookshelf"), ("knives", "knife"), ("caves", "cave"), ("chairs", "armchair"))))
        self.assertFalse(any(L.same(L.stem(a), L.stem(b)) for a, b in (("car", "cart"), ("bed", "flowerbed"), ("cars", "carpet"), ("eve", "elf"))))
    def test_good_layouts_have_no_faults(self):
        self.assertEqual(L.faults(GOOD, PARK), [])
        import re
        ex = re.findall(r'Example for "(.*?)":\n(\{.*?\})\n\n', L.PROMPT, re.S); self.assertEqual(len(ex), 5)
        for req, js in ex: self.assertEqual(L.faults(json.loads(js), req), [], req)                      # the prompt's own examples
        self.assertEqual(L.faults(OLD["chapel"][0], "a small chapel with two rows of pews facing an altar at the back and four columns"), [])
    def test_bad_layouts_have_faults(self):
        fs = L.faults(self.merged, PARK); self.assertEqual([w for w, _ in fs], [3]); self.assertIn('2 "big leafy trees" but only 1', fs[0][1])
        fs = L.faults(self.swarm, PARK); self.assertEqual([w for w, _ in fs], [3]); self.assertIn('"bee swarm"', fs[0][1]); self.assertIn("effects", fs[0][1])
        quiet = {**self.swarm, "pieces": [{k: v for k, v in p.items() if k != "sound"} for p in self.swarm["pieces"]]}
        self.assertEqual([w for w, _ in L.faults(quiet, PARK)], [3])                                     # silent, but it travels above the ground
        fs = L.faults(swap(GOOD, "flower bed"), PARK); self.assertEqual(fs, [(2, 'nothing was made for "flower bed"')])
        fs = L.faults(swap(GOOD, "tree", piece(label="tree", shape="cylinder", size=[1, 6], place={"corners": True})), PARK); self.assertEqual([w for w, _ in fs], [1])     # four for two: noted, not asked again
        fs = L.faults(swap(GOOD, "bench", piece(label="bench", size=[2, 0.6, 0.8], place={"at": [0.5, 0.5]}), piece(label="statue", size=[1, 2, 1], place={"at": [0.52, 0.5]})), PARK)
        self.assertEqual(fs, [(2, '"bench" and "statue" stand inside each other: move them apart')])
        fs = L.faults(swap(GOOD, "car", piece(label="car", size=[1.8, 1.4, 4.2], place={"at": [0.3, 0.9]}, motion={"type": "path", "points": [[0.3, 0.9], [0.7, 0.9]]})), PARK)
        self.assertIn((2, '"car" cannot travel where it was put: give it room'), fs)
        fs = L.faults(swap(GOOD, "swing seat", piece(label="swing seat", size=[0.6, 0.15, 0.3], base=0.5, place={"on": "the frame"}, motion={"type": "swing", "pivot": 2.9})), PARK)
        self.assertEqual(fs, [(1, '"swing seat" is placed on "the frame", which is not a piece')])
        for junk in (None, [], {}, {"pieces": "none"}, {"pieces": [piece(shape="blob")]}): self.assertEqual([w for w, _ in L.faults(junk, PARK)], [10])
        self.assertEqual(L.faults(GOOD, None), []); self.assertGreaterEqual(L.POOR, 2); self.assertLessEqual(L.POOR, 2)
    def test_choose_asks_again_and_keeps_the_best(self):
        def run(*answers):
            asked = []
            def ask(req):
                asked.append(req[len(PARK):]); a = answers[len(asked) - 1]
                if isinstance(a, Exception): raise a
                return a, 2.0
            return L.choose(PARK, ask=ask), asked
        (lay, secs, fs, k, n), asked = run(GOOD); self.assertEqual((lay, secs, fs, k, n, asked), (GOOD, 2.0, [], 1, 1, [""]))          # good at once: asked once, as before
        (lay, secs, fs, k, n), asked = run(self.merged, GOOD); self.assertEqual((lay, secs, fs, k, n), (GOOD, 4.0, [], 2, 2))
        self.assertIn("Do not repeat them", asked[1]); self.assertIn("big leafy trees", asked[1])
        (lay, _, fs, k, n), asked = run(self.merged, self.swarm, swap(GOOD, "flower bed")); self.assertEqual((k, n, weight(fs)), (3, 3, 2)); self.assertEqual(len(asked), 3)
        (lay, _, fs, k, n), _ = run(self.merged, self.swarm, self.merged); self.assertEqual((k, n), (1, 3))                          # equals: the earliest
        (lay, _, fs, k, n), _ = run(ValueError("not JSON"), GOOD); self.assertEqual((lay, k, n), (GOOD, 1, 1))
        (lay, _, fs, k, n), _ = run(self.merged, TimeoutError()); self.assertEqual((lay, k, n), (self.merged, 1, 1))                 # the model went away: what there is
        with self.assertRaises(TimeoutError): run(TimeoutError())
        with self.assertRaises(ValueError): run(ValueError("a"), ValueError("b"), ValueError("c"))
    def test_what_another_try_made_counts(self):
        req = "A study, sofa on the back wall and globe in the middle"      # nothing is brought in with "a": only another try shows what was left out
        full = {"room": {"width": 5, "depth": 5, "height": 2.6}, "pieces": [piece(label="sofa", shape="sofa", place={"wall": "back", "along": 0.5}), piece(label="globe", shape="cylinder", size=[0.3, 1], place={"at": [0.5, 0.5]}),
                piece(label="crate", place={"at": [0.2, 0.2]}), piece(label="barrel", place={"at": [0.22, 0.2]})]}      # the barrel stands in the crate
        bare = {**full, "pieces": full["pieces"][:1]}
        self.assertEqual(L.faults(bare, req), []); self.assertEqual(L.faults(bare, req, ["old globe", "desk", "back shelf"]), [(2, 'nothing was made for "old globe"')])
        answers = iter([full, bare, bare]); lay, _, fs, k, n = L.choose(req, ask=lambda r: (next(answers), 1.0))
        self.assertEqual((k, n), (1, 2)); self.assertEqual(weight(fs), 2)                                # the second try looked clean, but it lacks the globe: no better
    def test_kinds_of_a_thing_are_counted_apart(self):
        req = "A dining room: a dining table in the middle with four chairs around it, a coffee table, two side tables and two armchairs by the window on the left wall."
        room = {"room": {"width": 6, "depth": 6, "height": 2.6}}
        good = {**room, "pieces": [piece(label="dining table", size=[1.8, 0.75, 1], place={"at": [0.5, 0.5]}), piece(label="chair", size=[0.45, 0.9, 0.45], place={"ring": {"centre": [0.5, 0.5], "radius": 1.3, "count": 4}}),
                piece(label="window", shape="window", place={"wall": "left", "along": 0.5}), piece(label="armchair", shape="armchair", place={"wall": "left", "along": 0.25}), piece(label="armchair", shape="armchair", place={"wall": "left", "along": 0.75}),
                piece(label="coffee table", shape="coffee_table", place={"at": [0.5, 0.85]}), piece(label="side table", size=[0.4, 0.5, 0.4], place={"at": [0.9, 0.2]}), piece(label="side table", size=[0.4, 0.5, 0.4], place={"at": [0.9, 0.8]})]}
        self.assertEqual(L.faults(good, req), [])                                                        # an armchair is not one of the four chairs, nor a coffee table a side table
        less = {**room, "pieces": [q for q in good["pieces"] if q["label"] != "armchair"]}
        answers = iter([good, less]); self.assertEqual(L.choose(req, ask=lambda r: (next(answers), 1.0))[3:], (1, 1))      # so it is kept, and no try without the armchairs is asked for
        one = {**room, "pieces": [q for k, q in enumerate(good["pieces"]) if k != 4]}; self.assertEqual([w for w, _ in L.faults(one, req)], [3])      # the two armchairs made as one
    def test_on_a_stage_and_under_a_tree_is_not_inside(self):
        hall = {"room": {"width": 10, "depth": 12, "height": 5}, "pieces": [piece(label="stage", size=[8, 0.8, 3], place={"wall": "back", "along": 0.5}), piece(label="piano", size=[1.5, 1, 1.4], base=0.8, place={"at": [0.5, 0.9]})]}
        self.assertEqual(L.faults(hall, "A small theatre: a stage at the back with a piano on it"), [])
        low = {**hall, "pieces": [hall["pieces"][0], {**hall["pieces"][1], "base": 0}]}; self.assertEqual([w for w, _ in L.faults(low, "A small theatre: a stage at the back with a piano on it")], [2])
        garden = park(piece(label="oak tree", shape="cylinder", size=[2.5, 8], place={"at": [0.5, 0.5]}), piece(label="bench", size=[1.6, 0.9, 0.5], place={"at": [0.6, 0.55]}))
        self.assertEqual(L.faults(garden, "A quiet garden: a big oak tree in the middle with a bench under it"), [])
    def test_a_piece_that_cannot_be_read_stops_nothing(self):
        odd = {**GOOD, "pieces": GOOD["pieces"] + [{"label": "thing", "shape": ["box"], "size": [1, 1, 1], "place": {"at": [0.2, 0.2]}}, {"label": "other", "shape": {"a": 1}}]}
        self.assertEqual(L.faults(odd, PARK), [])
        real = L.faults; L.faults = lambda *a: 1 / 0
        try: self.assertEqual(L.choose(PARK, ask=lambda r: (GOOD, 1.0))[2:], ([], 1, 1))
        finally: L.faults = real

class Outdoor(unittest.TestCase):
    def test_setting(self):
        room, objs, info = made(park(piece(), {"label": "window", "shape": "window", "place": {"wall": "left"}}, surround=" rows of\n trees  ", wind={"strength": 3, "from": 610}))
        self.assertEqual(room, [14, 6, 12]); self.assertEqual([o["name"] for o in objs], ["thing"])
        self.assertEqual(info, {"setting": "outdoor", "surround": "rows of trees", "wind": {"strength": 1, "from": 250}})
        self.assertEqual(made({"setting": "outdoor", "room": {"height": 40}, "pieces": [piece()]})[0][1], 12)
        self.assertEqual(made({"setting": "outdoor", "room": {"height": 1}, "pieces": [piece()]})[0][1], 3)
        self.assertEqual(made({"setting": "Outdoors", "room": {"height": 40}, "pieces": [piece()]})[2], {})     # only the exact word
        self.assertEqual(made(park(piece()))[2]["wind"], {"strength": 0.4, "from": 270})
    def test_override(self):
        layout, _ = OLD["reading"]
        room, objs, info = made(layout, setting="outdoor"); self.assertEqual(info["setting"], "outdoor"); self.assertEqual(room[1], 3); self.assertNotIn("window", [o["name"] for o in objs])
        self.assertEqual(made(park(piece()), setting="indoor")[2], {}); self.assertEqual(made(park(piece()), setting="indoor")[0][1], 6)
        os.environ["WORLD_SETTING"] = "outdoor"
        try: self.assertEqual(made(layout)[2]["setting"], "outdoor")
        finally: del os.environ["WORLD_SETTING"]
        os.environ["WORLD_SETTING"] = "auto"
        try: self.assertEqual(made(layout)[2], {})
        finally: del os.environ["WORLD_SETTING"]
    def test_arch(self):
        room, objs, info = made(park({"label": "frame", "shape": "arch", "size": [2.2, 2.4, 0.3], "place": {"at": [0.5, 0.5]}},
                                     piece(size=[0.5, 0.1, 0.25], base=0.5, motion={"type": "swing", "pivot": 2.3})))
        a = objs[0]; self.assertIs(a["open"], True); self.assertEqual(len(a["prims"]), 3); self.assertNotIn("open", objs[1])
        posts, beam = a["prims"][:2], a["prims"][2]
        self.assertEqual([round(p["c"][0], 6) for p in posts], [7 - 1.04, 7 + 1.04]); self.assertTrue(all(abs(p["c"][1] + p["h"][1] - 2.28) < 1e-9 and p["c"][1] - p["h"][1] == 0 for p in posts))
        self.assertAlmostEqual(beam["c"][1] + beam["h"][1], 2.4); self.assertAlmostEqual(beam["h"][0], 1.1); self.assertAlmostEqual(beam["c"][1] - beam["h"][1], 2.28)
        seat = objs[1]["prims"][0]; self.assertTrue(abs(seat["c"][0] - 7) + seat["h"][0] < 1.04 - 0.06)        # the seat hangs between the posts
        import shapes
        self.assertEqual(shapes.support(objs, 1), (0.5, None))             # and is not taken to stand on the frame
        tiny = made(park({"label": "gate", "shape": "arch", "size": [0.1, 99], "place": {"wall": "back", "along": 0}}))[1][0]
        lo = min(p["c"][0] - p["h"][0] for p in tiny["prims"]); hi = max(p["c"][1] + p["h"][1] for p in tiny["prims"])
        self.assertGreaterEqual(lo, -1e-9); self.assertAlmostEqual(hi, 6); self.assertIn("yaw", tiny)
    def test_effects(self):
        e = [{"type": "wander", "label": "x" * 50, "at": [2, -1], "radius": 99, "height": [9, 1], "count": 999, "size": 9, "speed": 99, "colours": ["#D8A520", "red", 5, "#12345"], "sound": "hum"},
             {"type": "drift", "at": "here", "count": 1, "size": 0, "fall": 9, "radius": 0},
             {"type": "snow"}, "leaves", {"type": "drift", "count": 5000, "fall": -1, "sound": "chirp"}, {"type": "wander", "count": 0, "radius": 0, "speed": 0, "size": 0}, {"type": "wander"}]
        info = made(park(piece(), effects=e))[2]; f = info["effects"]; self.assertEqual(len(f), 4)
        self.assertEqual(f[0], {"type": "wander", "label": "x" * 30, "at": [14, 0], "radius": 6, "height": [6, 6.1], "count": 40, "size": 0.3, "speed": 4, "colours": ["#d8a520"], "sound": "buzz"})
        self.assertEqual(f[1], {"type": "drift", "label": "drift", "at": [7, 6], "radius": 0.3, "height": [0, 6], "count": 10, "size": 0.01, "fall": 2, "colours": ["#777777"], "sound": "none"})
        self.assertEqual((f[2]["count"], f[2]["fall"], f[2]["sound"]), (400, -1, "chirp")); self.assertEqual((f[3]["count"], f[3]["radius"], f[3]["speed"], f[3]["size"]), (1, 0.3, 0.2, 0.01))
        self.assertNotIn("effects", made(park(piece(), effects={"type": "wander"}))[2])
        g = made(park(piece(), effects=[{"type": "drift", "fall": 0.5, "rise": True, "glow": True, "opacity": 9}, {"type": "wander", "glow": "yes", "opacity": 0.4}, {"type": "drift", "fall": -9, "glow": False}]))[2]["effects"]
        self.assertEqual([(e.get("fall"), e.get("glow"), e.get("opacity")) for e in g], [(-0.5, True, 1), (None, None, 0.4), (-2, False, None)])      # sparks rise; what glows is said, not guessed
        room, objs, info = made({"room": {"width": 4, "depth": 4, "height": 2.6}, "pieces": [piece()], "effects": [{"type": "drift"}], "mood": {"feel": "odd", "time": "night"}})
        self.assertEqual(info["wind"], {"strength": 0.2, "from": 270}); self.assertEqual(info["mood"], {"energy": 0.5, "time": "night"}); self.assertEqual(info["effects"][0]["height"], [0, 2.6])

WORLDS = os.path.join(THREAD, "worlds")
def chisel(world, code, views=12, **env):
    """Run code in a fresh interpreter with chisel_ring imported as C for the world folder."""
    r = subprocess.run([sys.executable, "-c", "import chisel_ring as C, json, numpy as np\n" + code], cwd=THREAD, capture_output=True, text=True,
                       env={**{k: v for k, v in os.environ.items() if k != "WORLD_RELIEF"}, "WORLD_DIR": world, "WORLD_VIEWS": str(views), **env})
    if r.returncode: raise AssertionError(r.stderr[-2000:])
    return r.stdout

class Painting(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)
    def world(self, layout, **more):
        room, objs, info = made(layout)
        with open(f"{self.tmp}/boxes.json", "w") as h: json.dump({"request": "", "room": room, "objects": objs, **info, **more}, h)
        return info
    def test_indoor_interface(self):
        self.world(OLD["chapel"][0])
        out = json.loads(chisel(self.tmp, "sid = C.surfaces(0)[1]\nprint(json.dumps([C.OUT, C.MARGIN, C.SURROUND, C.LIFT, [list(map(float, v)) for v in C.B.ROOM], C.view_prompt(0, 'x'), bool(C.halo(sid).any()), int(C.halo(sid, also=range(7), px=49).sum()), int(C.halo(sid, also=range(7)).sum()), int(C.halo(sid, also=range(7), px=48).sum())]))"))
        self.assertEqual(out[:5], [False, 0, "", [], [[0, 0, 0], [8, 5, 12]]]); self.assertTrue(out[5].startswith("interior photo, x. "))
        self.assertFalse(out[6]); self.assertGreater(out[7], out[8]); self.assertGreater(out[8], 0); self.assertEqual(out[9], out[7])     # no shapes: no halo unless asked; an even width is made odd
    def test_outdoor_interface_and_depth(self):
        info = self.world(park(piece(size=[2, 5, 2], place={"wall": "back", "along": 0.5}, motion={"type": "sway"}), piece(size=[0.5, 0.1, 0.25], base=0.5, motion={"type": "swing", "pivot": 2.3}),
                               piece(size=[1.8, 1.5, 4.5], motion={"type": "path", "points": [[0.1, 0.1], [0.9, 0.1]]}), surround='distant "hills"'),
                          motions_extra=1)
        self.assertEqual([m["type"] for m in info["motions"]], ["sway", "swing", "path"])
        out = json.loads(chisel(self.tmp, """C.prep()
from PIL import Image
z = np.load(C.D + '/depth/00.npz'); g = np.asarray(Image.open(C.D + '/depth/00.png').convert('L')); far = np.isin(z['sid'], C.BACKDROP)
t, sid, _ = C.surfaces(0)
print(json.dumps([C.OUT, C.MARGIN, C.SURROUND, C.LIFT, [list(map(float, v)) for v in C.B.ROOM], float(far.mean()), int(g[far].max()), int(g[~far].min()), int(g[~far].max()), float(z['t'][far].min()),
                  C.view_prompt(0, 'x'), [C.view_prompt(i, 'x').count('Beyond') for i in range(C.N)], [float(np.abs(np.array(e)[[0, 2]] - [7, 6]).max()) for e, _ in C.B.CAMS.values()]]))""", 8).splitlines()[-1])
        self.assertEqual(out[:5], [True, 20, "distant hills", [1, 2], [[-20, 0, -20], [34, 20, 32]]])
        self.assertGreater(out[5], 0.2); self.assertEqual(out[6], 0); self.assertGreater(out[7], 0); self.assertEqual(out[8], 255); self.assertGreater(out[9], 15)   # backdrop black, ground not; the saved depth is the shell's
        self.assertTrue(out[10].startswith("outdoor photo, x. In view: thing.")); self.assertTrue(out[10].endswith(" Beyond: distant hills, under an open sky."))
        self.assertEqual(out[11][:8], [1] * 8); self.assertTrue(all(d < 7 for d in out[12]))            # cameras stay on the play area
    def test_lift_ignores_bad_motions(self):
        self.world(OLD["chapel"][0], motions=[{"i": 1, "type": "spin"}, {"i": 99, "type": "spin"}, {"i": "2", "type": "bob"}, {"i": 0, "type": "sway"}, "x", {"i": 3, "type": "bob"}, {"i": 1, "type": "path"}])
        self.assertEqual(json.loads(chisel(self.tmp, "print(json.dumps(C.LIFT))")), [1, 3])
    def test_thin_gaps_in_carried_paint_are_closed(self):
        self.world(OLD["chapel"][0])
        out = json.loads(chisel(self.tmp, """t, sid, _ = C.surfaces(0); f = np.bincount(sid[sid < 6]).argmax(); ys, xs = np.nonzero(sid == f); x = int(np.median(xs))
have = sid == f; have[:, x - 15:x + 15] = False; have[:, x + 200:x + 320] = False; col = np.full(sid.shape + (3,), 90, np.float32); col[:, x:] = 150
h, c = C.mend(have.copy(), col.copy(), sid); thin = (sid == f) & ~have; thin[:, x + 200:] = False; wide = (sid == f) & ~have & ~thin
print(json.dumps([float(h[thin].mean()), float(h[wide].mean()), bool((h | (sid == f) == (sid == f)).all()), bool((c[have] == col[have]).all()), float(c[h & thin].min()), float(c[h & thin].max()),
                  bool((C.mend(have.copy(), col.copy(), sid, 1)[0] == have).all())]))"""))
        self.assertGreater(out[0], 0.8); self.assertLess(out[1], 0.2)                # the 30 px gap is closed (but for the margin at silhouettes), the 120 px one is left to the painter
        self.assertTrue(out[2] and out[3] and out[6]); self.assertGreaterEqual(out[4], 85); self.assertLessEqual(out[5], 155)      # only on that face; paint that was there is untouched; the gap takes its neighbours' paint
    def test_gap_closing_does_not_reach_round_the_picture(self):
        self.world(OLD["chapel"][0])
        out = json.loads(chisel(self.tmp, """sid = np.zeros((C.B.H, C.B.W), np.int64); have = np.zeros(sid.shape, bool); have[:, 20:60] = True; have[:, -30:] = True
col = np.zeros(sid.shape + (3,), np.float32); col[:, 20:60] = [0, 200, 0]; col[:, -30:] = [200, 0, 0]
h, c = C.mend(have, col, sid); print(json.dumps([float(c[:, :20, 0].max()), float(c[:, :20, 1].min()), float(h[:, :20].mean())]))"""))
        self.assertEqual(out[0], 0); self.assertGreater(out[1], 150); self.assertEqual(out[2], 1)        # the gap at the left edge takes the green beside it, none of the red at the right edge
    def test_cameras_keep_clear_of_posts(self):
        cams = "print(json.dumps([C.NEW, C.SLIM, [[float(v) for v in e] for e, _ in C.B.CAMS.values()], [[x, z, d] for x, z, d in C.POSTS], C.N, C.RING]))"
        near = lambda eyes, posts: min(math.hypot(e[0] - x, e[2] - z) for e in eyes for x, z, _ in posts)
        layout = swap(GOOD, "bench", piece(label="lamp post", shape="cylinder", size=[0.1, 4], place={"at": [0.82, 0.5]}))
        self.world(layout); new, slim, old, posts, n, ring = json.loads(chisel(self.tmp, cams))
        self.assertEqual((new, slim, n, ring), (False, [2, 5], 18, 12)); self.assertEqual([d for _, _, d in posts], [2.4, 2.4, 1.6])
        self.assertLess(near(old, posts), 0.7)                                                           # as worlds were painted until now: right beside a post
        self.world(layout, rules=2); new, _, eyes, posts, n, _ = json.loads(chisel(self.tmp, cams)); self.assertTrue(new); self.assertEqual(n, 18)
        for e in eyes: self.assertTrue(all(math.hypot(e[0] - x, e[2] - z) >= d - 1e-9 for x, z, d in posts), e)
        self.assertTrue(all(0.3 < e[0] < 13.7 and 0.3 < e[2] < 11.7 for e in eyes))
        self.assertGreater(min(math.dist(a[::2], b[::2]) for k, a in enumerate(eyes[:12]) for b in eyes[:k]), 1.0)     # and not on top of each other
        same = sum(math.dist(a, b) < 1e-9 for a, b in zip(old, eyes)); self.assertGreaterEqual(same, 9); self.assertLess(same, 18)      # the rest stay where they were
        hall = {"room": {"width": 5, "depth": 4, "height": 2.6}, "pieces": [piece(label="coat stand", shape="cylinder", size=[0.08, 1.8], place={"at": [0.5, 0.5]}), piece(shape="sofa", place={"wall": "back", "along": 0.5})]}
        self.world(hall, rules=2); _, _, eyes, posts, n, _ = json.loads(chisel(self.tmp, cams)); self.assertEqual(n, 16)       # a post in the middle of a small room: every view still has a camera
        self.assertEqual(posts, [[2.5, 2.0, 1.2]]); self.assertGreaterEqual(near(eyes, posts), 0.6 - 1e-9)
    def test_grounds_reach_the_painter(self):
        code = """C.prep()
import hashlib
st = json.load(open(C.D + '/depth/start.json'))
print(json.dumps([[g[0] for g in C.GROUNDS], [C.view_prompt(i, 'x') for i in range(C.N)], [hashlib.md5(open(C.D + '/depth/%02d.' % i + e, 'rb').read()).hexdigest() for i in range(C.N) for e in ('png', 'npy')],
                  st, [list(map(float, v)) for v in C.B.CAMS[str(st['view'])]], C.RELIEF]))"""
        lawn = piece(label="lawn_1", shape="ground", size=[14, 12], place={"at": [0.5, 0.5]})
        self.world({**GOOD, "pieces": GOOD["pieces"] + [lawn]}, rules=2); names, prompts, sums, st, cam, relief = json.loads(chisel(self.tmp, code).splitlines()[-1])
        self.assertEqual((names, relief), (["lawn", "road", "flower bed"], 0.12)); self.assertEqual([st["eye"], st["look"]], cam); self.assertLess(st["view"], 12)
        self.assertTrue(all(p.startswith("outdoor photo, x. In view: ") for p in prompts))
        road = [p for p in prompts if " On the ground: " in p and "road " in p]; self.assertGreaterEqual(len(road), 4)
        self.assertTrue(all(" The rest of the ground is lawn, plain and unbroken." in p for p in road)); self.assertTrue(any("road across the " in p for p in road))
        self.assertTrue(any(" The ground is lawn, plain and unbroken." in p for p in prompts)); self.assertTrue(any("flower bed on the " in p for p in prompts))
        self.assertTrue(all(p.endswith("nder an open sky.") or p.endswith("unbroken.") for p in prompts))
        self.world(GOOD, rules=2, grounds="road"); names, bare, sums0, *_ = json.loads(chisel(self.tmp, code).splitlines()[-1])      # the same world, its grounds not told
        self.assertEqual(names, []); self.assertFalse(any("On the ground" in p or "lawn" in p for p in bare)); self.assertTrue(any(p.endswith(" The ground is plain and unbroken.") for p in bare))
        self.assertEqual(sums[1::2], sums0[1::2]); self.assertGreaterEqual(sum(a != b for a, b in zip(sums[::2], sums0[::2])), 4)   # only the painter's guide differs: the saved geometry is the flat ground
        self.world({**GOOD, "pieces": GOOD["pieces"] + [lawn]}, rules=2); self.assertEqual(json.loads(chisel(self.tmp, code, WORLD_RELIEF="0").splitlines()[-1])[2], sums0)
        room = {"room": {"width": 5, "depth": 4, "height": 2.6}, "pieces": [piece(shape="sofa", place={"wall": "back", "along": 0.5}), piece(label="rug", shape="ground", size=[2, 1.5], place={"at": [0.5, 0.4]})]}
        self.world(room); names, prompts, _, _, _, relief = json.loads(chisel(self.tmp, code).splitlines()[-1])
        self.assertEqual((names, relief), (["rug"], -0.03)); self.assertTrue(any(" On the floor: rug " in p for p in prompts)); self.assertFalse(any("unbroken" in p for p in prompts))
    @unittest.skipUnless(os.path.exists(f"{WORLDS}/garage-shapes/depth/00.png"), "the garage-shapes world is not on this Mac")
    def test_garage_depth_unchanged(self):
        src = f"{WORLDS}/garage-shapes"; shutil.copy(f"{src}/boxes.json", self.tmp); shutil.copytree(f"{src}/shapes", f"{self.tmp}/shapes")
        self.assertIn("depth maps 18", chisel(self.tmp, "C.prep()"))
        def md5(f):
            with open(f, "rb") as h: return hashlib.md5(h.read()).hexdigest()
        for i in range(18): self.assertEqual(md5(f"{self.tmp}/depth/{i:02d}.png"), md5(f"{src}/depth/{i:02d}.png"), i)

if __name__ == "__main__":
    unittest.main()
