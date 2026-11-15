"""Writes every hat: model, item file, texture, recipe, name, and the handbook page.  Run: python tools/hats.py

A hat is a list of boxes in model units, each of a material that paints its own texture (straw weave, felt grain,
knit ribs...), plus small pixel drawings ("decals") on chosen faces. Two texels per unit.

How a hat must be built:
- centred on x = z = 8, standing on y = 0 and never below it, north (-z) is the face side;
- on a player the hat is pulled HEAD_TOP units (3 pixels) down over the head, 12.8 units wide; the skin's outer
  layer is 14.4 wide and rises BAND_TOP high, and must not show through. So the hat's band (the boxes from y = 0
  that cover the square from 0.8 to 15.2) must reach BAND_TOP: where it falls short, fit() stretches the hat at the
  band's top, moving everything above up. What sits on the head rather than over it (a halo, a chicken) has no
  band, and stays perched on top as before;
- on a drone it stands on the tank at 0.27 pixels per unit, with every module below it.
"""
import json
import math
import re
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src/main/resources/assets/cyberhats"
DATA = ROOT / "src/main/resources/data/cyberhats"
# Each branch builds one Minecraft version; 1.20.1 has its own file formats, handbook and rotation limits
MC = next(line.split("=", 1)[1].strip() for line in (ROOT / "gradle.properties").read_text().splitlines()
          if line.startswith("minecraft_version="))
LEGACY = MC == "1.20.1"
RES = 2
HATS = []
FACES = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}
STITCH = (58, 42, 32)
PANELS = ["#d22b2b", "#f2c318", "#2b4bbd", "#2e8b3d"]
PARTY = ["#ff5fa2", "#3fc6e8", "#ffd23f"]


class Hat:
    def __init__(self, name, title, recipe):
        self.name, self.title, self.recipe = name, title, recipe
        self.boxes = []    # (bounds, material, rotation, faces, tag, part)
        self.decals = []   # (tag, face, column, row, art, colours)
        self.motions = {}  # part: (pivot, [(kind, axis, amount, period, phase)])
        HATS.append(self)

    def box(self, x0, y0, z0, x1, y1, z1, material, rot=None, faces="nsewud", tag=None, part=None):
        """rot: (axis, degrees, origin). material None: see-through, for a face that only carries a decal.
        part: the moving part the box belongs to (see move); without one it stands still."""
        if rot and LEGACY:
            # 1.20.1 only turns an element by a multiple of 22.5 degrees, up to 45
            angle = max(-45.0, min(45.0, round(rot[1] / 22.5) * 22.5))
            rot = (rot[0], angle, rot[2]) if angle else None
        self.boxes.append(((x0, y0, z0, x1, y1, z1), material, rot, faces, tag, part))

    def mid(self, width, depth, y0, y1, material, dx=0.0, dz=0.0, **more):
        """A box centred on the hat's axis, or dx / dz off it."""
        self.box(8 + dx - width / 2, y0, 8 + dz - depth / 2, 8 + dx + width / 2, y1, 8 + dz + depth / 2, material, **more)

    def brim(self, size, y0, y1, material):
        """A brim with its corners cut, as round as boxes get."""
        cut = round(size * 0.72 * 2) / 2
        self.mid(size, cut, y0, y1, material)
        self.mid(cut, size, y0, y1, material)
        self.mid(round(size * 0.9 * 2) / 2, round(size * 0.9 * 2) / 2, y0, y1, material)

    def move(self, part, pivot, *motions):
        """How a part moves around its pivot (model units), drawn by the game's code instead of the still model.
        Each motion is (kind, axis, amount, period in seconds, phase from 0 to 1):
        swing: turns back and forth by amount degrees; spin: turns all the way round once a period;
        bob: slides back and forth by amount units; blink: shrinks flat along the axis for a moment once a period."""
        self.motions[part] = (pivot, list(motions))

    def decal(self, tag, face, column, row, art, **colours):
        """art: rows of characters, each a colour name from `colours`; a dot leaves the texel alone."""
        self.decals.append((tag, face, column, row, art.split(), colours))


def shaped(*pattern, **key):
    return {"type": "minecraft:crafting_shaped", "category": "equipment", "key": key, "pattern": list(pattern)}


def shapeless(*ingredients):
    return {"type": "minecraft:crafting_shapeless", "category": "equipment", "ingredients": list(ingredients)}


def legacy_recipe(hat):
    """The same recipe in 1.20.1's format, where every item is {"item": id}."""
    recipe = dict(hat.recipe)
    if "key" in recipe:
        recipe["key"] = {k: {"item": v} for k, v in recipe["key"].items()}
    else:
        recipe["ingredients"] = [{"item": v} for v in recipe["ingredients"]]
    return {**recipe, "result": {"item": f"cyberhats:{hat.name}"}}


# ------------------------------------------------------------------ textures

def rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def grain(*key):
    return (zlib.crc32(repr(key).encode()) & 0xFFFF) / 0xFFFF


def corners(face, bounds):
    """Texture top-left, top-right and bottom-left of a face, as Minecraft maps a uv rectangle onto it."""
    x0, y0, z0, x1, y1, z1 = bounds
    return {
        "north": ((x1, y1, z0), (x0, y1, z0), (x1, y0, z0)),
        "south": ((x0, y1, z1), (x1, y1, z1), (x0, y0, z1)),
        "west": ((x0, y1, z0), (x0, y1, z1), (x0, y0, z0)),
        "east": ((x1, y1, z1), (x1, y1, z0), (x1, y0, z1)),
        "up": ((x0, y1, z0), (x1, y1, z0), (x0, y1, z1)),
        "down": ((x0, y0, z1), (x1, y0, z1), (x0, y0, z0)),
    }[face]


def texel(material, face, point, i, j, w, h):
    """One texel's colour. Patterns follow the texel's place in the model, so they run on from box to box."""
    if material is None:
        return (0, 0, 0, 0)
    colour, pattern = material
    x, y, z = point
    qx, qy, qz = (math.floor(v * RES + 1e-6) for v in point)
    side = face not in ("up", "down")
    # Along the face and across it, in texels
    along, across = (qx if face in ("north", "south") else qz, qy) if side else (qx, qz)
    noise = grain(qx, qy, qz)
    k = 0.95 + 0.08 * noise
    # A light line under the top edge: the sheen of something hard
    sheen = side and j == 1 and h > 3
    if pattern == "felt":
        k = 0.9 + 0.16 * noise
    elif pattern == "plastic":
        k = 0.98 + 0.03 * noise + (0.12 if sheen else 0.0)
    elif pattern == "straw":
        if side:
            ring, run = qy, along
        else:
            ring = math.floor(max(abs(x - 8), abs(z - 8)) * RES)
            run = qx if abs(z - 8) > abs(x - 8) else qz
        k = (1.0 if ring % 2 else 0.86) * (0.88 if (run + 2 * ring) % 4 == 0 else 1.0) * (0.96 + 0.06 * noise)
    elif pattern == "knit":
        k = (0.9 if along % 2 else 1.0) * (0.96 + 0.06 * noise)
    elif pattern == "tweed":
        weave = along + across if (along // 3) % 2 else along - across
        k = (0.82 if weave % 3 == 0 else 1.0) * (0.92 + 0.14 * noise)
    elif pattern == "leather":
        k = 0.93 + 0.1 * noise
        if w >= 8 and h >= 8 and 1 <= i <= w - 2 and 1 <= j <= h - 2 and (i in (1, w - 2) or j in (1, h - 2)) and (i + j) % 3:
            return STITCH + (255,)
    elif pattern == "beads":
        k = (1.2 if along % 2 == 0 else 0.7) * (0.85 if side and j == 0 else 1.0)
    elif pattern == "fur":
        k = 0.86 + 0.16 * noise
    elif pattern == "metal":
        k = 0.9 + 0.08 * noise + (0.16 if sheen else 0.0)
    elif pattern == "rivets":
        k = 0.92 + 0.08 * noise
        if side and j == h // 2 and along % 5 == 0:
            return (222, 200, 130, 255)
    elif pattern == "gold":
        k = 0.88 + 0.12 * noise + (0.22 if sheen else 0.0)
    elif pattern == "pleat":
        k = (0.86 if side and along % 3 == 0 else 1.0) * (0.97 + 0.04 * noise)
    elif pattern == "panels":
        turn = (math.atan2(z - 8, x - 8) + math.pi) / (2 * math.pi)
        colour = PANELS[math.floor(turn * 8 + 0.5) % 4]
        k = 0.92 + 0.12 * noise
    elif pattern == "zigzag":
        # Mexican band: red, with green and white teeth along it
        tooth = abs(along % 6 - 3)
        colour = "#2e8b3d" if j < tooth - 0.5 else "#f4f1e6" if j == h - 1 else colour
        k = 0.94 + 0.08 * noise
    elif pattern == "party":
        colour = PARTY[((along + across) // 3) % 3]
        k = 0.96 + 0.06 * noise
    elif pattern == "spots":
        a, b = (along, across) if side else (qx, qz)
        cell = (a // 6, b // 6, face)
        # A round 4x4 dot (corners left out) in some of the 6x6 cells
        spot = grain(*cell) > 0.5 and 1 <= a % 6 <= 4 and 1 <= b % 6 <= 4 and not (a % 6 in (1, 4) and b % 6 in (1, 4))
        colour = "#f6f1e4" if spot else colour
        k = 0.94 + 0.08 * noise
    elif pattern == "lames":
        # Lacquered plates laced with red cord
        if j % 3 == 2 or (j % 3 == 1 and along % 4 == 0):
            return rgb("#a52a24") + (255,)
        k = 0.9 + 0.1 * noise + (0.14 if j % 3 == 0 else 0.0)
    elif pattern == "glow":
        k = 1.0
    if side and h >= 4 and j == h - 1:
        k *= 0.88   # shadow where a part meets the one below
    return tuple(max(0, min(255, round(c * k))) for c in rgb(colour)) + (255,)


def turned(point, rot):
    """A point after the element's rotation, as Minecraft turns it."""
    if rot is None:
        return point
    axis, degrees, origin = rot
    x, y, z = (point[n] - origin[n] for n in range(3))
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    x, y, z = {"x": (x, y * c - z * s, y * s + z * c), "y": (x * c + z * s, y, -x * s + z * c), "z": (x * c - y * s, x * s + y * c, z)}[axis]
    return (x + origin[0], y + origin[1], z + origin[2])


# A wrapping hat comes down 3 pixels over the head, 4.8 units at the head's 0.625 pixels per unit; one with no band
# sits 1.5 pixels down, on top of it. The "head" display translation that puts each there, in model units.
HEAD_TOP = 4.8
# The skin's outer layer stands half a pixel proud of the head, 0.8 units at that scale; the band a hair above it,
# so the two never share a plane and flicker
BAND_TOP = HEAD_TOP + 0.9
WRAP_TRANSLATION, PERCH_TRANSLATION = 9.6, 12
HEAD = (0.8, 15.2)


def fit(hat):
    """Whether the hat wraps the head. If its band ends below BAND_TOP, the hat is stretched at that height: what is
    above moves up, what reaches it grows, so the band reaches BAND_TOP and the rest of the hat keeps its shape."""
    # The outline of the head's outer layer, as points every 0.8 units around it
    rim = [(a, b) for a in (HEAD[0], HEAD[1]) for b in [HEAD[0] + i * 0.8 for i in range(19)]]
    rim += [(b, a) for a, b in rim]

    def wrapped(y):
        """Whether the still boxes, together, go all the way round the head at this height."""
        here = [box[0] for box in hat.boxes if not box[2] and not box[5] and box[0][1] <= y < box[0][4]]
        return all(any(b[0] <= x <= b[3] and b[2] <= z <= b[5] for b in here) for x, z in rim)

    if not wrapped(0.05):
        return False
    # The band's top: the lowest height where something it is made of ends and the head would show
    reached = min(y for y in sorted({box[0][4] for box in hat.boxes}) if y > 0 and not wrapped(y + 1e-3))
    if reached >= BAND_TOP - 1e-6:
        return True
    rise = BAND_TOP - reached

    def lift(y):
        return y + rise if y >= reached - 1e-6 else y

    for i, (bounds, material, rot, faces, tag, part) in enumerate(hat.boxes):
        x0, y0, z0, x1, y1, z1 = bounds
        if rot:
            rot = (rot[0], rot[1], (rot[2][0], lift(rot[2][1]), rot[2][2]))
        hat.boxes[i] = ((x0, lift(y0), z0, x1, y1 + rise if y1 >= reached - 1e-6 else y1, z1), material, rot, faces, tag, part)
    for part, (pivot, motions) in hat.motions.items():
        hat.motions[part] = ((pivot[0], lift(pivot[1]), pivot[2]), motions)
    return True


def build(hat):
    """(model elements, texture rows, texture size, the hat's bounds)."""
    hat.wraps = fit(hat)
    faces = []   # (box index, face, width, height, pixels)
    assert {b[5] for b in hat.boxes if b[5]} == set(hat.motions), f"{hat.name}: every part needs one move and a box"
    for index, (bounds, material, rot, sides, tag, part) in enumerate(hat.boxes):
        x0, y0, z0, x1, y1, z1 = bounds
        assert x0 < x1 and y0 < y1 and z0 < z1 and min(bounds) >= -16 and max(bounds) <= 32, f"{hat.name}: bad box {bounds}"
        # Under the hat are the player's face and the drone's modules
        lowest = min(turned((x, y, z), rot)[1] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1))
        assert lowest >= -1e-6, f"{hat.name}: box {bounds} goes below the hat's bottom"
        for letter in sides:
            face = FACES[letter]
            tl, tr, bl = corners(face, bounds)
            w = max(1, round(math.dist(tl, tr) * RES))
            h = max(1, round(math.dist(tl, bl) * RES))
            pixels = [[texel(material, face, [tl[n] + (tr[n] - tl[n]) * (i + 0.5) / w + (bl[n] - tl[n]) * (j + 0.5) / h for n in range(3)],
                             i, j, w, h) for i in range(w)] for j in range(h)]
            for where, on, column, row, art, colours in hat.decals:
                if where == tag and on == face:
                    for dj, line in enumerate(art):
                        for di, char in enumerate(line):
                            if char != ".":
                                assert row + dj < h and column + di < w, f"{hat.name}: decal on {tag} leaves its face"
                                pixels[row + dj][column + di] = rgb(colours[char]) + (255,)
            faces.append((index, face, w, h, pixels))
    assert {d[0] for d in hat.decals} <= {b[4] for b in hat.boxes}, f"{hat.name}: decal without its box"

    # Shelf packing, tallest first
    size = 64
    while True:
        rows = [[(0, 0, 0, 0)] * size for _ in range(size)]
        placed, x, y, shelf = {}, 0, 0, 0
        for index, face, w, h, pixels in sorted(faces, key=lambda f: -f[3]):
            if x + w > size:
                x, y, shelf = 0, y + shelf, 0
            if y + h > size or w > size:
                break
            for j in range(h):
                rows[y + j][x:x + w] = pixels[j]
            placed[index, face] = (x, y, w, h)
            x, shelf = x + w, max(shelf, h)
        else:
            break
        size *= 2

    elements = []
    hat.quads, hat.bright = {}, set()
    for index, (bounds, material, rot, sides, tag, part) in enumerate(hat.boxes):
        if part:
            hat.quads.setdefault(part, []).extend(part_quads(bounds, rot, sides, placed, index, size))
            if material and material[1] == "glow":
                hat.bright.add(part)
            continue
        element = {"from": list(bounds[:3]), "to": list(bounds[3:]), "faces": {}}
        if rot:
            element["rotation"] = {"origin": list(rot[2]), "axis": rot[0], "angle": rot[1]}
        if material and material[1] == "glow":
            if LEGACY:
                element["forge_data"] = {"block_light": 15, "sky_light": 15}
            else:
                element["light_emission"] = 15
        for letter in sides:
            x, y, w, h = placed[index, FACES[letter]]
            # A hair inside the rectangle, so its neighbours never bleed in
            uv = [(x + 0.02) * 16 / size, (y + 0.02) * 16 / size, (x + w - 0.02) * 16 / size, (y + h - 0.02) * 16 / size]
            element["faces"][FACES[letter]] = {"uv": [round(v, 4) for v in uv], "texture": "#hat"}
        elements.append(element)
    for part, quads in hat.quads.items():
        check_motion(hat, part, quads)
    low = [min(b[0][n] for b in hat.boxes) for n in range(3)]
    high = [max(b[0][n + 3] for b in hat.boxes) for n in range(3)]
    return elements, rows, size, (low, high)


NORMALS = {"north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}


def part_quads(bounds, rot, sides, placed, index, size):
    """A moving box as the game's code draws it: per face, four corners (x, y, z, u, v) and the normal.
    Positions in model units, already turned by the box's own rotation; uv from 0 to 1 on the hat's texture."""
    quads = []
    for letter in sides:
        face = FACES[letter]
        tl, tr, bl = corners(face, bounds)
        br = tuple(tr[n] + bl[n] - tl[n] for n in range(3))
        x, y, w, h = placed[index, face]
        u0, v0, u1, v1 = (x + 0.02) / size, (y + 0.02) / size, (x + w - 0.02) / size, (y + h - 0.02) / size
        normal = NORMALS[face]
        if rot:
            # The rotation turns a direction as it turns a point about the origin
            origin = turned((0, 0, 0), (rot[0], rot[1], (0, 0, 0)))
            tip = turned(normal, (rot[0], rot[1], (0, 0, 0)))
            normal = tuple(tip[n] - origin[n] for n in range(3))
        quad = []
        for corner, u, v in ((tl, u0, v0), (bl, u0, v1), (br, u1, v1), (tr, u1, v0)):
            quad += [*turned(corner, rot), u, v]
        quads.append([round(value, 5) for value in quad + list(normal)])
    return quads


def moved(point, pivot, motions, t):
    """Where a point of a moving part is at time t, as the game's code moves it (HatParts.java)."""
    x, y, z = (point[n] - pivot[n] for n in range(3))
    for kind, axis, amount, period, phase in motions:
        cycle = t / period + phase
        if kind in ("swing", "spin"):
            angle = math.radians(amount * math.sin(2 * math.pi * cycle) if kind == "swing" else 360 * cycle)
            c, s = math.cos(angle), math.sin(angle)
            x, y, z = {"x": (x, y * c - z * s, y * s + z * c), "y": (x * c + z * s, y, -x * s + z * c),
                       "z": (x * c - y * s, x * s + y * c, z)}[axis]
        elif kind == "bob":
            offset = amount * math.sin(2 * math.pi * cycle)
            x, y, z = x + offset * (axis == "x"), y + offset * (axis == "y"), z + offset * (axis == "z")
    return (x + pivot[0], y + pivot[1], z + pivot[2])


def parts_data(hat):
    """A hat's moving parts as the game reads them: pivot, motions and quads, and whether they glow."""
    return [{"pivot": list(pivot), "bright": part in hat.bright, "quads": hat.quads[part],
             "motions": [{"kind": kind, "axis": axis, "amount": amount, "period": period, "phase": phase}
                         for kind, axis, amount, period, phase in motions]}
            for part, (pivot, motions) in hat.motions.items()]


def check_motion(hat, part, quads):
    """A moving part must stay above the hat's bottom all through its motion, like the still boxes."""
    pivot, motions = hat.motions[part]
    for kind, axis, amount, period, phase in motions:
        assert kind in ("swing", "spin", "bob", "blink") and axis in "xyz" and period > 0, f"{hat.name}: bad motion {kind}"
    for step in range(48):
        t = step / 48 * max(m[3] for m in motions)
        for quad in quads:
            for corner in range(4):
                y = moved(quad[corner * 5:corner * 5 + 3], pivot, motions, t)[1]
                assert y >= -1e-6, f"{hat.name}: part {part} goes below the hat's bottom"


# ------------------------------------------------------------------ the hats

def hard_hat():
    h = Hat("hard_hat", "Hard Hat", shaped("III", "IYI", I="minecraft:iron_ingot", Y="minecraft:yellow_dye"))
    yellow = ("#f2c318", "plastic")
    h.mid(16.5, 16.5, 0, 1, yellow)                    # rim
    h.box(2.5, 0, -3.5, 13.5, 1, -0.25, yellow)        # peak
    h.mid(15, 15, 1, 4.5, yellow)
    h.mid(14, 14, 4.5, 6, yellow)
    h.mid(12.5, 12.5, 6, 7.25, yellow)
    h.mid(10, 10, 7.25, 8.25, yellow)
    # Three ridges, front to back, stepping down with the dome
    for length, y in ((10, 8.25), (12.5, 7.25), (14, 6)):
        h.mid(2, length, y, y + 0.75, yellow)
        h.mid(1, length, y, y + 0.5, yellow, dx=-3.5)
        h.mid(1, length, y, y + 0.5, yellow, dx=3.5)


STAR = "..W.. .WWW. WWWWW .WWW. .W.W."
SPARK = ".W. WWW .W."


def wizard_hat():
    h = Hat("wizard_hat", "Wizard Hat", shaped(" G ", " W ", "WWW", G="minecraft:glowstone_dust", W="minecraft:blue_wool"))
    blue = ("#2b4bbd", "felt")
    h.brim(25, 0, 1, blue)
    h.mid(15, 15, 1, 5, blue, tag="c1")
    h.mid(12, 12, 5, 9, blue, tag="c2")
    h.mid(9, 9, 9, 13, blue, tag="c3")
    h.mid(6, 6, 13, 16.5, blue, tag="c4")
    h.mid(4, 4, 16.5, 19.5, blue, dz=1)                # the tip leans back...
    h.mid(3, 5, 18.5, 21, blue, dz=3.5)
    h.mid(2, 2.5, 16, 19, blue, dz=6.25)               # ...and turns down
    h.box(7.75, 13.5, 14, 8.25, 16, 14.5, ("#2a2a30", "cloth"), part="charm")   # string
    h.box(6.25, 10, 14.2, 9.75, 13.5, 14.3, None, faces="ns", tag="star", part="charm")
    h.move("charm", (8, 16, 14.25), ("swing", "x", 10, 1.8, 0), ("swing", "z", 5, 2.3, 0.2))
    gold = "...G... ...G... GGGGGGG .GGGGG. ..GGG.. .GG.GG. .G...G."
    h.decal("star", "north", 0, 0, gold, G="#e0b84a")
    h.decal("star", "south", 0, 0, gold, G="#e0b84a")
    white = {"W": "#eef0f6"}
    for face, shift in (("north", 0), ("east", 5), ("south", 2), ("west", 7)):
        h.decal("c1", face, 3 + shift, 1, STAR, **white)
        h.decal("c1", face, 14 + shift, 4, SPARK, **white)
        h.decal("c2", face, (9 + shift * 2) % 18, 2, STAR, **white)
        h.decal("c3", face, 3 + shift, 1, SPARK, **white)
        h.decal("c3", face, (10 + shift) % 13, 4, SPARK, **white)
        h.decal("c4", face, 2 + shift % 6, 2, SPARK, **white)


def flat_cap():
    h = Hat("flat_cap", "Flat Cap", shaped("WWW", "WL ", W="minecraft:gray_wool", L="minecraft:leather"))
    tweed = ("#4a4d54", "tweed")
    h.mid(15, 15, 0, 3.5, tweed)
    h.mid(15, 11.5, 3.5, 5, tweed, dz=1.75)            # higher at the back
    h.mid(15, 3.5, 3.5, 4.25, tweed, dz=-5.75)         # sloping to the front
    h.box(0.5, 1.5, -1, 15.5, 3.5, 0.5, tweed)         # the front, hanging over the peak
    h.box(2.5, 0, -3, 13.5, 0.75, 0.5, tweed)          # peak


def straw_hat():
    h = Hat("straw_hat", "Straw Hat", shaped("WWW", "WRW", W="minecraft:wheat", R="minecraft:red_carpet"))
    straw = ("#dfb65c", "straw")
    h.brim(27, 0, 0.75, straw)
    h.mid(15, 15, 0.75, 6, straw)
    h.mid(15.5, 15.5, 0.75, 2.75, ("#c9241f", "cloth"))   # band
    h.mid(14, 14, 6, 7.25, straw)
    h.mid(11.5, 11.5, 7.25, 8, straw)


def elf_cap():
    h = Hat("elf_cap", "Elf Cap", shaped("  W", " WW", "WWW", W="minecraft:green_wool"))
    green, cuff = ("#2e8b3d", "knit"), ("#256f31", "knit")
    h.mid(16, 16, 0, 3, cuff)
    h.mid(15, 15, 3, 6, green)
    h.mid(13, 13, 6, 8.5, green, dz=0.75)
    h.mid(10, 10, 8.5, 10.5, green, dz=2)
    h.mid(7, 7, 10, 12, green, dz=4)
    h.mid(5, 5, 8, 11.5, green, dz=7.5, part="tail")   # the tail falls behind the head
    h.mid(4, 4, 3.5, 9, green, dz=10, part="tail")
    h.mid(2.5, 2.5, 0.5, 4, green, dz=10, part="tail")
    h.move("tail", (8, 10.5, 11.5), ("swing", "z", 5, 2.6, 0))


def cowboy_hat():
    h = Hat("cowboy_hat", "Cowboy Hat", shaped("LLL", "LOL", L="minecraft:leather", O="minecraft:orange_dye"))
    orange = ("#e58a2e", "leather")
    h.mid(17, 26, 0, 0.75, orange)                     # brim, its two sides curled up
    h.box(16.5, 0, -4, 20.5, 0.75, 20, orange, rot=("z", 28, (16.5, 0, 8)))
    h.box(-4.5, 0, -4, -0.5, 0.75, 20, orange, rot=("z", -28, (-0.5, 0, 8)))
    h.mid(15, 15, 0.75, 5, orange)
    h.mid(15.5, 15.5, 1, 2, ("#c22a20", "beads"))
    h.mid(13, 14, 5, 7, orange)
    h.mid(4, 14, 7, 8, orange, dx=-4.5)                # pinched crown
    h.mid(4, 14, 7, 8, orange, dx=4.5)
    h.box(3.5, 2.25, 0.3, 7, 5.75, 0.5, None, faces="n", tag="smile")
    h.box(9, 2.25, 0.3, 12.5, 5.75, 0.5, None, faces="n", tag="frown")
    colours = {"W": "#f1f1ee", "B": "#27408f"}
    h.decal("smile", "north", 0, 0, "..WWW.. .WBBBW. WBWBWBW WBBBBBW WBWBWBW .WBWBW. ..WWW..", **colours)
    h.decal("frown", "north", 0, 0, "..WWW.. .WBBBW. WBWBWBW WBBBBBW WBBWBBW .WWBWW. ..WWW..", **colours)


def baseball_cap():
    h = Hat("baseball_cap", "Baseball Cap", shaped("WW ", "WWL", W="minecraft:red_wool", L="minecraft:leather"))
    red, peak = ("#d22b2b", "cloth"), ("#b92424", "cloth")
    h.mid(15, 15, 0, 4.5, red)
    h.mid(13.5, 13.5, 4.5, 6, red)
    h.mid(10.5, 10.5, 6, 7, red)
    h.mid(1.5, 1.5, 7, 7.5, red)                       # button
    h.box(2, 0, -5.5, 14, 0.75, 0.5, peak)
    h.box(3.5, 0, -6.5, 12.5, 0.75, -5.5, peak)
    h.box(5, 1.25, 0.3, 11, 4.25, 0.5, None, faces="n", tag="logo")
    h.decal("logo", "north", 0, 0, "...GGGGGG... .GGGGGGGGGG. YYYYYYYYYYYY YYYYYYYYYYYY .GGGGGGGGGG. ...GGGGGG...",
            G="#2e9a44", Y="#f2c318")


def top_hats():
    black = ("#1d1d22", "felt")
    for name, title, recipe in (
            ("top_hat", "Top Hat", shaped(" W ", " W ", "WRW", W="minecraft:black_wool", R="minecraft:red_dye")),
            ("goggle_top_hat", "Goggle Top Hat", shapeless("cyberhats:top_hat", "minecraft:glass_pane", "minecraft:glass_pane", "minecraft:blue_dye"))):
        h = Hat(name, title, recipe)
        h.brim(21, 0, 0.75, black)
        h.mid(15, 15, 0.75, 11, black)
        if name == "top_hat":
            h.mid(15.5, 15.5, 0.75, 2.75, ("#8a1a26", "cloth"))
            continue
        frame = ("#c9ced6", "metal")
        h.mid(15.5, 15.5, 2.25, 4.75, ("#1f3f8a", "cloth"))        # strap
        h.box(1.5, 1.5, -0.25, 7, 5.5, 0.5, frame, tag="lens")
        h.box(9, 1.5, -0.25, 14.5, 5.5, 0.5, frame, tag="lens")
        h.box(7, 3, 0, 9, 4, 0.5, frame)
        h.decal("lens", "north", 0, 0, ".FFFFFFFFF. FFLLLLLLLFF FLLHHLLLLLF FLLHLLLLLLF FLLLLLLLLLF FLLLLLLLLLF FFLLLLLLLFF .FFFFFFFFF.",
                F="#c9ced6", L="#2f63c9", H="#9cc0f5")


def plumber_caps():
    letters = {
        "M": "....WWWWWW.... ..WWWWWWWWWW.. .WWCWWWWWWCWW. WWWCCWWWWCCWWW WWWCCCWWCCCWWW WWWCWCCCCWCWWW"
             " WWWCWWCCWWCWWW WWWCWWWWWWCWWW .WWCWWWWWWCWW. ..WWWWWWWWWW.. ....WWWWWW....",
        "L": "....WWWWWW.... ..WWWWWWWWWW.. .WWWWCCWWWWWW. WWWWWCCWWWWWWW WWWWWCCWWWWWWW WWWWWCCWWWWWWW"
             " WWWWWCCWWWWWWW WWWWWCCCCCWWWW .WWWWCCCCCWWW. ..WWWWWWWWWW.. ....WWWWWW....",
    }
    for name, title, colour, wool, letter in (("red_plumber_cap", "Red Plumber Cap", "#de2424", "red", "M"),
                                              ("green_plumber_cap", "Green Plumber Cap", "#2ea63c", "green", "L")):
        h = Hat(name, title, shaped("WWW", "WD ", W=f"minecraft:{wool}_wool", D="minecraft:white_dye"))
        cloth = (colour, "cloth")
        h.mid(15, 15, 0, 3.5, cloth)
        h.mid(17, 16, 3.5, 6.5, cloth, dz=1)           # the puffy top
        h.mid(14, 13, 6.5, 7.5, cloth, dz=1)
        h.box(3, 0, -0.25, 13, 6.5, 1, cloth)          # front panel
        h.box(3, 0, -4, 13, 0.75, -0.25, cloth)        # peak
        h.box(4.5, 0.75, -0.45, 11.5, 6.25, -0.25, None, faces="n", tag="badge")
        h.decal("badge", "north", 0, 0, letters[letter], W="#f6f6f2", C=colour)


def chef_hat():
    h = Hat("chef_hat", "Chef Hat", shaped("WW", "WW", "PP", W="minecraft:white_wool", P="minecraft:paper"))
    h.mid(15, 15, 0, 5.5, ("#f3f3ef", "pleat"))
    h.mid(18, 18, 5.5, 10, ("#f3f3ef", "cloth"))
    h.mid(16, 16, 10, 11.5, ("#f3f3ef", "cloth"))


def crown():
    h = Hat("crown", "Crown", shaped("GDG", "GGG", G="minecraft:gold_ingot", D="minecraft:diamond"))
    gold, velvet = ("#e9bd2c", "gold"), ("#8c1630", "felt")
    h.mid(15, 15, 0, 3.5, gold, tag="ring")
    h.mid(14, 14, 3.5, 4.5, velvet)
    h.mid(11, 11, 4.5, 5.5, velvet)
    for x in (0.5, 6.75, 13):
        for z in (0.5, 6.75, 13):
            if (x, z) != (6.75, 6.75):
                h.box(x, 3.5, z, x + 2.5, 6.5 if x != 6.75 and z != 6.75 else 5.75, z + 2.5, gold)
    for face in ("north", "south", "east", "west"):
        for column, gem in ((4, "#d22b2b"), (13, "#2f63c9"), (22, "#d22b2b")):
            h.decal("ring", face, column, 2, ".G. GGG .G.", G=gem)


def santa_hat():
    h = Hat("santa_hat", "Santa Hat", shaped(" R ", "RRR", "WWW", R="minecraft:red_wool", W="minecraft:white_wool"))
    red, fur = ("#cc1f24", "felt"), ("#f4f4f0", "fur")
    h.mid(16.5, 16.5, 0, 3, fur)
    h.mid(15, 15, 3, 6, red)
    h.mid(12.5, 12.5, 6, 8.5, red, dx=1)
    h.mid(9.5, 9.5, 8.5, 10.5, red, dx=2.5)
    h.mid(6.5, 6.5, 9.5, 11.5, red, dx=5)
    h.box(15.5, 6, 5.5, 19.5, 10.5, 10.5, red, part="tip")   # the tip falls to one side
    h.box(16.5, 3.25, 6, 20.5, 6.75, 10, fur, part="tip")    # pom-pom
    h.move("tip", (15.5, 9, 8), ("swing", "z", 7, 2.2, 0))


def viking_helmet():
    h = Hat("viking_helmet", "Viking Helmet", shaped("B B", "III", "I I", B="minecraft:bone", I="minecraft:iron_ingot"))
    iron, bronze, horn = ("#a3a9b1", "metal"), ("#7a623a", "rivets"), ("#ece4cc", "cloth")
    h.mid(15.5, 15.5, 0, 1.5, bronze)
    h.mid(15, 15, 1.5, 4.5, iron)
    h.mid(13.5, 13.5, 4.5, 6.5, iron)
    h.mid(10.5, 10.5, 6.5, 7.75, iron)
    h.mid(1.5, 15.6, 1.5, 8.25, bronze)                # crest
    for x0, y0, z0, x1, y1, z1 in ((-3, 2, 6.25, 0.5, 5.5, 9.75), (-5.5, 4, 6.75, -2.5, 8.5, 9.25),
                                   (-6, 8, 7, -4, 12, 9), (-5.5, 11.5, 7.25, -4.25, 14, 8.75)):
        h.box(x0, y0, z0, x1, y1, z1, horn)
        h.box(16 - x1, y0, z0, 16 - x0, y1, z1, horn)


def propeller_beanie():
    h = Hat("propeller_beanie", "Propeller Beanie", shaped(" R ", "ABC", R="cyberfarm:rotor",
                                                           A="minecraft:red_wool", B="minecraft:yellow_wool", C="minecraft:blue_wool"))
    panels = ("#ffffff", "panels")
    h.mid(15, 15, 0, 4, panels)
    h.mid(13, 13, 4, 6, panels)
    h.mid(9.5, 9.5, 6, 7, panels)
    h.mid(1, 1, 7, 8.5, ("#8a8f98", "metal"))
    h.box(2.5, 8.5, 7.25, 13.5, 8.8, 8.75, ("#d22b2b", "plastic"), rot=("y", 25, (8, 8.5, 8)), part="rotor")
    h.box(7.25, 8.5, 2.5, 8.75, 8.8, 13.5, ("#f2c318", "plastic"), rot=("y", 25, (8, 8.5, 8)), part="rotor")
    h.mid(1.75, 1.75, 8.3, 9.1, ("#2b4bbd", "plastic"), part="rotor")
    h.move("rotor", (8, 8.5, 8), ("spin", "y", 1, 0.5, 0))


SKULL = ("...WWWWWW... ..WWWWWWWW.. .WWWWWWWWWW. .WWKKWWKKWW. .WWKKWWKKWW. .WWWWKKWWWW. ..WWWWWWWW.. "
         "...W.WW.W... W.........W. .WW......WW. ...WW..WW... .WW......WW. W..........W")


def pirate_hat():
    h = Hat("pirate_hat", "Pirate Hat", shaped("WWW", "WBW", W="minecraft:black_wool", B="minecraft:bone"))
    black, gold = ("#1b1a1f", "felt"), ("#d9a830", "gold")
    h.mid(15, 15, 0, 3.5, black)
    # A bicorne: a tall crescent across the head, its two ends drooping over the ears
    h.mid(24, 7, 3.5, 7, black)
    h.mid(19, 7, 7, 10, black)
    h.mid(13, 6.5, 10, 12.5, black)
    h.mid(7, 6, 12.5, 13.5, black)
    h.mid(4, 6, 0.5, 3.5, black, dx=-11)
    h.mid(4, 6, 0.5, 3.5, black, dx=11)
    # Gold edging along the outline, front and back
    for width, top in ((24, 7), (19, 10), (13, 12.5), (7, 13.5)):
        for dz in (-3.5, 3.5):
            h.mid(width + 0.5, 0.5, top - 0.75, top, gold, dz=dz)
    h.box(2, 4.25, 4.3, 14, 10.75, 4.5, None, faces="n", tag="skull")
    h.decal("skull", "north", 6, 0, SKULL, W="#ecebe4", K="#1b1a1f")


def sombrero():
    h = Hat("sombrero", "Sombrero", shaped(" H ", "WGW", H="minecraft:hay_block", W="minecraft:wheat", G="minecraft:green_dye"))
    straw = ("#dcb35a", "straw")
    h.brim(31, 0, 0.75, straw)
    h.brim(27, 0.75, 1.25, straw)
    h.mid(15, 15, 1.25, 5, straw)
    h.mid(15.5, 15.5, 1.25, 3.75, ("#c8202c", "zigzag"))
    h.mid(13, 13, 5, 8.5, straw)
    h.mid(10, 10, 8.5, 11, straw)
    h.mid(6.5, 6.5, 11, 12.5, straw)


def fedora():
    h = Hat("fedora", "Fedora", shaped(" B ", "BKB", B="minecraft:brown_wool", K="minecraft:black_carpet"))
    felt = ("#6a5240", "felt")
    h.brim(21, 0, 0.75, felt)
    h.mid(15, 15, 0.75, 6, felt)
    h.mid(15.5, 15.5, 0.75, 2.5, ("#1b1a1f", "cloth"))
    h.mid(13, 14, 6, 7.5, felt)
    h.mid(4, 12, 7.5, 8.5, felt, dx=-4)                  # the crown pinched along its top
    h.mid(4, 12, 7.5, 8.5, felt, dx=4)
    h.mid(1, 1, 1, 2.25, ("#c94a3a", "cloth"), dx=7.9, dz=-3)   # a feather's tip in the band


def beret():
    h = Hat("beret", "Beret", shapeless("minecraft:red_wool", "minecraft:red_wool", "minecraft:string"))
    red = ("#b0202a", "felt")
    h.mid(15, 15, 0, 3.5, red)
    h.mid(19, 19, 3.5, 5, red, rot=("z", 9, (8, 3.5, 8)))      # the flat top, worn to one side
    h.mid(16, 16, 5, 5.75, red, rot=("z", 9, (8, 3.5, 8)))
    h.mid(1, 1, 5.5, 6.75, red, dx=-0.5)


def ushanka():
    h = Hat("ushanka", "Ushanka", shaped("HHH", "HWH", H="minecraft:rabbit_hide", W="minecraft:brown_wool"))
    fur, top = ("#7a5636", "fur"), ("#3d2c22", "leather")
    h.mid(15, 15, 0, 6, top)
    h.mid(13.5, 13.5, 6, 7.5, top)
    # The flaps, tied up: the front over the forehead, the sides over the ears, the back
    h.box(0.5, 0.5, -1, 15.5, 6.5, 1, fur)
    h.box(-1, 1.5, 1, 1, 7, 15, fur)
    h.box(15, 1.5, 1, 17, 7, 15, fur)
    h.box(0.5, 0.5, 15, 15.5, 5, 16.5, fur)
    h.box(5.5, 3, -1.2, 10.5, 5.5, -1, None, faces="n", tag="badge")
    h.decal("badge", "north", 0, 0, "...GGGG... .GGYYYYGG. GYYYGGYYYG .GGYYYYGG. ...GGGG...", G="#a8823a", Y="#e4c058")


def graduation_cap():
    h = Hat("graduation_cap", "Graduation Cap", shaped("PPP", " WG", P="minecraft:black_carpet", W="minecraft:black_wool", G="minecraft:gold_nugget"))
    black, gold = ("#18181c", "felt"), ("#e2b33a", "gold")
    h.mid(15, 15, 0, 4.5, black)
    h.mid(20, 20, 4.5, 5.25, ("#18181c", "plastic"), rot=("y", 45, (8, 4.5, 8)))
    h.mid(1.75, 1.75, 5.25, 5.75, gold)
    h.box(8, 5.25, 7.6, 17.5, 5.55, 8.4, gold)          # cord to the corner...
    h.box(16.75, 1.5, 7.25, 18.25, 5.25, 8.75, gold, part="tassel")   # ...and the tassel hanging from it
    h.move("tassel", (17.5, 5.25, 8), ("swing", "x", 12, 1.6, 0))


def jester_hat():
    h = Hat("jester_hat", "Jester Hat", shaped("NNN", "RYP", N="minecraft:gold_nugget", R="minecraft:red_wool",
                                              Y="minecraft:yellow_wool", P="minecraft:purple_wool"))
    red, purple, yellow = ("#c8202c", "felt"), ("#6b2fa0", "felt"), ("#f0c020", "felt")
    bell = ("#e2b33a", "gold")
    h.box(0.5, 0, 0.5, 8, 4.5, 15.5, red)
    h.box(8, 0, 0.5, 15.5, 4.5, 15.5, purple)
    h.mid(16, 16, 0, 2, bell)
    # Three floppy points, each with its bell
    h.box(-1, 4, 5.5, 4, 7.5, 10.5, red)
    h.box(-4, 6, 6, 0, 8.5, 10, red, part="left")
    h.box(-6, 3.5, 6.5, -3, 7, 9.5, red, part="left")
    h.box(-6.25, 1.5, 6.75, -2.75, 3.5, 9.25, bell, part="left")
    h.box(12, 4, 5.5, 17, 7.5, 10.5, purple)
    h.box(16, 6, 6, 20, 8.5, 10, purple, part="right")
    h.box(19, 3.5, 6.5, 22, 7, 9.5, purple, part="right")
    h.box(18.75, 1.5, 6.75, 22.25, 3.5, 9.25, bell, part="right")
    h.box(5.5, 4.5, 6, 10.5, 10, 11, yellow)
    h.box(6, 9, 10, 10, 11.5, 14.5, yellow, part="middle")
    h.box(6.5, 6.5, 13.5, 9.5, 10, 16.5, yellow, part="middle")
    h.box(6.25, 4.5, 13.25, 9.75, 6.5, 16.75, bell, part="middle")
    h.move("left", (0, 7.25, 8), ("swing", "z", 6, 2.4, 0))
    h.move("right", (16, 7.25, 8), ("swing", "z", 6, 2.4, 0.5))
    h.move("middle", (8, 10.5, 10.5), ("swing", "x", 6, 2.8, 0.25))


def party_hat():
    h = Hat("party_hat", "Party Hat", shaped(" P ", "PDP", P="minecraft:paper", D="minecraft:pink_dye"))
    paper = ("#ffffff", "party")
    h.mid(15, 15, 0, 3.5, paper)
    h.mid(12, 12, 3.5, 7, paper)
    h.mid(9, 9, 7, 10.5, paper)
    h.mid(6, 6, 10.5, 14, paper)
    h.mid(3.5, 3.5, 14, 16.5, paper)
    h.mid(3.5, 3.5, 16.5, 19, ("#ffd23f", "fur"), part="pom")   # pom-pom
    h.move("pom", (8, 16.5, 8), ("bob", "y", 0.6, 0.9, 0))


def witch_hat():
    h = Hat("witch_hat", "Witch Hat", shaped(" S ", " W ", "WWW", S="minecraft:spider_eye", W="minecraft:black_wool"))
    black, band = ("#2a2233", "felt"), ("#6a2c91", "cloth")
    h.brim(26, 0, 0.75, black)
    h.mid(15, 15, 0.75, 5, black)
    h.mid(15.5, 15.5, 0.75, 3, band)
    h.mid(12, 12, 5, 9, black, dx=0.5)
    h.mid(9, 9, 9, 12.5, black, dx=1.5)
    h.mid(6, 6, 12, 15.5, black, dx=3)
    h.mid(4, 4, 15, 17.5, black, dx=5)                   # the tip bends over to one side
    h.box(14, 14.5, 7, 18, 16.5, 9, black, part="tip")
    h.box(16.5, 12, 7.25, 18.5, 15, 8.75, black, part="tip")
    h.move("tip", (14, 15.5, 8), ("swing", "z", 6, 2.4, 0))
    h.box(5.5, 1.125, 0.05, 10.5, 2.625, 0.25, None, faces="n", tag="buckle")
    h.decal("buckle", "north", 0, 0, "GGGGGGGGGG G........G GGGGGGGGGG", G="#e2b33a")


def fez():
    h = Hat("fez", "Fez", shaped("RRR", "RSR", R="minecraft:red_wool", S="minecraft:string"))
    red, black = ("#b51f28", "felt"), ("#18181c", "cloth")
    h.mid(15, 15, 0, 4, red)
    h.mid(14, 14, 4, 7, red)
    h.mid(13, 13, 7, 8.5, red)
    h.mid(1.5, 1.5, 8.5, 9, black)
    h.box(8, 8.5, 7.6, 15, 8.8, 8.4, black)              # the cord over the top...
    h.box(14.5, 3, 7.25, 16, 8.75, 8.75, black, part="tassel")   # ...and the tassel down the side
    h.move("tassel", (15.25, 8.75, 8), ("swing", "x", 12, 1.7, 0))


def mushroom_cap():
    h = Hat("mushroom_cap", "Mushroom Cap", shaped("MMM", "W W", M="minecraft:red_mushroom", W="minecraft:white_wool"))
    red = ("#d02a26", "spots")
    h.mid(15, 15, 0, 3, ("#efe6d2", "pleat"))            # the gills under the cap
    h.brim(22, 1, 3.5, red)
    h.brim(19, 3.5, 5.5, red)
    h.mid(14, 14, 5.5, 7, red)
    h.mid(8, 8, 7, 8, red)


def halo():
    h = Hat("halo", "Halo", shaped(" G ", "GLG", " G ", G="minecraft:gold_ingot", L="minecraft:glowstone_dust"))
    light = ("#ffe89a", "glow")
    # A ring floating over the head, not around it
    for x0, z0, x1, z1 in ((4, 1, 12, 2.5), (4, 13.5, 12, 15), (1, 4, 2.5, 12), (13.5, 4, 15, 12)):
        h.box(x0, 8, z0, x1, 9, z1, light, part="ring")
    for x, z in ((2, 2), (11.5, 2), (2, 11.5), (11.5, 11.5)):
        h.box(x, 8, z, x + 2.5, 9, z + 2.5, light, part="ring")
    h.move("ring", (8, 8.5, 8), ("spin", "y", 1, 6, 0), ("bob", "y", 0.5, 2.4, 0))


def samurai_helmet():
    h = Hat("samurai_helmet", "Samurai Helmet", shaped("G G", "III", "IRI", G="minecraft:gold_nugget", I="minecraft:iron_ingot", R="minecraft:red_dye"))
    lacquer, gold = ("#1f1d22", "plastic"), ("#d9a830", "gold")
    lames = ("#24222a", "lames")
    h.mid(15, 15, 0, 5, lacquer)
    h.mid(13, 13, 5, 7, lacquer)
    h.mid(9, 9, 7, 8, lacquer)
    h.mid(1.5, 1.5, 8, 8.75, gold)
    # The neck guard flares out over the sides and the back, in laced plates
    h.box(-1.5, 0, 3, 17.5, 3, 18, lames)
    h.box(-0.5, 3, 4, 16.5, 4.5, 17, lames)
    # Turned-back wings at the front
    h.box(-2.5, 1.5, 0.5, 0.5, 5, 3.5, lacquer)
    h.box(15.5, 1.5, 0.5, 18.5, 5, 3.5, lacquer)
    # The golden crest: a base on the brow and two horns sweeping up
    h.box(6.5, 4.5, -0.75, 9.5, 6.5, 0.5, gold)
    h.box(3.5, 5.5, -0.5, 6.5, 6.5, 0.25, gold)
    h.box(9.5, 5.5, -0.5, 12.5, 6.5, 0.25, gold)
    h.box(2.5, 6, -0.5, 3.75, 11, 0.25, gold, rot=("z", 20, (3.5, 6, 0)))
    h.box(12.25, 6, -0.5, 13.5, 11, 0.25, gold, rot=("z", -20, (12.5, 6, 0)))


def aviator_cap():
    h = Hat("aviator_cap", "Aviator Cap", shaped("LLL", "GLG", L="minecraft:leather", G="minecraft:glass_pane"))
    leather, fleece = ("#6b4226", "leather"), ("#e9dcc2", "fur")
    brass = ("#b8893a", "metal")
    h.mid(15, 15, 0, 5, leather)
    h.mid(13.5, 13.5, 5, 7, leather)
    h.mid(10, 10, 7, 8, leather)
    h.box(-0.5, 0, 4, 1, 4.5, 11, fleece)               # ear flaps, buckled up
    h.box(15, 0, 4, 16.5, 4.5, 11, fleece)
    h.mid(15.5, 15.5, 3.75, 5.25, ("#2a221c", "cloth"))  # the goggles' strap
    h.box(1.5, 3, -0.75, 7, 7, 0.5, brass, tag="lens")
    h.box(9, 3, -0.75, 14.5, 7, 0.5, brass, tag="lens")
    h.box(7, 4.5, -0.25, 9, 5.5, 0.5, brass)
    h.decal("lens", "north", 0, 0, ".BBBBBBBBB. BBGGGGGGGBB BGGHHGGGGGB BGGHGGGGGGB BGGGGGGGGGB BGGGGGGGGGB BBGGGGGGGBB .BBBBBBBBB.",
            B="#b8893a", G="#4f8a6a", H="#b9e3c6")


def captain_hat():
    h = Hat("captain_hat", "Captain Hat", shaped("WWW", "KGK", W="minecraft:white_wool", K="minecraft:black_wool", G="minecraft:gold_nugget"))
    white, black, gold = ("#f3f2ec", "cloth"), ("#1b1d26", "cloth"), ("#e2b33a", "gold")
    h.mid(15, 15, 0, 3.5, black)
    h.brim(18, 3.5, 6, white)                            # the wide top
    h.box(2.5, 0, -4, 13.5, 0.75, 0.5, ("#111114", "plastic"))   # visor
    h.box(2, 1, -0.25, 14, 1.75, 0.5, gold)              # braid over the visor
    h.box(5.5, 1.75, -0.5, 10.5, 6.25, -0.25, None, faces="n", tag="anchor")
    h.decal("anchor", "north", 0, 0, "....GG.... ...G..G... ....GG.... .GGGGGGGG. ....GG.... ....GG.... G...GG...G GG..GG..GG .GGGGGGGG.",
            G="#e2b33a")


def frog_hat():
    h = Hat("frog_hat", "Frog Hat", shaped("S S", "GGG", S="minecraft:slime_ball", G="minecraft:green_wool"))
    green = ("#5aa83e", "felt")
    h.brim(20, 0, 0.75, green)
    h.mid(15, 15, 0.75, 5, green)
    h.mid(13, 13, 5, 6.5, green)
    for x in (3, 10):
        h.box(x, 6, 2.5, x + 3, 9, 5.5, green, tag="eye", part="eyes")
    h.move("eyes", (8, 6, 4), ("blink", "y", 1, 3.5, 0))
    eye = ".WWWW. WWWWWW WKKWWW WKKWWW WWWWWW .WWWW."
    h.decal("eye", "north", 0, 0, eye, W="#f6f6f2", K="#18181c")
    h.box(4, 3, 0.3, 12, 4.5, 0.5, None, faces="n", tag="mouth")
    h.decal("mouth", "north", 0, 0, "K..............K .KKKKKKKKKKKKKK. ....PP....PP....", K="#2c4a22", P="#f08a9a")


def chicken_hat():
    h = Hat("chicken_hat", "Chicken Hat", shapeless("minecraft:feather", "minecraft:feather", "minecraft:egg", "minecraft:white_wool"))
    white = ("#f4f3ee", "fur")
    # A chicken sitting on the head, as Minecraft draws one
    h.box(4.5, 0, 4, 11.5, 7, 13, white)
    h.box(3.5, 2.5, 5, 4.5, 6, 11.5, white)              # wings
    h.box(11.5, 2.5, 5, 12.5, 6, 11.5, white)
    h.box(5.5, 5, 1.5, 10.5, 12, 5.5, white, tag="head", part="head")
    h.box(5.5, 8, -0.5, 10.5, 10, 1.5, ("#f2b51c", "plastic"), part="head")   # beak
    h.box(7, 6, 0.5, 9, 8, 1.5, ("#d0282a", "cloth"), part="head")            # wattle
    h.move("head", (8, 6, 4), ("swing", "x", 10, 1.1, 0))
    h.decal("head", "north", 0, 2, "K........K K........K", K="#18181c")


def tall_top_hats():
    """Top hats from games and anime: a felt crown, a coloured band, and each one's own touch."""
    for name, title, felt, band, wool, dye in (
            ("professor_top_hat", "Professor's Top Hat", "#4e3527", "#d4561e", "brown", "orange"),
            ("time_traveler_top_hat", "Time Traveler's Top Hat", "#6a4bb0", "#f2b81c", "purple", "yellow"),
            ("phantom_thief_hat", "Phantom Thief Hat", "#eef0f2", "#2f4a8a", "white", "blue")):
        h = Hat(name, title, shaped(" W ", " W ", f"WDW", W=f"minecraft:{wool}_wool", D=f"minecraft:{dye}_dye"))
        felt, band = (felt, "felt"), (band, "cloth")
        if name == "time_traveler_top_hat":
            h.brim(20, 0, 0.75, felt)
            h.mid(15, 15, 0.75, 6, felt)
            h.mid(16, 16, 6, 11.5, felt)                 # flaring out towards the top
            h.mid(15.5, 15.5, 0.75, 3.75, band)
            continue
        h.brim(22 if name == "phantom_thief_hat" else 21, 0, 0.75, felt)
        h.mid(15, 15, 0.75, 13.5 if name == "professor_top_hat" else 12.5, felt)
        h.mid(15.5, 15.5, 0.75, 3.5, band)
        if name == "phantom_thief_hat":
            h.box(-1, 1, 4, 0.25, 4, 7, band)            # a bow on the left side
            h.box(-1.5, 1.5, 2.5, 0.25, 3.5, 4, band)
            h.box(-1.5, 1.5, 7, 0.25, 3.5, 8.5, band)


def apprentice_cap():
    h = Hat("apprentice_cap", "Apprentice Cap", shaped("WWW", "WS ", W="minecraft:light_blue_wool", S="minecraft:stone_button"))
    cloth = ("#6f8ea3", "cloth")
    h.mid(15, 15, 0, 3.5, cloth)
    h.mid(17, 16, 3.5, 5.5, cloth, dz=0.5)               # soft and round, wider than the head
    h.mid(15.5, 14.5, 5.5, 7, cloth, dz=0.5)
    h.mid(11, 10.5, 7, 8, cloth, dz=0.5)
    h.mid(0.75, 12, 7.75, 8.3, cloth, dz=0.5)            # the seam over the top
    h.mid(1.5, 1.5, 8, 8.75, cloth)                      # button
    h.box(3, 0, -2.5, 13, 0.75, 0.5, ("#5d7a8d", "cloth"))   # a short peak


def trainer_cap():
    h = Hat("trainer_cap", "Trainer Cap", shaped("RWR", "GL ", R="minecraft:red_wool", W="minecraft:white_wool",
                                                  G="minecraft:green_dye", L="minecraft:leather"))
    red, white = ("#d62b2b", "cloth"), ("#f4f4f0", "cloth")
    h.mid(15, 15, 0, 4.5, red)
    h.mid(13.5, 13.5, 4.5, 6, red)
    h.mid(10.5, 10.5, 6, 7, red)
    h.box(1.5, 0.5, -0.25, 14.5, 6.25, 4, white)         # the white front
    h.box(3, 6, 0.5, 13, 7, 4, white)
    h.box(2, 0, -5.5, 14, 0.75, 0.5, red)                # peak
    h.box(3.5, 0, -6.5, 12.5, 0.75, -5.5, red)
    h.box(4.5, 1, -0.45, 11.5, 5.5, -0.25, None, faces="n", tag="logo")
    h.decal("logo", "north", 0, 0, "...........GG. .........GGG.. .......GGG.... .....GGG...... ...GGG........ ..GG.......... "
                                   ".GG........... .GGGGGGGGGGG.. ..GGGGGGGGGGGG", G="#2e7d32")


def wanderer_hat():
    h = Hat("wanderer_hat", "Wanderer's Hat", shaped("NGN", "BBB", "S S", N="minecraft:gold_nugget", G="minecraft:gold_ingot",
                                                    B="minecraft:black_wool", S="minecraft:string"))
    dark, red, gold = ("#2b1d22", "felt"), ("#b3262b", "cloth"), ("#c99a3c", "gold")
    h.mid(15, 15, 0, 6, dark)
    # A wide, low cone, red underneath
    h.brim(31, 6, 6.5, red)
    h.brim(30, 6.5, 7.25, dark)
    h.brim(22, 7.25, 8.25, dark)
    h.brim(14, 8.25, 9.25, dark)
    h.mid(8, 8, 9.25, 10.25, dark)
    # The golden crest in front, and the scrolls on the two ends of the brim
    h.box(7.25, 7.25, 0.25, 8.75, 13.5, 1.25, gold)
    h.box(6.75, 13.5, -0.5, 9.25, 16, 2, gold)              # a plate on top of the post
    h.box(7.25, 16, 0, 8.75, 16.75, 1.5, gold)
    for x0, y0, z0, x1, y1, z1, material, cord in (
            (-6.5, 7.25, 7, -5, 10, 9, gold, False), (-8, 9, 7, -6.5, 11, 9, gold, False),
            (-6.5, 10.5, 7, -5, 11.5, 9, gold, False),
            # A red cord hanging from under the brim, with a golden ring at its end
            (-5.25, 2, 7.6, -4.5, 6, 8.4, red, True), (-6, 0.5, 7.25, -3.75, 2, 8.75, gold, True)):
        h.box(x0, y0, z0, x1, y1, z1, material, part="left_cord" if cord else None)
        # and the same on the right
        h.box(16 - x1, y0, z0, 16 - x0, y1, z1, material, part="right_cord" if cord else None)
    h.move("left_cord", (-4.875, 6.25, 8), ("swing", "x", 8, 2.0, 0))
    h.move("right_cord", (20.875, 6.25, 8), ("swing", "x", 8, 2.0, 0.5))


def black_mage_hat():
    h = Hat("black_mage_hat", "Black Mage Hat", shaped("  Y", " YY", "YLY", Y="minecraft:yellow_wool", L="minecraft:leather"))
    straw, band = ("#d4b064", "felt"), ("#8b5a36", "leather")
    h.brim(25, 0, 1, straw)
    h.mid(15, 15, 1, 6, straw)
    h.mid(15.5, 15.5, 1.5, 4, band)
    h.mid(13, 13, 6, 9.5, straw)
    h.mid(11, 11, 9.5, 12.5, straw, dz=-0.5)
    h.mid(8.5, 8.5, 12.5, 15, straw, dx=0.5, dz=-1.5)
    h.mid(6, 6, 15, 17, straw, dx=0.5, dz=-3)
    h.mid(4.5, 4.5, 16.5, 18.5, straw, dx=0.5, dz=-5.5, part="tip")  # the tip flops forward...
    h.mid(3, 3, 14.5, 17, straw, dx=0.5, dz=-7.5, part="tip")        # ...and down
    h.move("tip", (8.5, 17.5, 4.5), ("swing", "x", 6, 2.6, 0), ("swing", "z", 4, 3.3, 0.3))


# Two-texel round eyes with a white glint, and the like, for the faces on the hats below
EYE = "KWK KKK KKK"
BIG_EYE = ".KK. KWKK KKKK .KK."


def electric_mouse_hat():
    h = Hat("electric_mouse_hat", "Electric Mouse Hat", shaped("Y Y", "YRY", Y="minecraft:yellow_wool", R="minecraft:red_dye"))
    yellow, black = ("#f5cf2e", "felt"), ("#2a2522", "felt")
    h.mid(15, 15, 0, 5, yellow, tag="face")
    h.mid(13.5, 13.5, 5, 7, yellow)
    h.mid(10, 10, 7, 8, yellow)
    # Long ears leaning out, black at the tips; they twitch
    for part, x0, angle in (("left_ear", 2, 22.5), ("right_ear", 11, -22.5)):
        pivot = (x0 + 1.5, 6.5, 8)
        h.box(x0, 6.5, 7, x0 + 3, 12.5, 9.5, yellow, rot=("z", angle, pivot), part=part)
        h.box(x0, 12.5, 7, x0 + 3, 15, 9.5, black, rot=("z", angle, pivot), part=part)
    h.move("left_ear", (3.5, 7, 8), ("swing", "z", 5, 2.2, 0))
    h.move("right_ear", (12.5, 7, 8), ("swing", "z", 5, 2.2, 0.35))
    face = {"K": "#2a2522", "W": "#ffffff", "R": "#d8392b"}
    h.decal("face", "north", 7, 1, EYE, **face)
    h.decal("face", "north", 20, 1, EYE, **face)
    h.decal("face", "north", 2, 5, ".RR. RRRR .RR.", **face)
    h.decal("face", "north", 24, 5, ".RR. RRRR .RR.", **face)
    h.decal("face", "north", 12, 5, "K.K.K .K.K.", **face)


def sea_otter_hat():
    h = Hat("sea_otter_hat", "Sea Otter Hat", shaped("BBB", "WSW", B="minecraft:blue_wool", W="minecraft:white_wool",
                                                    S="minecraft:nautilus_shell"))
    # A crocheted white beanie: blue pointed ears, big eyes, a round brown nose, freckles, a pale blue rim
    white, rim, blue = ("#f1efe8", "knit"), ("#8fc6e8", "knit"), ("#2f55c0", "felt")
    h.mid(15, 15, 0, 5.5, white, tag="face")
    h.mid(15.5, 15.5, 0, 1, rim)
    h.mid(14, 14, 5.5, 7.5, white)
    h.mid(11.5, 11.5, 7.5, 9, white)
    h.mid(7, 7, 9, 9.75, white)
    # The ears rise from the top corners and lean out
    for x0, x1, x2, x3, x4, x5 in ((0.5, 5, -0.5, 3.5, -1.5, 1.5), (11, 15.5, 12.5, 16.5, 14.5, 17.5)):
        h.box(x0, 6, 6, x1, 9, 10, blue)
        h.box(x2, 9, 6.5, x3, 11, 9.5, blue)
        h.box(x4, 11, 7, x5, 12.5, 9, blue)
    nose = ("#8a5a36", "knit")                                     # the nose, a round brown button
    h.box(6.5, 2, -0.75, 9.5, 4, 0.5, nose)
    h.box(7, 1.5, -0.75, 9, 4.5, 0.5, nose)
    face = {"N": "#1f2440", "W": "#ffffff", "K": "#1a1a1a"}
    h.decal("face", "north", 4, 1, ".NNNN. NNWWNN NNWWNN NNNNNN NNNNWN .NNNN.", **face)
    h.decal("face", "north", 20, 1, ".NNNN. NNWWNN NNWWNN NNNNNN NWNNNN .NNNN.", **face)
    h.decal("face", "north", 3, 8, "K.K. .K..", **face)
    h.decal("face", "north", 25, 8, ".K.K ..K.", **face)


def sleepy_giant_hat():
    h = Hat("sleepy_giant_hat", "Sleepy Giant Hat", shaped("TTT", "TCT", T="minecraft:cyan_wool", C="minecraft:cake"))
    teal, cream = ("#2f6474", "felt"), ("#efe0bd", "felt")
    h.mid(15, 15, 0, 6, teal)
    h.mid(14, 14, 6, 8, teal)
    h.mid(11, 11, 8, 9.25, teal)
    h.box(1.5, 0.25, -0.3, 14.5, 6.5, 1, cream, tag="face")   # the pale face, fast asleep
    for x0 in (1, 12):
        h.box(x0, 7.5, 6, x0 + 3, 10.5, 9, teal)              # small pointed ears
        h.box(x0 + 0.75, 10.5, 6.75, x0 + 2.25, 12, 8.25, teal)
    face = {"K": "#2a2522", "W": "#ffffff"}
    h.decal("face", "north", 4, 4, "KKKKK", **face)
    h.decal("face", "north", 17, 4, "KKKKK", **face)
    h.decal("face", "north", 7, 8, "KKKKKKKKKKKK .W........W.", **face)


def pink_puffball_hat():
    h = Hat("pink_puffball_hat", "Pink Puffball Hat", shaped("PPP", "PSP", P="minecraft:pink_wool", S="minecraft:sugar"))
    pink = ("#f4a3c3", "felt")
    h.mid(15, 15, 0, 5.5, pink, tag="face")
    h.mid(14, 14, 5.5, 7.5, pink)
    h.mid(11.5, 11.5, 7.5, 9, pink)
    h.mid(7, 7, 9, 9.75, pink)
    h.box(-0.75, 1, 6, 0.75, 4, 10, pink)                  # stubby arms
    h.box(15.25, 1, 6, 16.75, 4, 10, pink)
    face = {"N": "#1f2a55", "W": "#ffffff", "R": "#e8607e", "K": "#7a2a3a"}
    h.decal("face", "north", 10, 1, "W. NN NN NN", **face)
    h.decal("face", "north", 18, 1, "W. NN NN NN", **face)
    h.decal("face", "north", 5, 7, "RRR", **face)
    h.decal("face", "north", 22, 7, "RRR", **face)
    h.decal("face", "north", 14, 7, "KK", **face)


def blue_slime_hat():
    h = Hat("blue_slime_hat", "Blue Slime Hat", shaped("BSB", "BBB", B="minecraft:blue_wool", S="minecraft:slime_ball"))
    blue = ("#3d8fe6", "plastic")
    h.mid(15, 15, 0, 4, blue, tag="face")
    h.mid(13.5, 13.5, 4, 6.5, blue)
    h.mid(10.5, 10.5, 6.5, 8.5, blue)
    h.mid(7, 7, 8.5, 10, blue)
    # The little curl on top, wobbling
    h.mid(4, 4, 10, 11.5, blue, part="tip")
    h.mid(2, 2, 11.5, 13, blue, part="tip")
    h.box(9, 12.5, 7.25, 10.5, 13.5, 8.75, blue, part="tip")
    h.move("tip", (8, 10, 8), ("swing", "z", 8, 1.4, 0), ("swing", "x", 5, 1.9, 0.25))
    face = {"K": "#1a1a1a", "W": "#ffffff", "R": "#d23a3a"}
    h.decal("face", "north", 8, 1, BIG_EYE, **face)
    h.decal("face", "north", 18, 1, BIG_EYE, **face)
    h.decal("face", "north", 10, 5, "K..........K .KKKKKKKKKK. ..KKRRRRKK..", **face)


def reindeer_doctor_hat():
    h = Hat("reindeer_doctor_hat", "Reindeer Doctor Hat", shaped("PPP", "PWP", P="minecraft:pink_wool", W="minecraft:white_wool"))
    pink, antler = ("#f08ab2", "felt"), ("#8a5a32", "leather")
    h.brim(21, 0, 0.75, pink)
    h.mid(15, 15, 0.75, 8, pink, tag="cross")
    h.mid(14.5, 14.5, 8, 10, pink)
    # The antlers poke out through holes in the sides
    for side in (1, -1):
        def at(x0, x1):
            return (x0, x1) if side == 1 else (16 - x1, 16 - x0)
        a0, a1 = at(-2.5, 0.75)
        h.box(a0, 4.5, 7.25, a1, 5.75, 8.75, antler)
        b0, b1 = at(-2.5, -1.25)
        h.box(b0, 5.75, 7.25, b1, 10, 8.75, antler)
        c0, c1 = at(-1.25, 0)
        h.box(c0, 8, 7.4, c1, 9, 8.6, antler)
    h.decal("cross", "north", 9, 1, "WW......WW .WW....WW. ..WW..WW.. ...WWWW... ....WW.... ...WWWW... ..WW..WW.. "
                                    ".WW....WW. WW......WW", W="#f6f6f2")


def forest_spirit_hat():
    h = Hat("forest_spirit_hat", "Forest Spirit Hat", shaped("G G", "GGG", "GWG", G="minecraft:gray_wool", W="minecraft:white_wool"))
    gray = ("#7d7f7a", "felt")
    h.mid(15, 15, 0, 5.5, gray, tag="face")
    h.mid(13.5, 13.5, 5.5, 7.5, gray)
    h.mid(10, 10, 7.5, 8.5, gray)
    # Pointed ears that twitch
    for part, x0 in (("left_ear", 3), ("right_ear", 11)):
        h.box(x0, 8, 7, x0 + 2, 11, 9, gray, part=part)
        h.box(x0 + 0.4, 11, 7.4, x0 + 1.6, 13, 8.6, gray, part=part)
    h.move("left_ear", (4, 8, 8), ("swing", "z", 4, 3.1, 0))
    h.move("right_ear", (12, 8, 8), ("swing", "z", 4, 3.1, 0.4))
    face = {"K": "#1a1a1a", "W": "#f2efe6", "G": "#4a4b48"}
    h.decal("face", "north", 5, 1, ".WWW. WWWWW WWKKW WWKKW .WWW.", **face)
    h.decal("face", "north", 20, 1, ".WWW. WWWWW WKKWW WKKWW .WWW.", **face)
    h.decal("face", "north", 13, 3, "KKKK .KK.", **face)
    h.decal("face", "north", 0, 6, "GGGGG ....G", **face)
    h.decal("face", "north", 25, 6, "GGGGG G....", **face)


def horned_mask():
    h = Hat("horned_mask", "Horned Mask", shaped("B B", "WWW", B="minecraft:bone_block", W="minecraft:white_wool"))
    white = ("#f2f2ee", "plastic")
    h.mid(15, 15, 0, 6, white, tag="face")
    h.mid(13, 13, 6, 8, white)
    h.mid(9, 9, 8, 9, white)
    # Two horns curving out and up
    for x0, x1, x2, x3, x4, x5 in ((2, 4, 1, 3, 0.5, 2), (12, 14, 13, 15, 14, 15.5)):
        h.box(x0, 8, 7, x1, 11, 9, white)
        h.box(x2, 10.5, 7.25, x3, 14, 8.75, white)
        h.box(x4, 13.5, 7.5, x5, 16, 8.5, white)
    face = {"K": "#101014"}
    eye = ".KKK. KKKKK KKKKK KKKKK KKKKK .KKK."
    h.decal("face", "north", 6, 3, eye, **face)
    h.decal("face", "north", 19, 3, eye, **face)


for make in (hard_hat, wizard_hat, flat_cap, straw_hat, elf_cap, cowboy_hat, baseball_cap, top_hats, plumber_caps,
             chef_hat, crown, santa_hat, viking_helmet, propeller_beanie, pirate_hat, sombrero, fedora, beret, ushanka,
             graduation_cap, jester_hat, party_hat, witch_hat, fez, mushroom_cap, halo, samurai_helmet, aviator_cap,
             captain_hat, frog_hat, chicken_hat, tall_top_hats, apprentice_cap, trainer_cap, wanderer_hat, black_mage_hat,
             electric_mouse_hat, sea_otter_hat, sleepy_giant_hat, pink_puffball_hat, blue_slime_hat, reindeer_doctor_hat,
             forest_spirit_hat, horned_mask):
    make()

# A famous line from the game, anime or film a hat comes from, shown under its name
QUOTES = {
    "red_plumber_cap": "It's-a me, Mario!",
    "green_plumber_cap": "Okey dokey!",
    "mushroom_cap": "Thank you Mario! But our princess is in another castle!",
    "elf_cap": "It's dangerous to go alone! Take this.",
    "straw_hat": "I'm gonna be King of the Pirates!",
    "cowboy_hat": "Thank you for loving me.",
    "baseball_cap": "The ball is my friend!",
    "flat_cap": "By order of the Peaky Blinders.",
    "fedora": "It belongs in a museum!",
    "fez": "I wear a fez now. Fezzes are cool.",
    "party_hat": "The cake is a lie.",
    "halo": "Wake me, when you need me.",
    "chicken_hat": "Chicken jockey!",
    "professor_top_hat": "Every puzzle has an answer.",
    "apprentice_cap": "I'm the Professor's number one apprentice!",
    "phantom_thief_hat": "Ladies and gentlemen, it's showtime!",
    "trainer_cap": "I choose you!",
    "black_mage_hat": "How do you prove that you exist...?",
    "electric_mouse_hat": "Pika pika!",
    "sea_otter_hat": "Osha osha!",
    "sleepy_giant_hat": "A sleeping Pokemon blocks the way!",
    "pink_puffball_hat": "Poyo!",
    "blue_slime_hat": "A slime draws near!",
    "reindeer_doctor_hat": "Saying that won't make me happy, you jerk!",
}


# ------------------------------------------------------------------ files

GUI_SPRITES = {
    # The empty Hat slot, like vanilla's armor slot silhouettes
    "container/slot/hat": ("................ ................ ....########.... ....########.... ....########.... ....########.... "
                           "....########.... ....########.... ...##########... ....########.... ..############.. "
                           ".##############. ..############.. ................ ................ ................",
                           {"#": (198, 198, 198, 255)}),
    # The button above it: an open eye shows the hat, a closed one hides it
    "hat_shown": ("......... ...###... .##WWW##. #WWW#WWW# #WW###WW# #WWW#WWW# .##WWW##. ...###... .........",
                  {"#": (55, 55, 55, 255), "W": (255, 255, 255, 255)}),
    "hat_hidden": ("......... ......... ......... #.......# .#######. ..#.#.#.. ......... ......... .........",
                   {"#": (55, 55, 55, 255)}),
}


def sprite(art, colours):
    """Pixel art from rows of letters, one per colour; a dot is transparent."""
    return [[colours.get(char, (0, 0, 0, 0)) for char in line] for line in art.split()]


def png(path, rows):
    raw = b"".join(b"\0" + bytes(channel for pixel in row for channel in pixel) for row in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", len(rows[0]), len(rows), 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, indent=2) + "\n", encoding="utf-8")


JEI_INFO = ("A hat, just for looks. Right-click with it or put it in your helmet slot to wear it.\n\n"
            "Over a helmet, put it in the Hat slot right of you in the inventory (Curios' head slot, with Curios): it shows "
            "in place of the helmet, which still protects you. The eye above the slot hides it.\n\n"
            "Right-click a CyberFarm drone with it (sneaking, on a Taxi drone) and the drone wears it in place of its "
            "antenna. Shears take it off; a drone you pick up drops its hat.")

# Book pages: a Patchouli page holds about 250 characters
PATCHOULI_TEXT = ("Hats do nothing at all, and look good doing it. $(l)You$() can wear one, and so can your drones: a drone "
                  "folds its antenna away and wears the hat on its tank, clear of every module.$(br2)"
                  "Some hats move: the propeller spins, tassels and tips sway, the halo floats.",
                  "$(li)$(l)Wear a hat$(): right-click with it, or put it in your helmet slot.$(br)"
                  "$(li)$(l)Over a helmet$(): put it in the Hat slot right of you in the inventory. The helmet still "
                  "protects you; the eye above the slot hides the hat.",
                  "$(li)$(l)On a drone$(): right-click the drone with the hat.$(br)"
                  "$(li)$(l)Take it off$(): right-click the drone with Shears.$(br2)"
                  "A drone you pick up drops its hat. Armor stands can wear hats too. With Curios or Cosmetic Armor "
                  "there is no Hat slot: their cosmetic slots take hats.")

PAGE = """---
navigation:
  title: Hats
  parent: cyberfarm:drone_systems.md
  position: 10
  icon: cyberhats:straw_hat
item_ids:
{ids}
---

# Hats

<ItemGrid>
{icons}
</ItemGrid>

Hats do nothing at all, and look good doing it. **You** can wear one, and so can your
[drones](cyberfarm:drones.md): a drone folds its antenna away and wears the hat on its tank, clear of every module.

Some hats move: the propeller spins, tassels and floppy tips sway, the jester's points jiggle, the halo floats and
turns, the frog blinks and the chicken pecks.

| To | Do this |
| --- | --- |
| Wear a hat | Right-click with it in your hand, or put it in your helmet slot |
| Wear it over a helmet | Put it in the **Hat slot**, right of you in the inventory: it shows in place of the helmet, which still protects you |
| Hide it for a while | Click the **eye** above the Hat slot |
| Put a hat on a drone | Right-click the drone with the hat. On a Taxi drone, **sneak** and right-click |
| Take a hat off a drone | Right-click the drone with **Shears** |

With **Curios** installed there is no Hat slot: hats go in Curios' head slot instead, and Curios' own
buttons show or hide them.

A drone wears one hat at a time. If you **pick the drone up**, or it is destroyed, its hat drops on the
ground. Armor stands can wear hats too.

## The hats

{recipes}
"""


def main():
    java = (ROOT / "src/main/java/com/cyberhats/CyberHats.java").read_text(encoding="utf-8")
    quoted = set(re.findall(r'"(\w+)"', java.split("QUOTED =")[1].split(";")[0]))
    assert quoted == set(QUOTES), f"CyberHats.QUOTED must list exactly the hats with a quote: {sorted(quoted ^ set(QUOTES))}"
    for hat in HATS:
        assert f'"{hat.name}"' in java, f"{hat.name} is not registered in CyberHats.HATS"
        elements, rows, size, (low, high) = build(hat)
        png(ASSETS / f"textures/item/{hat.name}.png", rows)
        # In a slot: as large as fits, the way a block is shown, and centred on the hat's own middle
        scale = round(min(0.72, 0.625 * 16 / max(high[0] - low[0], high[2] - low[2], (high[1] - low[1]) * 1.3)), 3)
        lift = round(0.866 * scale * (8 - (low[1] + high[1]) / 2), 2)
        write(ASSETS / f"models/item/{hat.name}.json", {
            "parent": "cyberhats:item/hat",
            "textures": {"hat": f"cyberhats:item/{hat.name}", "particle": f"cyberhats:item/{hat.name}"},
            "display": {"head": {"translation": [0, WRAP_TRANSLATION if hat.wraps else PERCH_TRANSLATION, 0]},
                        "gui": {"rotation": [30, 225, 0], "translation": [0, lift, 0], "scale": [scale] * 3},
                        # In an item frame: the same three-quarter view, turned for a frame that faces the viewer
                        "fixed": {"rotation": [-30, 45, 0], "translation": [0, round(lift * 0.8, 2), 0], "scale": [round(scale * 0.8, 3)] * 3}},
            "elements": elements})
        if LEGACY:
            write(DATA / f"recipes/{hat.name}.json", legacy_recipe(hat))
        else:
            model = {"type": "minecraft:model", "model": f"cyberhats:item/{hat.name}"}
            if hat.motions:
                # The still model, and over it the moving parts the game's code draws (HatParts.java)
                model = {"type": "minecraft:composite", "models": [model, {
                    "type": "minecraft:special", "base": f"cyberhats:item/{hat.name}",
                    "model": {"type": "cyberhats:hat_parts", "texture": f"cyberhats:textures/item/{hat.name}.png", "parts": parts_data(hat)}}]}
            write(ASSETS / f"items/{hat.name}.json", {"model": model})
        if LEGACY and hat.motions:
            write(ASSETS / f"hat_parts/{hat.name}.json", {"parts": parts_data(hat)})
            write(DATA / f"recipe/{hat.name}.json", {**hat.recipe, "result": {"id": f"cyberhats:{hat.name}"}})
    lang = {}
    for hat in HATS:
        lang[f"item.cyberhats.{hat.name}"] = hat.title
        if hat.name in QUOTES:
            lang[f"item.cyberhats.{hat.name}.quote"] = f'"{QUOTES[hat.name]}"'
    write(ASSETS / "lang/en_us.json", {**lang, "cyberhats.jei.hat": JEI_INFO, "cyberhats.hat_slot.toggle": "Show or hide the hat",
                                         "cyberhats.hat_slot.hide": "Hide the hat", "cyberhats.hat_slot.show": "Show the hat"})
    for name, (art, colours) in GUI_SPRITES.items():
        # 1.20.1 has no GUI sprites: the empty slot's icon lives in the block atlas, the buttons are plain textures
        path = {"container/slot/hat": "item/empty_hat_slot", "hat_shown": "gui/hat_shown", "hat_hidden": "gui/hat_hidden"}[name]             if LEGACY else f"gui/sprites/{name}"
        png(ASSETS / f"textures/{path}.png", sprite(art, colours))
    # With Curios: hats are let into its head slot, and players are given that slot
    write(DATA.parent / f"curios/tags/{'items' if LEGACY else 'item'}/head.json",
          {"replace": False, "values": [f"cyberhats:{hat.name}" for hat in HATS]})
    write(DATA / "curios/entities/hats.json", {"entities": ["minecraft:player"], "slots": ["head"]})
    if LEGACY:
        # CyberFarm's 1.20.1 handbook is a Patchouli book read from resource packs: the entry joins its Drones chapter
        pages = [{"type": "patchouli:text", "text": text} for text in PATCHOULI_TEXT]
        pages += [{"type": "patchouli:crafting", "recipe": f"cyberhats:{a.name}", **({"recipe2": f"cyberhats:{b.name}"} if b else {})}
                  for a, b in zip(HATS[::2], HATS[1::2] + [None])]
        write(ROOT / "src/main/resources/assets/cyberfarm/patchouli_books/handbook/en_us/entries/drone_systems/hats.json",
              {"name": "Hats", "icon": "cyberhats:straw_hat", "category": "cyberfarm:drone_systems", "sortnum": 20, "pages": pages})
        print(f"{len(HATS)} hats for {MC}")
        return
    write(ASSETS / "guides/cyberfarm/handbook/hats.md", PAGE.format(
        ids="\n".join(f"  - cyberhats:{hat.name}" for hat in HATS),
        icons="\n".join(f'  <ItemIcon id="cyberhats:{hat.name}" />' for hat in HATS),
        recipes="\n".join(f'<RecipeFor id="cyberhats:{hat.name}" />' for hat in HATS)))
    print(f"{len(HATS)} hats: " + ", ".join(f'"{hat.name}"' for hat in HATS))


if __name__ == "__main__":
    main()
