"""Writes every hat: model, item file, texture, recipe, name, and the handbook page.  Run: python tools/hats.py

A hat is a list of boxes in model units, each of a material that paints its own texture (straw weave, felt grain,
knit ribs...), plus small pixel drawings ("decals") on chosen faces. Two texels per unit.

How a hat must be built:
- centred on x = z = 8, standing on y = 0 and never below it, north (-z) is the face side;
- its lowest 3.5 units cover the square from 0.5 to 15.5: on a player the hat is pulled 2.4 units down over the
  head (12.8 units wide, 14.4 with the skin's outer layer), which must not show through;
- on a drone it stands on the tank at 0.27 pixels per unit, with every module below it.
"""
import json
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src/main/resources/assets/cyberhats"
DATA = ROOT / "src/main/resources/data/cyberhats"
RES = 2
HATS = []
FACES = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}
STITCH = (58, 42, 32)
PANELS = ["#d22b2b", "#f2c318", "#2b4bbd", "#2e8b3d"]


class Hat:
    def __init__(self, name, title, recipe):
        self.name, self.title, self.recipe = name, title, recipe
        self.boxes = []    # (bounds, material, rotation, faces, tag)
        self.decals = []   # (tag, face, column, row, art, colours)
        HATS.append(self)

    def box(self, x0, y0, z0, x1, y1, z1, material, rot=None, faces="nsewud", tag=None):
        """rot: (axis, degrees, origin). material None: see-through, for a face that only carries a decal."""
        self.boxes.append(((x0, y0, z0, x1, y1, z1), material, rot, faces, tag))

    def mid(self, width, depth, y0, y1, material, dx=0.0, dz=0.0, **more):
        """A box centred on the hat's axis, or dx / dz off it."""
        self.box(8 + dx - width / 2, y0, 8 + dz - depth / 2, 8 + dx + width / 2, y1, 8 + dz + depth / 2, material, **more)

    def brim(self, size, y0, y1, material):
        """A brim with its corners cut, as round as boxes get."""
        cut = round(size * 0.72 * 2) / 2
        self.mid(size, cut, y0, y1, material)
        self.mid(cut, size, y0, y1, material)
        self.mid(round(size * 0.9 * 2) / 2, round(size * 0.9 * 2) / 2, y0, y1, material)

    def decal(self, tag, face, column, row, art, **colours):
        """art: rows of characters, each a colour name from `colours`; a dot leaves the texel alone."""
        self.decals.append((tag, face, column, row, art.split(), colours))


def shaped(*pattern, **key):
    return {"type": "minecraft:crafting_shaped", "category": "equipment", "key": key, "pattern": list(pattern)}


def shapeless(*ingredients):
    return {"type": "minecraft:crafting_shapeless", "category": "equipment", "ingredients": list(ingredients)}


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


def build(hat):
    """(model elements, texture rows, texture size, the hat's bounds)."""
    faces = []   # (box index, face, width, height, pixels)
    for index, (bounds, material, rot, sides, tag) in enumerate(hat.boxes):
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
    for index, (bounds, material, rot, sides, tag) in enumerate(hat.boxes):
        element = {"from": list(bounds[:3]), "to": list(bounds[3:]), "faces": {}}
        if rot:
            element["rotation"] = {"origin": list(rot[2]), "axis": rot[0], "angle": rot[1]}
        for letter in sides:
            x, y, w, h = placed[index, FACES[letter]]
            # A hair inside the rectangle, so its neighbours never bleed in
            uv = [(x + 0.02) * 16 / size, (y + 0.02) * 16 / size, (x + w - 0.02) * 16 / size, (y + h - 0.02) * 16 / size]
            element["faces"][FACES[letter]] = {"uv": [round(v, 4) for v in uv], "texture": "#hat"}
        elements.append(element)
    low = [min(b[0][n] for b in hat.boxes) for n in range(3)]
    high = [max(b[0][n + 3] for b in hat.boxes) for n in range(3)]
    return elements, rows, size, (low, high)


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
    h.box(7.75, 13.5, 14, 8.25, 16, 14.5, ("#2a2a30", "cloth"))   # string
    h.box(6.25, 10, 14.2, 9.75, 13.5, 14.3, None, faces="ns", tag="star")
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
    h.mid(5, 5, 8, 11.5, green, dz=7.5)                # the tail falls behind the head
    h.mid(4, 4, 3.5, 9, green, dz=10)
    h.mid(2.5, 2.5, 0.5, 4, green, dz=10)


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
    h.box(15.5, 6, 5.5, 19.5, 10.5, 10.5, red)         # the tip falls to one side
    h.box(16.5, 3.25, 6, 20.5, 6.75, 10, fur)          # pom-pom


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
    h.box(2.5, 8.5, 7.25, 13.5, 8.8, 8.75, ("#d22b2b", "plastic"), rot=("y", 25, (8, 8.5, 8)))
    h.box(7.25, 8.5, 2.5, 8.75, 8.8, 13.5, ("#f2c318", "plastic"), rot=("y", 25, (8, 8.5, 8)))
    h.mid(1.75, 1.75, 8.3, 9.1, ("#2b4bbd", "plastic"))


for make in (hard_hat, wizard_hat, flat_cap, straw_hat, elf_cap, cowboy_hat, baseball_cap, top_hats, plumber_caps,
             chef_hat, crown, santa_hat, viking_helmet, propeller_beanie):
    make()


# ------------------------------------------------------------------ files

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

| To | Do this |
| --- | --- |
| Wear a hat | Right-click with it in your hand, or put it in your helmet slot |
| Put a hat on a drone | Right-click the drone with the hat. On a Taxi drone, **sneak** and right-click |
| Take a hat off a drone | Right-click the drone with **Shears** |

A drone wears one hat at a time. If you **pick the drone up**, or it is destroyed, its hat drops on the
ground. Armor stands can wear hats too.

## The hats

{recipes}
"""


def main():
    java = (ROOT / "src/main/java/com/cyberhats/CyberHats.java").read_text(encoding="utf-8")
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
            "display": {"gui": {"rotation": [30, 225, 0], "translation": [0, lift, 0], "scale": [scale] * 3}},
            "elements": elements})
        write(ASSETS / f"items/{hat.name}.json", {"model": {"type": "minecraft:model", "model": f"cyberhats:item/{hat.name}"}})
        write(DATA / f"recipe/{hat.name}.json", {**hat.recipe, "result": {"id": f"cyberhats:{hat.name}"}})
    write(ASSETS / "lang/en_us.json", {f"item.cyberhats.{hat.name}": hat.title for hat in HATS})
    write(ASSETS / "guides/cyberfarm/handbook/hats.md", PAGE.format(
        ids="\n".join(f"  - cyberhats:{hat.name}" for hat in HATS),
        icons="\n".join(f'  <ItemIcon id="cyberhats:{hat.name}" />' for hat in HATS),
        recipes="\n".join(f'<RecipeFor id="cyberhats:{hat.name}" />' for hat in HATS)))
    print(f"{len(HATS)} hats: " + ", ".join(f'"{hat.name}"' for hat in HATS))


if __name__ == "__main__":
    main()
