#!/usr/bin/env python3
"""Render assets/brain.svg and assets/chip-*.svg from config + activity data.

Stdlib only. The picture is a coronal slice drawn procedurally from a set of
anatomical landmarks: the cortical ribbon is built by offsetting that outline
along its own normals, gyri are a sinusoid riding on the same normals, and the
corona radiata is generated between the ventricles and the ribbon. Each region
stands for one repo and is lit in proportion to recent commits.

Colours follow a four-channel immunofluorescence palette (405/488/555/647),
which is why the field is black: it reads the same in GitHub's light and dark
themes, and it is what this subject actually looks like down a microscope.

Run with no data file to render demo values:  python3 scripts/render_brain.py
"""

import json
import math
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "regions.json").read_text())
ASSETS = ROOT / "assets"

# ---------------------------------------------------------------- palette ---
FIELD = "#07090F"
WHITE_MATTER = "#161D2B"
DEEP_GREY = "#1E2739"
EDGE = "#313D57"
TEXT = "#C9D3E4"
MUTED = "#6E7C96"

W, H = 1200, 570
CX = 600
ZOOM, DROP = 1.07, 18      # slice sits slightly larger and lower in frame
PIVOT_Y = 330
MIDGAP = 3.5          # half-width of the interhemispheric fissure
RIBBON = 18           # cortical thickness in px
GYRI_AMP = 8
GYRI_COUNT = 15

# Right hemisphere outline, traced from coronal landmarks: superior surface,
# lateral convexity, Sylvian notch, temporal lobe, basal surface, medial wall.
OUTLINE = [
    (603, 128), (652, 130), (712, 143), (772, 170), (826, 210), (860, 262),
    (868, 318), (861, 360), (843, 384), (856, 420), (844, 456), (806, 468),
    (774, 447), (766, 410), (730, 424), (694, 444), (656, 454), (622, 452),
    (603, 444), (603, 392), (603, 330), (603, 268), (603, 206), (603, 162),
]


# --------------------------------------------------------------- geometry ---
def catmull(points, samples_per_seg=14, close=True):
    """Densify a polyline into a smooth curve."""
    n = len(points)
    last = n if close else n - 1
    out = []
    for i in range(last):
        p0, p1 = points[(i - 1) % n], points[i % n]
        p2, p3 = points[(i + 1) % n], points[(i + 2) % n]
        for s in range(samples_per_seg):
            t = s / samples_per_seg
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def normals(points):
    """Outward unit normals for a closed polyline wound clockwise in SVG space."""
    n = len(points)
    out = []
    for i in range(n):
        ax, ay = points[(i - 1) % n]
        bx, by = points[(i + 1) % n]
        tx, ty = bx - ax, by - ay
        L = math.hypot(tx, ty) or 1
        out.append((ty / L, -tx / L))
    return out


def poly(points, close=True):
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return d + ("Z" if close else "")


def medial_mask(x):
    """Suppress gyri on the flat medial wall so the two halves stay parallel."""
    return min(1.0, max(0.0, (x - 606) / 26))


def build_hemisphere():
    """Outer (gyral) and inner (white matter) boundaries for the right half."""
    base = catmull(OUTLINE)
    norm = normals(base)
    n = len(base)
    outer, inner = [], []
    for i, ((x, y), (nx, ny)) in enumerate(zip(base, norm)):
        u = i / n
        w = math.sin(2 * math.pi * GYRI_COUNT * u) * medial_mask(x)
        outer.append((x + nx * GYRI_AMP * w, y + ny * GYRI_AMP * w))
        k = RIBBON - 0.45 * GYRI_AMP * w
        inner.append((x - nx * k, y - ny * k))
    return base, outer, inner


BASE, OUTER, INNER = build_hemisphere()


def shift(points, dx):
    return [(x + dx, y) for x, y in points]


def mirror(points):
    return [(2 * CX - x, y) for x, y in points][::-1]


# Lateral ventricle: a thin crescent hugging the midline above the thalamus.
VENTRICLE_PATH = "M616,306 Q644,310 663,330"
VENT_MARGIN = ((616, 310), (694, 358))     # fibre origins run along this line
LESION = (752, 292)


def blob(cx, cy, r, amp, freq, phase=0.0, n=72, squash=1.0):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = r * (1 + amp * math.sin(freq * t + phase) + 0.35 * amp * math.sin(2.7 * freq * t + 1.3))
        pts.append((cx + rr * math.cos(t), cy + rr * squash * math.sin(t)))
    return pts


# --------------------------------------------------------------- activity ---
def load_activity():
    path = ROOT / "data" / "activity.json"
    if path.exists():
        return json.loads(path.read_text())
    demo = {r["id"]: {"repo": r["repo"], "commits": c, "weeks": w}
            for r, c, w in zip(CONFIG["regions"],
                               [23, 11, 4, 1],
                               [[3, 5, 2, 8, 6, 1, 4, 9, 7, 5, 6, 8],
                                [0, 2, 4, 1, 3, 0, 5, 2, 6, 3, 2, 4],
                                [0, 0, 1, 0, 2, 0, 0, 3, 1, 0, 2, 1],
                                [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]])}
    return {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "window_days": CONFIG.get("window_days", 30), "repos": demo}


def intensity(commits):
    """0 for a dormant repo, 1 for a busy one. Log, so one big day can't blow it out."""
    return min(1.0, math.log1p(commits) / math.log1p(24))


# ------------------------------------------------------------------ parts ---
def defs(regions):
    out = ["<defs>"]
    for r in regions:
        out.append(
            f'<filter id="g-{r["id"]}" x="-70%" y="-70%" width="240%" height="240%">'
            f'<feGaussianBlur stdDeviation="{1.2 + 5.0 * r["intensity"]:.1f}" result="b"/>'
            f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        )
    out.append('<radialGradient id="field" cx="50%" cy="46%" r="65%">'
               f'<stop offset="0%" stop-color="#0D131E"/><stop offset="100%" stop-color="{FIELD}"/>'
               '</radialGradient>')
    return "".join(out) + "</defs>"


def styles():
    lx, ly = LESION
    return "<style>" + "".join([
        ".lbl{font-family:'Inter','Helvetica Neue',Helvetica,Arial,sans-serif}",
        ".mono{font-family:'SFMono-Regular',Menlo,Consolas,monospace}",
        ".flow{stroke-dasharray:4 11;animation:flow 4s linear infinite}",
        "@keyframes flow{to{stroke-dashoffset:-30}}",
        f".ring-a{{animation:spin 28s linear infinite;transform-origin:{lx}px {ly}px}}",
        f".ring-b{{animation:spinr 38s linear infinite;transform-origin:{lx}px {ly}px}}",
        "@keyframes spin{to{transform:rotate(360deg)}}",
        "@keyframes spinr{to{transform:rotate(-360deg)}}",
        ".pulse{animation:breathe 5s ease-in-out infinite}",
        "@keyframes breathe{0%,100%{opacity:.5}50%{opacity:1}}",
        "@media (prefers-reduced-motion:reduce){.flow,.ring-a,.ring-b,.pulse{animation:none}}",
    ]) + "</style>"


def both(points):
    """The right hemisphere shape and its mirror image."""
    return [shift(points, MIDGAP), mirror(shift(points, -MIDGAP))]


def tissue():
    """White matter, deep grey nuclei, corpus callosum: unlabelled anatomy."""
    parts = []
    for pts in both(INNER):
        parts.append(f'<path d="{poly(pts)}" fill="{WHITE_MATTER}"/>')
    for sx in (1, -1):
        cx = CX + sx * 112
        parts.append(f'<ellipse cx="{cx}" cy="322" rx="34" ry="26" fill="{DEEP_GREY}" '
                     f'transform="rotate({-18 * sx} {cx} 322)"/>')
        parts.append(f'<ellipse cx="{CX + sx * 66}" cy="366" rx="42" ry="28" fill="{DEEP_GREY}"/>')
    parts.append(f'<path d="M522,296 C556,264 644,264 678,296 C644,280 556,280 522,296Z" '
                 f'fill="{EDGE}" opacity="0.95"/>')
    return "".join(parts)


def cortex_ribbon(region):
    i, col = region["intensity"], region["color"]
    parts = []
    outers, inners = both(OUTER), both(INNER)
    for outer, inner in zip(outers, inners):
        parts.append(
            f'<path d="{poly(outer)} {poly(inner)}" fill-rule="evenodd" fill="{col}" '
            f'fill-opacity="{0.06 + 0.20 * i:.2f}" stroke="{col}" stroke-width="1.3" '
            f'stroke-opacity="{0.26 + 0.48 * i:.2f}" stroke-linejoin="round"/>'
        )
    return f'<g filter="url(#g-{region["id"]})">{"".join(parts)}</g>'


def tracts(region):
    """Corona radiata: fibres from the ventricle margin out to the ribbon."""
    i, col = region["intensity"], region["color"]
    n = len(INNER)
    (mx0, my0), (mx1, my1) = VENT_MARGIN
    count = 13
    fibres = []
    for side in (1, -1):
        for k in range(count):
            u = k / (count - 1)
            idx = int(n * (0.03 + 0.40 * u))
            ex, ey = INNER[idx]
            ex = ex + MIDGAP if side == 1 else 2 * CX - (ex - MIDGAP)
            sx = mx0 + (mx1 - mx0) * u
            sy = my0 + (my1 - my0) * u
            sx = sx if side == 1 else 2 * CX - sx
            dx, dy = ex - sx, ey - sy
            L = math.hypot(dx, dy) or 1
            bow = (14 + 34 * u) * side
            cx1 = (sx + ex) / 2 - dy / L * bow
            cy1 = (sy + ey) / 2 + dx / L * bow
            fibres.append((sx, sy, cx1, cy1, ex, ey, k))
    faint = "".join(f'<path d="M{a:.1f},{b:.1f} Q{c:.1f},{d:.1f} {e:.1f},{f:.1f}"/>'
                    for a, b, c, d, e, f, _ in fibres)
    moving = "".join(
        f'<path class="flow" d="M{a:.1f},{b:.1f} Q{c:.1f},{d:.1f} {e:.1f},{f:.1f}" '
        f'style="animation-duration:{6.0 - 3.0 * i:.1f}s;animation-delay:{k * 0.15:.2f}s"/>'
        for a, b, c, d, e, f, k in fibres)
    nodes = "".join(f'<circle cx="{e:.1f}" cy="{f:.1f}" r="{1.7 + 1.5 * i:.1f}"/>'
                    for a, b, c, d, e, f, k in fibres if k % 3 != 1)
    return (
        f'<g filter="url(#g-{region["id"]})" fill="none" stroke="{col}" stroke-linecap="round">'
        f'<g stroke-width="1" stroke-opacity="{0.08 + 0.22 * i:.2f}">{faint}</g>'
        f'<g stroke-width="{1.0 + 0.8 * i:.1f}" stroke-opacity="{0.22 + 0.55 * i:.2f}">{moving}</g>'
        f'<g class="pulse" fill="{col}" stroke="none" fill-opacity="{0.3 + 0.6 * i:.2f}">{nodes}</g>'
        f'</g>'
    )


def ventricles_svz(region):
    """A thin CSF slit lined by a glowing subventricular zone."""
    i, col = region["intensity"], region["color"]
    parts = []
    for d, flip in ((VENTRICLE_PATH, False), (VENTRICLE_PATH, True)):
        tr = (f' transform="translate({2 * CX - MIDGAP},0) scale(-1,1)"' if flip
              else f' transform="translate({MIDGAP},0)"')
        parts.append(
            f'<g{tr}><path d="{d}" fill="none" stroke="{col}" stroke-width="11" '
            f'stroke-linecap="round" stroke-opacity="{0.22 + 0.55 * i:.2f}"/>'
            f'<path d="{d}" fill="none" stroke="#080D16" stroke-width="6.5" '
            f'stroke-linecap="round"/></g>'
        )
    return f'<g filter="url(#g-{region["id"]})">{"".join(parts)}</g>'


def lesion(region):
    """A lesion with two contested margins, drifting in opposite directions."""
    i, col = region["intensity"], region["color"]
    cx, cy = LESION
    core = poly(catmull(blob(cx, cy, 33, 0.13, 6, 0.4, n=26, squash=0.88), 6))
    m1 = poly(catmull(blob(cx, cy, 44, 0.10, 5, 1.1, n=24, squash=0.9), 6))
    m2 = poly(catmull(blob(cx, cy, 52, 0.08, 7, 2.4, n=24, squash=0.92), 6))
    return (
        f'<g filter="url(#g-{region["id"]})">'
        f'<path d="{core}" fill="{col}" fill-opacity="{0.15 + 0.4 * i:.2f}"/>'
        f'<path class="ring-a" d="{m1}" fill="none" stroke="{col}" stroke-width="1.7" '
        f'stroke-dasharray="9 9" stroke-opacity="{0.3 + 0.55 * i:.2f}"/>'
        f'<path class="ring-b" d="{m2}" fill="none" stroke="{col}" stroke-width="1.1" '
        f'stroke-dasharray="3 11" stroke-opacity="{0.22 + 0.5 * i:.2f}"/></g>'
    )


# ----------------------------------------------------------------- labels ---
SLOTS = {
    "synapse":       dict(x=44,   y=214, side="left",  anchor=(392, 214)),
    "cortex-garden": dict(x=44,   y=418, side="left",  anchor=(346, 404)),
    "counterglia":   dict(x=1156, y=206, side="right", anchor=(806, 274)),
    "brain-map":     dict(x=1156, y=418, side="right", anchor=(684, 322)),
}


def in_frame(px, py):
    """Move a point through the same transform applied to the slice."""
    return CX + (px - CX) * ZOOM, PIVOT_Y + (py - PIVOT_Y) * ZOOM + DROP


def label(region, window):
    slot = SLOTS.get(region["id"])
    if not slot:
        return ""
    x, y, side = slot["x"], slot["y"], slot["side"]
    ax, ay = in_frame(*slot["anchor"])
    bend = x + (168 if side == "left" else -168)
    align = "start" if side == "left" else "end"
    n = region["commits"]
    return (
        f'<polyline points="{x},{y + 6} {bend},{y + 6} {ax:.1f},{ay:.1f}" fill="none" '
        f'stroke="{region["color"]}" stroke-opacity="0.38" stroke-width="1"/>'
        f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="2.6" fill="{region["color"]}"/>'
        f'<text class="lbl" x="{x}" y="{y - 8}" text-anchor="{align}" fill="{TEXT}" '
        f'font-size="20" font-weight="600">{region["label"]}</text>'
        f'<text class="lbl" x="{x}" y="{y + 34}" text-anchor="{align}" fill="{MUTED}" '
        f'font-size="13.5">{region["blurb"]}</text>'
        f'<text class="mono" x="{x}" y="{y + 55}" text-anchor="{align}" fill="{region["color"]}" '
        f'fill-opacity="0.9" font-size="12">{n} commit{"" if n == 1 else "s"} / {window}d</text>'
    )


# ------------------------------------------------------------------ build ---
def build_brain(regions, meta):
    by = {r["anatomy"]: r for r in regions}
    slice_layers = [tissue()]
    for key, fn in (("tracts", tracts), ("cortex", cortex_ribbon),
                    ("svz", ventricles_svz), ("lesion", lesion)):
        if key in by:
            slice_layers.append(fn(by[key]))
    layers = [
        f'<rect width="{W}" height="{H}" fill="url(#field)"/>',
        f'<g transform="translate({CX},{PIVOT_Y + DROP}) scale({ZOOM}) '
        f'translate({-CX},{-PIVOT_Y})">{"".join(slice_layers)}</g>',
    ]

    header = (
        f'<text class="lbl" x="44" y="60" fill="{TEXT}" font-size="30" font-weight="650">'
        f'{CONFIG["title"]}</text>'
        f'<text class="lbl" x="44" y="88" fill="{MUTED}" font-size="14.5">{CONFIG["subtitle"]}</text>'
    )
    footer = (
        f'<line x1="44" y1="524" x2="104" y2="524" stroke="{MUTED}" stroke-opacity="0.7" '
        f'stroke-width="3"/>'
        f'<text class="mono" x="44" y="544" fill="{MUTED}" font-size="11">1 cm</text>'
        f'<text class="mono" x="{W - 44}" y="544" text-anchor="end" fill="{MUTED}" font-size="11">'
        f'updated {meta["generated"]}, brightness tracks commits in the last '
        f'{meta["window_days"]} days</text>'
    )
    labels = "".join(label(r, meta["window_days"]) for r in regions)
    alt = ", ".join(f'{r["label"]} {r["commits"]} commits' for r in regions)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="A coronal brain slice in which each region stands for one '
        f'project, lit by recent activity: {alt}.">'
        f'<title>Projects as brain regions</title>{defs(regions)}{styles()}'
        f'{"".join(layers)}{labels}{header}{footer}</svg>'
    )


def build_chip(region):
    w, h = 360, 78
    weeks = region["weeks"] or [0] * 12
    top = max(max(weeks), 1)
    pts = " ".join(f"{218 + k * (126 / max(len(weeks) - 1, 1)):.1f},{60 - (v / top) * 22:.1f}"
                   for k, v in enumerate(weeks))
    i, n, col = region["intensity"], region["commits"], region["color"]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{region["label"]}: {n} recent commits">'
        f"<style>.l{{font-family:'Inter','Helvetica Neue',Helvetica,Arial,sans-serif}}"
        f".m{{font-family:'SFMono-Regular',Menlo,Consolas,monospace}}</style>"
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="#0C1119" '
        f'stroke="{col}" stroke-opacity="{0.25 + 0.5 * i:.2f}"/>'
        f'<rect x="0" y="16" width="3" height="{h-32}" rx="1.5" fill="{col}"/>'
        f'<text class="l" x="20" y="34" fill="{TEXT}" font-size="16" font-weight="600">'
        f'{region["label"]}</text>'
        f'<text class="l" x="20" y="56" fill="{MUTED}" font-size="11.5">{region["blurb"]}</text>'
        f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6" '
        f'stroke-opacity="0.75" stroke-linejoin="round"/>'
        f'<text class="m" x="{w-16}" y="32" text-anchor="end" fill="{col}" font-size="13">{n}</text>'
        f'</svg>'
    )


def main():
    activity = load_activity()
    repos = activity["repos"]
    regions = []
    for r in CONFIG["regions"]:
        d = repos.get(r["id"], {})
        regions.append({**r, "commits": d.get("commits", 0), "weeks": d.get("weeks", []),
                        "intensity": intensity(d.get("commits", 0))})
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "brain.svg").write_text(build_brain(regions, activity))
    for r in regions:
        (ASSETS / f'chip-{r["id"]}.svg').write_text(build_chip(r))
    print(f"wrote assets/brain.svg and {len(regions)} chips")


if __name__ == "__main__":
    main()
