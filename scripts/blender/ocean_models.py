"""Build, animate and render the ocean-depth episode's 3D models (run inside Blender).

    blender -b --factory-startup -P scripts/blender/ocean_models.py -- <out_dir> <texture_dir> [names...]

Makes four models from scratch (no downloaded assets) and renders each as a
loop of transparent PNGs, <out_dir>/<name>/000.png ..., lit the way the dive
lights them: a lamp up and to the left of the lens, dim blue water all round,
a cool rim from above.

    diver      a scuba diver in a flutter kick, bubbles rising      (40 frames)
    whale      Cuvier's beaked whale, tail beating up and down      (48 frames)
    snailfish  the hadal snailfish (Pseudoliparis) filmed at 8,336 m (48 frames)
    titanic    the Titanic's wrecked bow, resting on the seabed     (1 frame)

Every model is about one unit long, nose towards +X, up +Z. Nothing is rigged:
each frame the model is rebuilt in its next pose, which keeps the motion exact
and loopable. Painted textures (scars, portholes, rust) come from
scripts/make_ocean_models.py, which also runs this.
"""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "."
TEX = argv[1] if len(argv) > 1 else "."
ONLY = argv[2:]
WIDTH = int(os.environ.get("OCEAN_SPRITE_W", "1792"))
SAMPLES = int(os.environ.get("OCEAN_SAMPLES", "220"))
EVERY = int(os.environ.get("OCEAN_EVERY", "1"))        # render every n-th frame (previews)
TAU = 2 * math.pi

LIVE = []                                               # this frame's objects (cleared between frames)


# --------------------------------------------------------------------------- #
# Scene, mesh and material helpers
# --------------------------------------------------------------------------- #
def new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    LIVE.clear()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == kind
                    sc.cycles.device = "GPU"
                    break
            except Exception:
                continue
    except Exception as exc:                       # no GPU: the CPU still renders it
        print("GPU not set:", exc)
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.render.use_persistent_data = True
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    world = bpy.data.worlds.new("water")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.035, 0.085, 0.16, 1)
    bg.inputs["Strength"].default_value = 1.0
    sc.world = world
    return sc


def keep(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def link(obj):
    LIVE.append(keep(obj))
    return obj


def clear():
    """Remove this frame's objects and their meshes."""
    for ob in LIVE:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0:
            (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.curves).remove(data)
    LIVE.clear()


def finish(name, bm, mat=None, subsurf=2, smooth=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new(name, me))
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    if subsurf:
        m = ob.modifiers.new("subsurf", "SUBSURF")
        m.levels = m.render_levels = subsurf
    if mat:
        me.materials.append(mat)
    return ob


def loft(name, rings, mat=None, subsurf=2, cap=True, rest=None):
    """A skin over a list of rings (each a list of points, all the same length).
    `rest`: the same rings in the resting pose. Their (x, z) go into a UV map
    called "rest", so painted markings stay put on the skin while the body bends."""
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(vr[0])
    where = {}
    if rest:
        for ring_v, ring_r in zip(vr, rest):
            for v, r in zip(ring_v, ring_r):
                where[v] = (r[0], r[2])
    for a, b in zip(vr, vr[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    if cap:
        for k, ring_v in ((0, vr[0]), (-1, vr[-1])):
            c = bm.verts.new(sum((v.co for v in ring_v), Vector()) / n)
            if rest:
                where[c] = (sum(r[0] for r in rest[k]) / n, sum(r[2] for r in rest[k]) / n)
            for i in range(n):
                bm.faces.new((ring_v[i], ring_v[(i + 1) % n], c))
    if rest:
        uv = bm.loops.layers.uv.new("rest")
        for f in bm.faces:
            for lp in f.loops:
                lp[uv].uv = where[lp.vert]
    return finish(name, bm, mat, subsurf)


def ring(centre, ax1, ax2, a, b, n=20, power=2.0, flat=0.0):
    """Superellipse of half-axes a (along ax1) and b (along ax2). `flat` > 0
    squashes the lower half (a flatter belly)."""
    out = []
    for i in range(n):
        th = TAU * i / n
        c, s = math.cos(th), math.sin(th)
        x = math.copysign(abs(c) ** (2 / power), c) * a
        y = math.copysign(abs(s) ** (2 / power), s) * b
        if y < 0:
            y *= 1 - flat
        out.append(Vector(centre) + Vector(ax1) * x + Vector(ax2) * y)
    return out


def curve(pts, smooth=0.035):
    """Smooth 1-D profile through (s, value) points, s in 0..1."""
    px = np.array([p[0] for p in pts], float)
    py = np.array([p[1] for p in pts], float)
    xs = np.linspace(0, 1, 600)
    ys = np.interp(xs, px, py)
    k = max(3, int(smooth * 600) | 1)
    win = np.hanning(k + 2)[1:-1]
    win /= win.sum()
    pad = np.concatenate([np.full(k, ys[0]), ys, np.full(k, ys[-1])])
    ys2 = np.convolve(pad, win, mode="same")[k:-k]
    ys2[0], ys2[-1] = ys[0], ys[-1]
    return lambda s: float(np.interp(s, xs, ys2))


def fin(name, root, span, chord, n, chord_at, sweep_at, thick=0.12, mat=None, bend_at=None, subsurf=2, seg=14):
    """A fin or fluke: aerofoil-like rings along `span` (a vector, tip = root + span).
    chord_at(t), sweep_at(t) give chord length and trailing offset at t in 0..1."""
    span, chord = Vector(span), Vector(chord).normalized()
    up = span.normalized().cross(chord).normalized()
    rings = []
    for i in range(n + 1):
        t = i / n
        c = max(1e-4, chord_at(t))
        centre = Vector(root) + span * t - chord * sweep_at(t)
        if bend_at:
            centre += up * bend_at(t)
        rings.append(ring(centre, chord, up, c / 2, max(1e-4, c * thick / 2), seg, power=1.7))
    return loft(name, rings, mat, subsurf)


def tube(name, pts, radii, mat=None, n=14, subsurf=2, side=(0, 1, 0)):
    """A limb: a tube along a polyline. radii: (r_side, r_up) per point, or a number."""
    pts = [Vector(p) for p in pts]
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        d = (b - a).normalized()
        s = Vector(side) - d * Vector(side).dot(d)
        s = s.normalized() if s.length > 1e-5 else d.orthogonal().normalized()
        u = d.cross(s).normalized()
        r = radii[i]
        rs, ru = (r, r) if isinstance(r, (int, float)) else r
        rings.append(ring(p, s, u, rs, ru, n))
    return loft(name, rings, mat, subsurf)


def sphere(name, loc, scale, mat=None, seg=32):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    ob = finish(name, bm, mat, subsurf=0)
    ob.location = loc
    ob.scale = scale if isinstance(scale, (tuple, list, Vector)) else (scale,) * 3
    return ob


def box(name, lo, hi, mat=None, bevel=0.0, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    ob = finish(name, bm, mat, subsurf=0, smooth=False)
    lo, hi = Vector(lo), Vector(hi)
    ob.location = (lo + hi) / 2
    ob.scale = hi - lo
    if rot:
        ob.rotation_euler = rot
    if bevel:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
    return ob


def cylinder(name, a, b, r, mat=None, seg=32, r2=None):
    a, b = Vector(a), Vector(b)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2,
                          depth=(b - a).length)
    ob = finish(name, bm, mat, subsurf=0)
    ob.location = (a + b) / 2
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = (b - a).to_track_quat("Z", "Y")
    return ob


def wire(name, pts, r, mat=None):
    """A hose, stay, rail or fin ray: a smooth round curve through pts."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 4
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1.0)
    sp.use_endpoint_u = True
    sp.order_u = min(4, len(pts))
    ob = link(bpy.data.objects.new(name, cu))
    if mat:
        cu.materials.append(mat)
    return ob


class Mat:
    """A Principled material with a few node shortcuts. With uv=True its
    textures follow the "rest" UV map (see loft) instead of object space."""

    def __init__(self, name, color=(0.5, 0.5, 0.5), rough=0.5, uv=False, **inputs):
        self.m = bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.nt = self.m.node_tree
        self.b = self.nt.nodes["Principled BSDF"]
        self.uv = uv
        self.set(**{"Base Color": (*color, 1), "Roughness": rough}, **inputs)

    def set(self, **inputs):
        for k, v in inputs.items():
            self.b.inputs[k.replace("_", " ")].default_value = v
        return self

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            if k.startswith("in_"):
                n.inputs[k[3:].replace("_", " ")].default_value = v
            else:
                setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def where(self):
        """Position to texture by: object space, or the resting pose (x, 0, z)."""
        if not self.uv:
            return self.node("ShaderNodeTexCoord").outputs["Object"]
        um = self.node("ShaderNodeUVMap", uv_map="rest")
        sep = self.node("ShaderNodeSeparateXYZ")
        self.link(um.outputs["UV"], sep.inputs["Vector"])
        com = self.node("ShaderNodeCombineXYZ")
        self.link(sep.outputs["X"], com.inputs["X"])
        self.link(sep.outputs["Y"], com.inputs["Z"])
        return com.outputs["Vector"]

    def coords(self, scale=(1, 1, 1), loc=(0, 0, 0)):
        mp = self.node("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = scale
        mp.inputs["Location"].default_value = loc
        self.link(self.where(), mp.inputs["Vector"])
        return mp.outputs["Vector"]

    def noise(self, scale, detail=6.0, rough=0.55, vec=None, stretch=(1, 1, 1)):
        n = self.node("ShaderNodeTexNoise", in_Scale=scale, in_Detail=detail, in_Roughness=rough)
        self.link(vec or self.coords(stretch), n.inputs["Vector"])
        return n.outputs["Fac"]

    def ramp(self, fac, stops):
        """stops: [(position, (r, g, b))]"""
        r = self.node("ShaderNodeValToRGB")
        el = r.color_ramp.elements
        while len(el) < len(stops):
            el.new(0.5)
        for e, (pos, col) in zip(el, stops):
            e.position = pos
            e.color = (*col, 1)
        self.link(fac, r.inputs["Fac"])
        return r.outputs["Color"]

    def mix(self, fac, a, b, kind="MIX"):
        m = self.node("ShaderNodeMixRGB", blend_type=kind)
        for sock, v in ((m.inputs["Fac"], fac), (m.inputs["Color1"], a), (m.inputs["Color2"], b)):
            if isinstance(v, (int, float)):
                sock.default_value = v
            elif isinstance(v, tuple):
                sock.default_value = (*v, 1) if len(v) == 3 else v
            else:
                self.link(v, sock)
        return m.outputs["Color"]

    def axis(self, which, lo, hi):
        """0..1 along an axis between lo and hi."""
        sep = self.node("ShaderNodeSeparateXYZ")
        self.link(self.where(), sep.inputs["Vector"])
        mr = self.node("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = lo
        mr.inputs["From Max"].default_value = hi
        self.link(sep.outputs[which], mr.inputs["Value"])
        return mr.outputs["Result"]

    def image(self, path, x0, x1, z0, z1):
        """A painted texture projected from the side: x in x0..x1 -> u, z in z0..z1 -> v."""
        img = bpy.data.images.load(path)
        com = self.node("ShaderNodeCombineXYZ")
        self.link(self.axis("X", x0, x1), com.inputs["X"])
        self.link(self.axis("Z", z0, z1), com.inputs["Y"])
        t = self.node("ShaderNodeTexImage", image=img, extension="EXTEND")
        self.link(com.outputs["Vector"], t.inputs["Vector"])
        return t.outputs["Color"]

    def base(self, sock):
        self.link(sock, self.b.inputs["Base Color"])
        return self

    def bump(self, height, strength=0.3, distance=0.01):
        bp = self.node("ShaderNodeBump")
        bp.inputs["Strength"].default_value = strength
        bp.inputs["Distance"].default_value = distance
        self.link(height, bp.inputs["Height"])
        self.link(bp.outputs["Normal"], self.b.inputs["Normal"])
        return self

    def add(self, a, b, fac=1.0):
        return self.mix(fac, a, b, "ADD")

    def cells(self, scale, vec=None, stretch=(1, 1, 1)):
        """Cell edges (cracks, wrinkles, pores): 0 in a cell, rising to its border."""
        v = self.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", in_Scale=scale)
        self.link(vec or self.coords(stretch), v.inputs["Vector"])
        return self.ramp(v.outputs["Distance"], [(0.0, (0, 0, 0)), (0.12, (1, 1, 1))])

    def into(self, name, sock):
        self.link(sock, self.b.inputs[name])
        return self


def _extent(right, up, d):
    """Bounds of this frame's objects along the camera's axes."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    xs, ys, ds = [], [], []
    for ob in LIVE:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        arr = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", arr)
        for v in arr.reshape(-1, 3)[:: max(1, len(me.vertices) // 6000)]:
            w = mw @ Vector(v)
            xs.append(w.dot(right))
            ys.append(w.dot(up))
            ds.append(w.dot(d))
        ev.to_mesh_clear()
    return min(xs), max(xs), min(ys), max(ys), max(ds)


def film(name, build, frames, az=22.0, el=13.0, margin=0.05, key=60.0, rim=1.2, top=0.0, caustics=0.0, persp=None,
         hard=0.26):
    """Render build(phase) for phase = 0 .. 1 as <OUT>/<name>/NNN.png, every frame
    in the same framing. The camera is to the side (-Y), swung `az` degrees
    towards the nose and `el` up; the key light is the dive's lamp, up and left
    of the lens; `top` adds daylight from above and `caustics` ripples it.
    `persp` = (camera position, target, field of view in degrees, width, height)
    swaps the flat-on camera for a close one with perspective. `hard`: the key
    lamp's size relative to the model (small = crisp highlights and shadows)."""
    sc = bpy.context.scene
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    co = keep(bpy.data.objects.new("cam", cam))
    co.rotation_mode = "QUATERNION"
    co.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    sc.camera = co
    bpy.context.view_layer.update()
    right = co.matrix_world.to_3x3() @ Vector((1, 0, 0))
    up = co.matrix_world.to_3x3() @ Vector((0, 1, 0))
    box_ = None
    for ph in ((0.0, 0.25, 0.5, 0.75) if frames > 1 else (0.0,)):       # one framing that fits every pose
        build(ph)
        b = _extent(right, up, d)
        box_ = b if box_ is None else (min(box_[0], b[0]), max(box_[1], b[1]), min(box_[2], b[2]),
                                       max(box_[3], b[3]), max(box_[4], b[4]))
        clear()
    x0, x1, y0, y1, dmax = box_
    w, h = (x1 - x0) * (1 + 2 * margin), (y1 - y0) + (x1 - x0) * 2 * margin
    centre = right * ((x0 + x1) / 2) + up * ((y0 + y1) / 2)
    co.location = centre + d * (dmax + 6.0)
    cam.ortho_scale = w
    cam.clip_end = 60
    sc.render.resolution_x = WIDTH
    sc.render.resolution_y = int(math.ceil(WIDTH * h / w / 16) * 16)
    span = x1 - x0
    if persp:
        loc, target, fov, rx, ry = persp
        cam.type = "PERSP"
        cam.sensor_fit = "HORIZONTAL"
        cam.angle = math.radians(fov)
        cam.clip_start = 0.005
        co.location = loc
        d = (Vector(loc) - Vector(target)).normalized()
        co.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
        bpy.context.view_layer.update()
        right = co.matrix_world.to_3x3() @ Vector((1, 0, 0))
        up = co.matrix_world.to_3x3() @ Vector((0, 1, 0))
        centre = Vector(target)
        span = (Vector(loc) - Vector(target)).length * 1.1
        sc.render.resolution_x, sc.render.resolution_y = rx, ry

    def lamp(nm, kind, loc, energy, color, size=1.0):
        li = bpy.data.lights.new(nm, kind)
        li.energy = energy
        li.color = color
        if kind == "AREA":
            li.size = size
        lo = keep(bpy.data.objects.new(nm, li))
        lo.location = loc
        lo.rotation_mode = "QUATERNION"
        lo.rotation_quaternion = (centre - Vector(loc)).to_track_quat("-Z", "Y")
        return li
    lamp("key", "AREA", centre + d * 2.3 * span - right * 0.95 * span + up * 0.9 * span, key * span * span,
         (1.0, 0.97, 0.90), size=hard * span)
    lamp("rim", "SUN", centre - d * 2.0 + up * 3.0 + right * 0.6, rim, (0.55, 0.82, 1.0))
    if top:
        lamp("top", "SUN", centre + up * 5.0 + d * 0.8, top, (0.70, 0.92, 1.0))
    ripple = None
    if caustics:
        # daylight broken up by the waves above: a spot whose brightness is a
        # moving cell pattern. Two copies of the pattern cross-fade, so it loops.
        li = lamp("caustics", "SPOT", centre + Vector((0.25 * span, 0.1 * span, 3.2 * span)), caustics * span * span,
                  (0.72, 0.95, 1.0))
        li.spot_size = math.radians(42)
        li.spot_blend = 0.6
        li.shadow_soft_size = 0.01
        li.use_nodes = True
        nt = li.node_tree
        em = nt.nodes["Emission"]
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (26.0, 26.0, 26.0)
        nt.links.new(tc.outputs["Normal"], mp.inputs["Vector"])
        vs = []
        for _ in range(2):
            v = nt.nodes.new("ShaderNodeTexVoronoi")
            v.voronoi_dimensions = "4D"
            v.feature = "SMOOTH_F1"
            v.inputs["Smoothness"].default_value = 0.35
            nt.links.new(mp.outputs["Vector"], v.inputs["Vector"])
            vs.append(v)
        mx = nt.nodes.new("ShaderNodeMixRGB")
        nt.links.new(vs[0].outputs["Distance"], mx.inputs["Color1"])
        nt.links.new(vs[1].outputs["Distance"], mx.inputs["Color2"])
        rp = nt.nodes.new("ShaderNodeValToRGB")
        rp.color_ramp.elements[0].position = 0.30
        rp.color_ramp.elements[0].color = (0.06, 0.06, 0.06, 1)
        rp.color_ramp.elements[1].position = 0.78
        rp.color_ramp.elements[1].color = (1, 1, 1, 1)
        nt.links.new(mx.outputs["Color"], rp.inputs["Fac"])
        nt.links.new(rp.outputs["Color"], em.inputs["Strength"])
        em.inputs["Strength"].default_value = 1.0
        ripple = (vs, mx)
    os.makedirs(os.path.join(OUT, name), exist_ok=True)
    for i in range(0, frames, EVERY):
        ph = i / frames
        if ripple:
            vs, mx = ripple
            vs[0].inputs["W"].default_value = ph * 0.9
            vs[1].inputs["W"].default_value = (ph - 1.0) * 0.9
            mx.inputs["Fac"].default_value = ph
        build(ph)
        sc.render.filepath = os.path.join(OUT, name, f"{i:03d}.png")
        bpy.ops.render.render(write_still=True)
        clear()
    print("rendered", name, frames, sc.render.resolution_x, sc.render.resolution_y)


# --------------------------------------------------------------------------- #
# Cuvier's beaked whale: the tail stock and flukes beat up and down
# --------------------------------------------------------------------------- #
def whale():
    new_scene()
    skin = Mat("whale skin", rough=0.34, uv=True)
    skin.set(**{"Coat Weight": 0.45, "Coat Roughness": 0.10, "Subsurface Weight": 0.06, "Roughness": 0.30})
    tex = skin.image(os.path.join(TEX, "whale.png"), -0.5, 0.5, -0.115, 0.115)
    mott = skin.noise(9.0, 5.0, 0.6, stretch=(1.0, 2.0, 2.0))
    skin.base(skin.mix(skin.ramp(mott, [(0.35, (0.0, 0.0, 0.0)), (0.75, (0.22, 0.22, 0.22))]), tex, (1, 1, 1), "MULTIPLY"))
    relief = skin.add(skin.add(skin.noise(60.0, 4.0, 0.6), skin.noise(420.0, 6.0, 0.7), 0.6),
                      skin.cells(90.0, stretch=(1.0, 1.0, 3.0)), 0.07)
    skin.bump(relief, 0.13, 0.0026)
    fin_m = Mat("whale fin", (0.15, 0.13, 0.12), 0.50)
    fin_m.set(**{"Coat Weight": 0.12, "Coat Roughness": 0.35})
    eye = Mat("eye", (0.01, 0.01, 0.012), 0.08)
    dark = Mat("mouth", (0.02, 0.018, 0.018), 0.6)

    # body: s = 0 at the beak tip, 1 at the tail
    hh = curve([(0, 0.004), (0.035, 0.019), (0.075, 0.040), (0.14, 0.068), (0.26, 0.088), (0.40, 0.094),
                (0.56, 0.086), (0.70, 0.066), (0.82, 0.040), (0.91, 0.021), (0.97, 0.012), (1, 0.007)])
    ww = curve([(0, 0.003), (0.035, 0.015), (0.075, 0.036), (0.14, 0.062), (0.26, 0.082), (0.40, 0.086),
                (0.56, 0.074), (0.70, 0.050), (0.82, 0.024), (0.91, 0.010), (0.97, 0.006), (1, 0.004)])
    cz = curve([(0, -0.016), (0.05, -0.012), (0.12, -0.004), (0.4, 0.0), (0.8, 0.004), (1, 0.006)])

    def build(ph):
        def dz(s):                                   # the swimming wave: grows towards the tail
            back = max(0.0, (s - 0.26) / 0.74) ** 1.9
            head = max(0.0, (0.26 - s) / 0.26) ** 2
            return 0.060 * back * math.sin(TAU * (ph - 0.52 * s)) - 0.008 * head * math.sin(TAU * ph - 0.5)

        def pitch(s):                                # the body's tilt there, radians (nose-up positive)
            return math.atan2(dz(s - 0.01) - dz(s + 0.01), 0.02)
        rings, rest = [], []
        for i in range(46):
            s = (i / 45) ** 1.08
            th = pitch(s)
            ax = Vector((math.sin(th), 0, math.cos(th)))             # rings stay square to the spine
            rings.append(ring((0.5 - s, 0, cz(s) + dz(s)), (0, 1, 0), ax, ww(s), hh(s), 24, power=2.15, flat=0.06))
            rest.append(ring((0.5 - s, 0, cz(s)), (0, 1, 0), (0, 0, 1), ww(s), hh(s), 24, power=2.15, flat=0.06))
        loft("body", rings, skin.m, rest=rest)
        # flukes: wide, no notch; they feather against the stroke
        st = 0.978
        th = pitch(st) + 0.42 * math.cos(TAU * (ph - 0.52 * st))
        chord = (math.cos(th), 0, math.sin(th))
        for sgn in (1, -1):
            fin("fluke", (-0.478, 0, 0.006 + dz(st)), (0, sgn * 0.135, 0), chord, 12,
                lambda t: 0.105 * (1 - t ** 1.7) ** 0.75 + 0.004, lambda t: 0.070 * t ** 1.5, 0.11, fin_m.m)
        # small falcate dorsal fin, two thirds of the way back
        sd = 0.665
        th = pitch(sd)
        fin("dorsal", (-0.165, 0, 0.066 + dz(sd)), (-0.050 * math.sin(th), 0, 0.050 * math.cos(th)),
            (math.cos(th), 0, math.sin(th)), 9,
            lambda t: 0.090 * (1 - t) ** 0.7 + 0.004, lambda t: 0.052 * t ** 1.4, 0.13, fin_m.m)
        # small flippers, sculling a little
        scull = 0.012 * math.sin(TAU * ph + 1.0)
        for sgn in (1, -1):
            fin("flipper", (0.235, sgn * 0.070, -0.050 + dz(0.265)), (-0.060, sgn * (0.028 + scull), -0.040 - scull),
                (1, 0, 0.35), 9, lambda t: 0.050 * (1 - t ** 2.2) ** 0.8 + 0.003, lambda t: 0.012 * t, 0.16, fin_m.m)
        sphere("blowhole", (0.385, 0, cz(0.115) + hh(0.115) * 0.985 + dz(0.115)), (0.0075, 0.0052, 0.0016), dark.m)
        for sgn in (1, -1):                                  # the two throat grooves
            wire("groove", [(0.452, sgn * 0.010, cz(0.048) - hh(0.048) * 0.86 + dz(0.048)),
                            (0.415, sgn * 0.022, cz(0.085) - hh(0.085) * 0.84 + dz(0.085)),
                            (0.378, sgn * 0.040, cz(0.122) - hh(0.122) * 0.74 + dz(0.122))], 0.0012, dark.m)
        for sgn in (1, -1):
            hz = dz(0.11)
            sphere("eye", (0.388, sgn * 0.0605, -0.008 + hz), 0.0050, eye.m)
            wire("mouth", [(0.497, sgn * 0.004, -0.017 + dz(0.0)), (0.455, sgn * 0.026, -0.022 + dz(0.045)),
                           (0.420, sgn * 0.046, -0.021 + dz(0.08)), (0.396, sgn * 0.056, -0.015 + hz)], 0.0016, dark.m)
    film("whale", build, 48, az=20, el=12, key=60, rim=1.3)


# --------------------------------------------------------------------------- #
# Hadal snailfish (Pseudoliparis): broad soft head, ribbon tail edged with fin,
# big fan pectorals with free lower rays, a slow wiggle
# --------------------------------------------------------------------------- #
def snailfish():
    new_scene()
    body = Mat("snailfish", (0.96, 0.80, 0.80), 0.34, uv=True)
    body.set(**{"Subsurface Weight": 0.55, "Subsurface Scale": 0.018, "Coat Weight": 0.55, "Coat Roughness": 0.12,
                "Transmission Weight": 0.05, "IOR": 1.36})
    body.b.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.35)
    along = body.axis("X", -0.5, 0.5)
    col = body.ramp(along, [(0.0, (0.99, 0.93, 0.93)), (0.55, (0.97, 0.82, 0.83)), (1.0, (0.95, 0.74, 0.76))])
    # the dark gut and liver show through the belly, behind the head
    gx = body.ramp(body.axis("X", 0.00, 0.34), [(0.0, (0, 0, 0)), (0.35, (1, 1, 1)), (0.75, (1, 1, 1)), (1.0, (0, 0, 0))])
    gz = body.ramp(body.axis("Z", -0.13, 0.03), [(0.0, (0.25, 0.25, 0.25)), (0.45, (1, 1, 1)), (1.0, (0, 0, 0))])
    col = body.mix(body.mix(0.85, (0, 0, 0), body.mix(1.0, gx, gz, "MULTIPLY")), col, (0.22, 0.12, 0.22))
    # muscle blocks (myomeres) showing through the skin along the tail
    bands = body.node("ShaderNodeTexWave", wave_type="BANDS", in_Scale=13.0, in_Distortion=1.0)
    bands.inputs["Detail"].default_value = 1.5
    body.link(body.coords((1.0, 0.0, 0.5)), bands.inputs["Vector"])
    tail = body.ramp(along, [(0.0, (0.20, 0.20, 0.20)), (0.60, (0.14, 0.14, 0.14)), (0.78, (0, 0, 0))])
    col = body.mix(body.mix(1.0, body.ramp(bands.outputs["Fac"], [(0.35, (0, 0, 0)), (0.65, (1, 1, 1))]), tail,
                            "MULTIPLY"), col, (0.84, 0.56, 0.60))
    speck = body.noise(60.0, 3.0, 0.5)
    body.base(body.mix(body.ramp(speck, [(0.55, (0, 0, 0)), (0.80, (0.10, 0.10, 0.10))]), col, (0.70, 0.46, 0.50)))
    body.bump(body.add(body.add(body.noise(70.0, 4.0, 0.6), body.noise(380.0, 6.0, 0.7), 0.7),
                       body.cells(210.0), 0.25), 0.14, 0.0016)
    veil = Mat("fin membrane", (0.99, 0.90, 0.91), 0.30)
    veil.set(**{"Subsurface Weight": 0.8, "Subsurface Scale": 0.03, "Transmission Weight": 0.0, "Alpha": 0.58,
                "Specular IOR Level": 0.15})
    veil.b.inputs["Subsurface Radius"].default_value = (1.0, 0.6, 0.5)
    veil.set(**{"Emission Color": (0.95, 0.62, 0.66, 1), "Emission Strength": 0.22})     # stays pink in blue water
    rays = veil.node("ShaderNodeTexWave", wave_type="BANDS", in_Scale=95.0, in_Distortion=0.4)
    veil.link(veil.coords((1.0, 0.0, 0.42)), rays.inputs["Vector"])
    veil.base(veil.mix(rays.outputs["Fac"], (1.0, 0.93, 0.93), (0.96, 0.78, 0.80)))
    ray_m = Mat("fin ray", (0.98, 0.86, 0.87), 0.35)
    ray_m.set(**{"Subsurface Weight": 0.5, "Subsurface Scale": 0.01})
    eye = Mat("eye", (0.004, 0.004, 0.006), 0.05)
    lips = Mat("mouth", (0.50, 0.33, 0.36), 0.5)

    hh = curve([(0, 0.030), (0.02, 0.070), (0.06, 0.100), (0.12, 0.118), (0.20, 0.122), (0.30, 0.108), (0.40, 0.082),
                (0.52, 0.056), (0.66, 0.038), (0.82, 0.025), (0.94, 0.016), (1, 0.009)], 0.03)
    ww = curve([(0, 0.040), (0.02, 0.086), (0.06, 0.114), (0.12, 0.122), (0.20, 0.106), (0.30, 0.076), (0.40, 0.046),
                (0.52, 0.027), (0.66, 0.015), (0.82, 0.008), (0.94, 0.005), (1, 0.003)], 0.03)
    cz = curve([(0, -0.020), (0.10, -0.008), (0.25, 0.0), (0.6, 0.008), (1, 0.012)])

    def on_head(y, z):
        """x of the head's surface at that (y, z): where the body first gets that wide."""
        lo, hi = 0.0, 0.16
        for _ in range(30):
            s = (lo + hi) / 2
            inside = (y / ww(s)) ** 2 + ((z - cz(s)) / hh(s)) ** 2 <= 1
            lo, hi = (lo, s) if inside else (s, hi)
        return 0.5 - hi

    def build(ph):
        def sway(s):                                 # the tail's sideways wave
            return 0.085 * max(0.0, (s - 0.22) / 0.78) ** 1.5 * math.sin(TAU * (ph - 1.05 * s))
        rings, rest = [], []
        for i in range(48):
            s = i / 47
            rings.append(ring((0.5 - s, sway(s), cz(s)), (0, 1, 0), (0, 0, 1), ww(s), hh(s), 22, power=2.1, flat=0.10))
            rest.append(ring((0.5 - s, 0, cz(s)), (0, 1, 0), (0, 0, 1), ww(s), hh(s), 22, power=2.1, flat=0.10))
        loft("body", rings, body.m, rest=rest)
        # one long fin along the back and one along the belly, meeting in a small round tail fin
        for sgn in (1, -1):
            rows = []
            for i in range(54):
                s = 0.26 + 0.80 * i / 53                                   # runs on past the body's end
                t = (s - 0.26) / 0.80
                sb = min(s, 1.0)
                hgt = (0.034 * math.sin(math.pi * min(1.0, t * 1.9) * 0.5) ** 0.8) * (1.0 if sgn > 0 else 0.86)
                if s > 0.93:                                               # the rounded tail fin
                    hgt *= max(0.0, 1 - ((s - 0.93) / 0.13) ** 2) ** 0.5
                edge = cz(sb) + sgn * hh(sb) * (0.86 if s <= 1.0 else max(0.0, 1 - (s - 1.0) / 0.06))
                rows.append(ring((0.5 - s, sway(s), edge + sgn * hgt * 0.5), (0, 1, 0), (0, 0, 1),
                                 0.0014, max(1e-4, hgt * 0.54), 8, power=1.5))
            loft("fin", rows, veil.m, subsurf=2)
        # big fan pectorals, sculling, with their free lower rays reaching under the chin
        flap = math.sin(TAU * ph * 2)
        for sgn in (1, -1):
            fin("pectoral", (0.305, sgn * 0.100, -0.040),
                (-0.105, sgn * (0.085 + 0.022 * flap), -0.075 - 0.018 * flap), (0.30, 0, 1), 12,
                lambda t: 0.040 + 0.115 * math.sin(math.pi * min(1, t * 1.08)) ** 0.75, lambda t: 0.006 * t, 0.035, veil.m)
            for k in range(4):                                             # free rays: fine feelers, splayed
                f = k / 3
                root = (0.345 - 0.014 * k, sgn * (0.078 + 0.005 * k), -0.100 + 0.006 * k)
                tip = (0.335 - 0.050 * f + 0.008 * flap, sgn * (0.118 + 0.034 * f), -0.176 + 0.034 * f - 0.008 * flap)
                mid = ((root[0] + tip[0]) / 2 + 0.016, (root[1] + tip[1]) / 2 + sgn * 0.004, (root[2] + tip[2]) / 2 - 0.006)
                wire("free ray", [root, mid, tip], 0.0017, ray_m.m)
        # small dark eyes, pores on the snout, a wide mouth under it
        for sgn in (1, -1):
            ey, ez = sgn * 0.088, 0.040
            sphere("eye", (on_head(ey, ez) - 0.004, ey, ez), 0.0088, eye.m)
            for py, pz in ((0.030, 0.030), (0.052, 0.006)):
                sphere("pore", (on_head(sgn * py, pz) - 0.0015, sgn * py, pz), 0.0030, lips.m)
        mouth = []
        for i in range(13):
            y = -0.074 + 0.148 * i / 12
            z = -0.050 - 0.009 * (y / 0.074) ** 2
            mouth.append((on_head(y, z) - 0.0030, y, z))
        wire("mouth", mouth, 0.0024, lips.m)
    film("snailfish", build, 48, az=32, el=15, key=42, rim=1.0)


# --------------------------------------------------------------------------- #
# RMS Titanic's bow section as it lies today: upright in the mud, rusted, the
# upper decks collapsing towards the break, the foremast fallen across the bridge
# --------------------------------------------------------------------------- #
M = 1 / 269.0                     # metres -> units (the whole ship was 269 m)


def titanic():
    new_scene()
    B = 28.2 * M
    # deck heights above the keel, metres: waterline, C, B, A and boat decks
    z_wl, z_c, z_b, z_a, z_boat = 10.5 * M, 20.4 * M, 23.2 * M, 26.0 * M, 28.9 * M
    rng = np.random.default_rng(12)

    def rusty(mat, col, amount, scale=10.0):
        """Rust streaks down the sides, rusticle lumps, and grey silt lying on top."""
        streak = mat.noise(scale * 3.0, 6.0, 0.62, stretch=(9.0, 9.0, 0.5))
        blot = mat.noise(scale * 0.6, 5.0, 0.6)
        col = mat.mix(mat.ramp(streak, [(0.30, (0, 0, 0)), (0.66, (amount,) * 3)]), col, (0.26, 0.105, 0.040))
        col = mat.mix(mat.ramp(blot, [(0.40, (0, 0, 0)), (0.80, (amount * 0.7,) * 3)]), col, (0.11, 0.065, 0.040))
        return mat.mix(mat.ramp(mat.noise(scale * 1.6, 4.0, 0.5), [(0.50, (0, 0, 0)), (0.85, (amount * 0.5,) * 3)]), col,
                       (0.33, 0.34, 0.29))

    hull_m = Mat("hull", rough=0.72)
    hull_m.base(rusty(hull_m, hull_m.image(os.path.join(TEX, "titanic_hull.png"), -0.5, 0.5, 0.0, 24.0 * M), 0.50))
    hull_m.bump(hull_m.add(hull_m.add(hull_m.noise(150.0, 5.0, 0.65, stretch=(1.0, 1.0, 0.35)),
                                      hull_m.noise(700.0, 6.0, 0.7), 0.5),
                           hull_m.image(os.path.join(TEX, "titanic_hull.png"), -0.5, 0.5, 0.0, 24.0 * M), 0.8),
                0.75, 0.0012)
    white = Mat("upperworks", rough=0.7)
    white.base(rusty(white, white.mix(1.0, white.image(os.path.join(TEX, "titanic_decks.png"), -0.5, 0.5, 20.0 * M, 33.0 * M),
                                      (0.20, 0.17, 0.14), "MULTIPLY"), 0.75))
    white.bump(white.noise(170.0, 5.0, 0.65, stretch=(1.0, 1.0, 0.35)), 0.5, 0.001)
    deck_m = Mat("deck", rough=0.85)
    deck_m.base(rusty(deck_m, (0.12, 0.11, 0.10), 0.8, 18.0))
    iron = Mat("iron", rough=0.75)
    iron.base(rusty(iron, (0.16, 0.10, 0.07), 0.9, 30.0))
    iron.bump(iron.noise(260.0, 4.0, 0.6), 0.5, 0.0008)
    # the seabed: grey-brown sediment, fading out to nothing at the edge of the patch
    mud = Mat("sediment", rough=0.9)
    mud.base(mud.mix(mud.ramp(mud.noise(22.0, 6.0, 0.6), [(0.3, (0, 0, 0)), (0.75, (1, 1, 1))]), (0.060, 0.062, 0.060),
                     (0.150, 0.145, 0.130)))
    mud.bump(mud.noise(120.0, 6.0, 0.65), 0.6, 0.002)
    rad = mud.node("ShaderNodeTexGradient", gradient_type="SPHERICAL")
    mud.link(mud.coords((2.5, 4.4, 0.0), (-0.65, 0.0, 0.0)), rad.inputs["Vector"])
    mud.into("Alpha", mud.ramp(rad.outputs["Fac"], [(0.0, (0, 0, 0)), (0.42, (1, 1, 1))]))

    half = curve([(0, 0.004), (0.03, 0.20), (0.08, 0.50), (0.16, 0.84), (0.26, 0.985), (0.34, 1.0), (1, 1.0)], 0.02)
    full = curve([(0, 0.02), (0.08, 0.22), (0.2, 0.62), (0.32, 0.95), (1, 0.95)])
    top = curve([(0, z_b), (0.145, z_b), (0.146, z_c), (1, z_c)], 0.004)
    end = 0.50                                          # where the ship tore in two (fraction from the bow)

    def build(ph):
        rings, planks = [], []
        nv = 12
        for i in range(72):
            u = end * i / 71
            x = 0.5 - u
            hb, f, zt = half(u) * B / 2, full(u), top(u)
            torn = max(0.0, (u - 0.43) / (end - 0.43))                     # the break: sagging, ragged plating
            zt -= torn ** 1.3 * 9.0 * M * (0.6 + 0.8 * rng.random())
            z0 = 0.02 * (z_wl * 1.25) if u < 0.02 else 0.0
            side = []
            for k in range(nv + 1):
                v = k / nv
                g = 1 - (1 - min(1.0, v / max(0.06, 1.0 - 0.94 * f))) ** (1.6 + 1.6 * f)
                jag = 1 + torn * 0.10 * rng.normal()
                side.append((hb * g * jag, z0 + (zt - z0) * v))
            rings.append([Vector((x, y, z)) for y, z in side] + [Vector((x, -y, z)) for y, z in reversed(side)])
            planks.append([Vector((x, hb * 0.955, zt + 0.10 * M)), Vector((x, -hb * 0.955, zt + 0.10 * M)),
                           Vector((x, -hb * 0.955, zt - 0.4 * M)), Vector((x, hb * 0.955, zt - 0.4 * M))])
        loft("hull", rings, hull_m.m, subsurf=1)
        loft("decks", planks, deck_m.m, subsurf=0)
        # upperworks: what is left of three decks, each ending further forward than the one below
        xs0 = 0.5 - 0.198
        for nm, z0, z1, inset, aft, sag in (("c", z_c, z_b, 0.499, 0.455, 0.02), ("b", z_b, z_a, 0.494, 0.420, 0.035),
                                            ("a", z_a, z_boat, 0.488, 0.385, 0.05)):
            box(nm + " deck", (0.5 - aft, -B * inset, z0), (xs0, B * inset, z1), white.m, 0.25 * M)
            box(nm + " deck fallen", (0.5 - aft - 0.050, -B * inset * 0.96, z0 - 1.8 * M), (0.5 - aft + 0.004, B * inset * 0.96, z1 - 2.2 * M),
                white.m, 0.2 * M, rot=(rng.normal(0, 0.03), sag * 3.2, 0))
        box("boat deck planks", (0.5 - 0.385, -B * 0.486, z_boat - 0.1 * M), (xs0 - 0.004, B * 0.486, z_boat + 0.08 * M), deck_m.m)
        box("bridge base", (xs0 - 0.024, -B * 0.50, z_boat), (xs0 - 0.008, B * 0.50, z_boat + 1.1 * M), white.m, 0.2 * M)
        box("officers", (0.5 - 0.300, -B * 0.28, z_boat), (0.5 - 0.225, B * 0.28, z_boat + 2.7 * M), white.m, 0.3 * M)
        # the hole where the first funnel stood
        cylinder("funnel base", (0.5 - 0.318, 0, z_boat + 0.1 * M), (0.5 - 0.318, 0, z_boat + 1.6 * M), 3.6 * M, iron.m, 28)
        cylinder("funnel hole", (0.5 - 0.318, 0, z_boat + 1.55 * M), (0.5 - 0.318, 0, z_boat + 1.65 * M), 3.1 * M,
                 Mat("void", (0.004, 0.004, 0.004), 0.9).m, 28)
        # the foremast, fallen back across the bridge
        cylinder("foremast", (0.5 - 0.160, 0.2 * M, z_b + 0.8 * M), (0.5 - 0.345, -1.5 * M, z_boat + 3.6 * M), 0.50 * M, iron.m,
                 16, r2=0.26 * M)
        cylinder("crows nest", (0.5 - 0.218, -0.3 * M, z_b + 7.2 * M), (0.5 - 0.226, -0.4 * M, z_b + 8.3 * M), 1.0 * M, iron.m, 16)
        # the prow's rail and its stanchions, the anchors and deck gear
        for sgn in (1, -1):
            rail_pts = []
            for i in range(30):
                u = 0.001 + 0.142 * i / 29
                rail_pts.append((0.5 - u, sgn * half(u) * B / 2 * 0.99, z_b + 1.15 * M))
                if i % 2 == 0:
                    cylinder("stanchion", (0.5 - u, sgn * half(u) * B / 2 * 0.99, z_b), rail_pts[-1], 0.07 * M, iron.m, 8)
            for dzr in (0.0, -0.40 * M, -0.80 * M):
                wire("rail", [(x, y, z + dzr) for x, y, z in rail_pts], 0.045 * M, iron.m)
            sphere("anchor", (0.5 - 0.022, sgn * 2.2 * M, z_c - 1.2 * M), (1.5 * M, 0.5 * M, 2.1 * M), iron.m)
            cylinder("bollard", (0.5 - 0.06, sgn * 3.2 * M, z_b), (0.5 - 0.06, sgn * 3.2 * M, z_b + 0.9 * M), 0.42 * M, iron.m, 12)
            cylinder("capstan", (0.5 - 0.085, sgn * 2.2 * M, z_b), (0.5 - 0.085, sgn * 2.2 * M, z_b + 1.2 * M), 0.8 * M, iron.m, 14)
        # rusticles: icicles of rust hanging from the rail, the deck edge and the plating
        for _ in range(620):
            u = abs(rng.normal(0.0, 0.11)) + 0.001
            if u > 0.42:
                continue
            sgn = 1 if rng.random() < 0.5 else -1
            zt = (top(u) if rng.random() < 0.72 else rng.uniform(12.0, 20.0) * M) - rng.uniform(0.0, 0.8) * M
            y = sgn * half(u) * B / 2 * (1.0 if zt > 19 * M else 1.0) * 1.005
            ln = rng.uniform(0.4, 2.3) * M
            cylinder("rusticle", (0.5 - u, y, zt), (0.5 - u + rng.normal(0, 0.15) * M, y * 1.004, zt - ln),
                     rng.uniform(0.07, 0.19) * M, iron.m, 6, r2=0.02 * M)
        box("anchor crane", (0.5 - 0.050, -0.4 * M, z_b), (0.5 - 0.026, 0.4 * M, z_b + 0.5 * M), iron.m)
        cylinder("crane jib", (0.5 - 0.046, 0, z_b + 0.4 * M), (0.5 - 0.020, 0, z_b + 3.4 * M), 0.2 * M, iron.m, 10)
        box("hatch", (0.5 - 0.125, -3.0 * M, z_b), (0.5 - 0.100, 3.0 * M, z_b + 0.7 * M), iron.m)
        # the seabed she ploughed into: a mound pushed up round the bow, flat mud beyond
        nx, ny = 150, 110
        bm = bmesh.new()
        grid = []
        for i in range(nx):
            row = []
            for j in range(ny):
                x = -0.16 + 0.84 * i / (nx - 1)
                y = -0.24 + 0.48 * j / (ny - 1)
                u = 0.5 - x
                inside = abs(y) < half(min(max(u, 0.0), 1.0)) * B / 2 if 0 <= u <= end else False
                berm = 3.6 * M * math.exp(-(((x - 0.50) / 0.05) ** 2 + (y / 0.08) ** 2))
                z = (5.4 * M - 1.2 * M * min(1.0, max(0.0, u) / end) + berm
                     + 0.45 * M * math.sin(x * 41 + 1.3 * math.sin(y * 23)) * math.sin(y * 37 + 0.7)
                     + 0.18 * M * math.sin(x * 113 + y * 71))
                row.append(bm.verts.new((x, y, z - (6.0 * M if inside else 0.0))))
            grid.append(row)
        for i in range(nx - 1):
            for j in range(ny - 1):
                bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
        finish("seabed", bm, mud.m, subsurf=0)
        # wreckage strewn aft of the break
        for _ in range(46):
            x = 0.5 - end - abs(rng.normal(0.02, 0.07))
            y = rng.normal(0, 0.06)
            sz = rng.uniform(0.8, 4.5) * M
            zg = 5.4 * M - 1.2 * M
            box("debris", (x - sz, y - sz * rng.uniform(0.3, 1.2), zg - 0.2 * M), (x + sz, y + sz * rng.uniform(0.3, 1.2), zg + sz * rng.uniform(0.2, 0.9)),
                iron.m, rot=(rng.normal(0, 0.3), rng.normal(0, 0.3), rng.uniform(0, 3.1)))
    film("titanic", build, 1, key=60, rim=2.2,
         persp=((0.5 + 0.185, -0.150, 0.054), (0.5 - 0.085, 0.0, 0.066), 46.0, 1920, 1296))


# --------------------------------------------------------------------------- #
# Scuba diver in a slow flutter kick (1.8 m tall -> 0.69 units; with fins, about 1)
# --------------------------------------------------------------------------- #
def diver():
    new_scene()
    S = 0.385                                     # metres -> units
    suit = Mat("neoprene", (0.022, 0.024, 0.028), 0.62)
    suit.set(**{"Sheen Weight": 0.5, "Sheen Roughness": 0.4})
    suit.bump(suit.add(suit.noise(260.0, 5.0, 0.7), suit.noise(1100.0, 3.0, 0.6), 0.6), 0.34, 0.0010)
    panel = Mat("suit stripe", (0.02, 0.20, 0.42), 0.5)
    bcd = Mat("bcd", (0.030, 0.032, 0.036), 0.75)
    bcd.bump(bcd.add(bcd.noise(300.0, 5.0, 0.7), bcd.noise(900.0, 3.0, 0.6), 0.6), 0.45, 0.0012)
    tank_m = Mat("tank", (0.92, 0.72, 0.04), 0.28)
    tank_m.set(**{"Coat Weight": 0.6, "Coat Roughness": 0.1})
    scr = tank_m.noise(30.0, 6.0, 0.7, stretch=(1.0, 12.0, 12.0))
    tank_m.base(tank_m.mix(tank_m.ramp(scr, [(0.52, (0, 0, 0)), (0.80, (0.35, 0.35, 0.35))]), (0.92, 0.72, 0.04),
                           (0.55, 0.50, 0.42)))
    metal = Mat("chrome", (0.75, 0.76, 0.78), 0.22)
    metal.set(Metallic=1.0)
    rubber = Mat("rubber", (0.012, 0.012, 0.013), 0.42)
    fin_m = Mat("fin", (0.95, 0.70, 0.03), 0.34)
    fin_m.set(**{"Coat Weight": 0.5, "Coat Roughness": 0.1})
    lead = Mat("lead", (0.16, 0.17, 0.18), 0.55)
    lead.set(Metallic=0.6)
    glass = Mat("mask glass", (0.55, 0.80, 0.92), 0.03)
    glass.set(**{"Transmission Weight": 0.6, "IOR": 1.45, "Coat Weight": 1.0, "Coat Roughness": 0.0})
    skin = Mat("skin", (0.78, 0.56, 0.45), 0.5)
    skin.set(**{"Subsurface Weight": 0.3, "Subsurface Scale": 0.01})
    frame = Mat("mask frame", (0.03, 0.30, 0.62), 0.3)
    bubble = Mat("bubble", (1, 1, 1), 0.0)
    bubble.set(**{"Transmission Weight": 1.0, "IOR": 1.0 / 1.33, "Coat Weight": 0.4})
    lens = Mat("torch lens", (1, 1, 1), 0.1)
    lens.set(**{"Emission Color": (1.0, 0.95, 0.80, 1), "Emission Strength": 6.0})
    brng = np.random.default_rng(5)
    bub = [(brng.uniform(0.7, 1.25), brng.uniform(-0.02, 0.02), brng.uniform(-0.05, 0.05), brng.uniform(-0.015, 0.015),
            brng.uniform(0.7, 0.95)) for _ in range(13)]

    def p(x, y, z):
        return Vector((x * S, y * S, z * S))

    def build(ph):
        roll = 0.012 * math.sin(TAU * ph)                      # the body rocks a little with each kick
        spine = [p(-0.18, 0, -0.01), p(-0.02, 0, 0.0), p(0.16, 0, 0.005), p(0.34, 0, 0.012), p(0.50, 0, 0.022),
                 p(0.60, 0, 0.034), p(0.66, 0, 0.044)]
        tube("torso", spine, [(0.150 * S, 0.105 * S), (0.172 * S, 0.118 * S), (0.150 * S, 0.108 * S), (0.172 * S, 0.118 * S),
                              (0.190 * S, 0.118 * S), (0.150 * S, 0.095 * S), (0.070 * S, 0.062 * S)], suit.m, 18)
        tube("neck", [p(0.62, 0, 0.04), p(0.72, 0, 0.065)], [0.058 * S, 0.060 * S], suit.m, 14)
        sphere("head", p(0.80, 0, 0.092), (0.118 * S, 0.100 * S, 0.112 * S), suit.m)
        sphere("face", p(0.868, 0, 0.064), (0.060 * S, 0.068 * S, 0.074 * S), skin.m)
        # legs: the kick starts at the hip, the knee follows, the fin blade trails behind the foot
        for sgn, off in ((1, 0.0), (-1, 0.5)):
            a = TAU * (ph + off)
            kz = 0.050 * math.sin(a) - 0.004
            az_ = 0.118 * math.sin(a - 0.55) + 0.022
            bend = -0.105 * math.cos(a - 0.75)                 # blade lags the foot: bent against the stroke
            hip, knee, ankle = p(-0.10, sgn * 0.095, -0.005), p(-0.52, sgn * 0.105, kz), p(-0.92, sgn * 0.110, az_)
            tube("leg", [hip, (hip + knee) / 2 + p(0, 0, 0.004), knee, (knee + ankle) / 2, ankle],
                 [0.096 * S, 0.086 * S, 0.064 * S, 0.056 * S, 0.042 * S], suit.m, 14)
            wire("leg stripe", [hip + p(0.02, sgn * 0.094, 0.01), knee + p(0, sgn * 0.063, 0.004), ankle + p(0.05, sgn * 0.043, 0)],
                 0.007 * S, panel.m)
            d = (ankle - knee).normalized()
            up = Vector((0, 0, 1)) - d * d.z
            up.normalize()
            tube("foot pocket", [ankle - d * 0.02 * S, ankle + d * 0.22 * S], [(0.055 * S, 0.046 * S), (0.062 * S, 0.030 * S)],
                 rubber.m, 12)
            blade = []
            for j in range(9):
                t = j / 8
                c = ankle + d * (0.16 + 0.58 * t) * S + up * bend * S * 1.6 * t ** 1.8
                blade.append(ring(c, (0, 1, 0), up, (0.070 + 0.062 * t ** 0.7) * S, (0.014 - 0.008 * t) * S, 12, power=3.0))
            loft("blade", blade, fin_m.m, subsurf=1)
            for e in (-0.5, 0.0, 0.5):                          # the blade's ribs
                wire("fin rib", [ankle + d * (0.20 + 0.52 * tt) * S + Vector((0, e * (0.075 + 0.06 * tt) * S, 0))
                                 + up * (bend * S * 1.6 * tt ** 1.8 + 0.012 * S) for tt in (0.0, 0.5, 1.0)], 0.006 * S, rubber.m)
            tip = ankle + d * 0.74 * S + up * bend * S * 1.6
            for e in (1, -1):
                wire("fin rail", [ankle + d * 0.14 * S + Vector((0, e * 0.066 * S, 0)),
                                  ankle + d * 0.45 * S + Vector((0, e * 0.105 * S, 0)) + up * bend * S * 1.6 * 0.5 ** 1.8,
                                  tip + Vector((0, e * 0.128 * S, 0))], 0.012 * S, rubber.m)
        # arms: the near one (towards the camera, -Y) reaches forward with a torch, the far one trails
        sw = 0.012 * math.sin(TAU * ph + 0.8)
        near = [p(0.50, -0.205, 0.010), p(0.66, -0.250, -0.110 + sw), p(0.83, -0.225, -0.215 + 1.6 * sw),
                p(1.00, -0.195, -0.235 + 2.2 * sw)]
        far = [p(0.50, 0.205, 0.010), p(0.34, 0.255, -0.050), p(0.14, 0.260, -0.085 - sw), p(-0.04, 0.245, -0.070 - sw)]
        for pts in (near, far):
            tube("arm", pts, [0.062 * S, 0.054 * S, 0.046 * S, 0.036 * S], suit.m, 12)
            sphere("glove", pts[-1] + (pts[-1] - pts[-2]).normalized() * 0.045 * S, (0.052 * S, 0.034 * S, 0.040 * S), rubber.m)
        torch_a = near[-1] + p(0.02, 0, -0.01)
        cylinder("torch", torch_a, torch_a + p(0.17, 0.012, -0.012), 0.022 * S, metal.m, 20)
        cylinder("torch lens", torch_a + p(0.17, 0.012, -0.012), torch_a + p(0.176, 0.0124, -0.0124), 0.026 * S, lens.m, 20)
        # buoyancy jacket and its straps
        tube("jacket", [p(0.10, 0, 0.012), p(0.26, 0, 0.018), p(0.44, 0, 0.026), p(0.56, 0, 0.034)],
             [(0.176 * S, 0.126 * S), (0.196 * S, 0.134 * S), (0.200 * S, 0.134 * S), (0.150 * S, 0.110 * S)], bcd.m, 18)
        for x in (0.16, 0.36):
            tube("strap", [p(x, 0, 0.01), p(x + 0.03, 0, 0.012)], [(0.200 * S, 0.139 * S)] * 2, rubber.m, 18, subsurf=1)
        # weight belt, gauge console, D-rings
        tube("belt", [p(-0.045, 0, -0.004), p(0.005, 0, -0.002)], [(0.176 * S, 0.123 * S)] * 2, rubber.m, 18, subsurf=1)
        for sgn in (1, -1):
            for dx in (-0.02,):
                box("weight", p(-0.050 + dx + 0.02, sgn * 0.150, -0.045), p(0.010 + dx + 0.02, sgn * 0.188, 0.040), lead.m, 0.004 * S)
            sphere("d-ring", p(0.40, sgn * 0.170, 0.075), (0.016 * S, 0.006 * S, 0.016 * S), metal.m, 12)
        box("console", p(0.235, 0.205, -0.115), p(0.300, 0.240, -0.045), rubber.m, 0.006 * S)
        cylinder("gauge", p(0.268, 0.203, -0.080), p(0.268, 0.199, -0.080), 0.024 * S, glass.m, 16)
        # tank on the back, valve towards the head
        tz = 0.215
        tube("tank", [p(-0.06, 0, tz - 0.004), p(-0.035, 0, tz - 0.003), p(0.0, 0, tz - 0.002), p(0.50, 0, tz + 0.018),
                      p(0.555, 0, tz + 0.021), p(0.585, 0, tz + 0.022)],
             [0.050 * S, 0.088 * S, 0.092 * S, 0.092 * S, 0.074 * S, 0.030 * S], tank_m.m, 28)
        tube("tank boot", [p(-0.066, 0, tz - 0.004), p(0.03, 0, tz - 0.001)], [0.096 * S, 0.096 * S], rubber.m, 28, subsurf=1)
        for x in (0.12, 0.38):
            tube("tank band", [p(x, 0, tz + 0.003), p(x + 0.035, 0, tz + 0.004)], [0.0945 * S, 0.0945 * S], rubber.m, 28, subsurf=1)
        cylinder("valve", p(0.585, 0, tz + 0.022), p(0.635, 0, tz + 0.025), 0.022 * S, metal.m, 16)
        cylinder("valve knob", p(0.612, 0.02, tz + 0.024), p(0.612, 0.062, tz + 0.024), 0.020 * S, rubber.m, 14)
        sphere("first stage", p(0.640, 0, tz + 0.025), (0.036 * S, 0.030 * S, 0.030 * S), metal.m)
        # mask, strap, regulator and hoses
        sphere("mask skirt", p(0.900, 0, 0.098), (0.046 * S, 0.084 * S, 0.050 * S), rubber.m)
        sphere("mask lens", p(0.922, 0, 0.100), (0.030 * S, 0.074 * S, 0.040 * S), glass.m)
        tube("mask rim", [p(0.918, 0, 0.100), p(0.930, 0, 0.100)], [(0.080 * S, 0.046 * S)] * 2, frame.m, 20, subsurf=1)
        wire("mask strap", [p(0.89, -0.086, 0.105), p(0.80, -0.104, 0.118), p(0.72, -0.06, 0.135), p(0.705, 0, 0.14),
                            p(0.72, 0.06, 0.135), p(0.80, 0.104, 0.118), p(0.89, 0.086, 0.105)], 0.011 * S, rubber.m)
        cylinder("regulator", p(0.930, -0.004, 0.030), p(0.978, -0.004, 0.024), 0.040 * S, metal.m, 20)
        cylinder("reg cover", p(0.978, -0.004, 0.024), p(0.985, -0.004, 0.023), 0.042 * S, rubber.m, 20)
        wire("reg hose", [p(0.950, -0.045, 0.030), p(0.90, -0.150, 0.060), p(0.74, -0.190, 0.150), p(0.66, -0.080, 0.220),
                          p(0.642, -0.020, tz + 0.03)], 0.013 * S, rubber.m)
        wire("gauge hose", [p(0.640, 0.020, tz + 0.02), p(0.58, 0.170, 0.150), p(0.42, 0.215, 0.030), p(0.28, 0.22, -0.06)],
             0.012 * S, rubber.m)
        wire("inflator", [p(0.640, -0.02, tz + 0.02), p(0.56, -0.170, 0.130), p(0.44, -0.205, 0.020), p(0.34, -0.20, -0.07)],
             0.014 * S, rubber.m)
        # exhaust bubbles: each one rises the whole trail once per loop, swelling, wobbling, then gone
        for j, (rs, jx, jy, jz, sq) in enumerate(bub):
            t = (j / len(bub) + ph) % 1.0
            r = 0.026 * S * rs * math.sin(math.pi * t) ** 0.55 * (0.55 + 0.6 * t)
            if r < 1e-4:
                continue
            wob = 0.018 * math.sin(TAU * (3 * t + j * 0.37))
            sphere("bubble", p(0.955 - 0.34 * t ** 1.3 + jx + wob, jy + 0.5 * wob, 0.105 + 0.70 * t ** 0.85 + jz + roll),
                   (r, r, r * sq), bubble.m, 20)
    film("diver", build, 40, az=20, el=13, key=44, rim=1.0, top=1.2, caustics=38.0, margin=0.04)


BUILD = {"whale": whale, "snailfish": snailfish, "titanic": titanic, "diver": diver}
for name in (ONLY or list(BUILD)):
    print("== building", name)
    BUILD[name]()
