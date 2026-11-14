"""Render Buffon's needle frames (run inside Blender; see graph_bot/sims/blend.py).

    blender -b --factory-startup -P scripts/blender/buffon_scene.py -- <job.json> <out_dir> <frame list>

The scene: a varnished oak floor of boards exactly one needle wide, the cracks
between them dark and real (the boards are separate, bevelled planks), lit by
low afternoon sun and a big window. Long steel needles (pointed tip, flattened
head with an eye) fall, strike end first, slap flat and settle; a needle that
lies across a crack turns brass. Every needle's motion comes from
graph_bot/sims/buffon_model.py with the drops listed in the job, so the count
the sim prints is the count of what is rendered.
"""
import importlib.util
import json
import math
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
JOB = json.load(open(argv[0], encoding="utf-8"))
OUT = argv[1]
FRAMES = [int(v) for v in open(argv[2], encoding="utf-8").read().split()]

spec = importlib.util.spec_from_file_location("buffon_model", JOB["model_path"])
bm_ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm_)


# --------------------------------------------------------------------------- #
# Render settings
# --------------------------------------------------------------------------- #
def setup_render():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
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
            pass
    sc.cycles.samples = int(JOB.get("samples", 64))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.012
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPTIX"
        sc.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 3
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 0.5
    sc.cycles.filter_width = 1.2
    sc.render.use_persistent_data = True
    sc.render.resolution_x, sc.render.resolution_y = JOB["width"], JOB["height"]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 15
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.view_settings.exposure = JOB.get("exposure", 0.0)
    return sc


# --------------------------------------------------------------------------- #
# Node helpers
# --------------------------------------------------------------------------- #
def node(nt, kind, loc=(0, 0), **inputs):
    n = nt.nodes.new(kind)
    n.location = loc
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def link(nt, a, b):
    nt.links.new(a, b)


def ramp(nt, stops, loc=(0, 0)):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.location = loc
    els = r.color_ramp.elements
    while len(els) < len(stops):
        els.new(0.5)
    for e, (p, c) in zip(els, stops):
        e.position = p
        e.color = (*c, 1.0)
    return r


def math_node(nt, op, a=None, b=None, loc=(0, 0)):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.location = loc
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n


# --------------------------------------------------------------------------- #
# Materials
# --------------------------------------------------------------------------- #
def oak():
    """Varnished flat-sawn oak. The figure is real geometry: growth rings are
    cylinders round a pith that runs along the board, a little below its face
    and off to one side, so the face cuts them into arches ("cathedrals") and
    long straight lines. Each board has its own pith, depth and stretch of
    log. Open pores dot the earlywood of every ring; pale ray flecks cross it."""
    m = bpy.data.materials.new("oak")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    M_ = lambda op, a, b=None, loc=(0, 0): math_node(nt, op, a, b, loc).outputs[0]
    tc = node(nt, "ShaderNodeTexCoord", (-1800, 0))
    oi = node(nt, "ShaderNodeObjectInfo", (-1800, -400))
    xyz = node(nt, "ShaderNodeSeparateXYZ", (-1600, 0))
    link(nt, tc.outputs["Object"], xyz.inputs[0])
    rnd = oi.outputs["Random"]
    r1 = M_("FRACT", M_("MULTIPLY", rnd, 13.71))
    r2 = M_("FRACT", M_("MULTIPLY", rnd, 71.37))
    r3 = M_("FRACT", M_("MULTIPLY", rnd, 5.913))
    ox = M_("ADD", xyz.outputs["X"], M_("MULTIPLY", M_("SUBTRACT", r1, 0.5), 1.7))     # across, from the pith
    dep = M_("ADD", M_("MULTIPLY", r2, 2.0), 0.30)                                    # how deep the pith lies
    yy = M_("ADD", xyz.outputs["Y"], M_("MULTIPLY", r3, 60.0))                        # along
    # slow wobble of the rings (the tree did not grow perfectly round)
    wv = node(nt, "ShaderNodeCombineXYZ", (-1100, 300))
    link(nt, M_("MULTIPLY", yy, 0.11), wv.inputs[0])
    link(nt, M_("MULTIPLY", ox, 0.9), wv.inputs[1])
    link(nt, M_("MULTIPLY", r1, 17.0), wv.inputs[2])
    wn = node(nt, "ShaderNodeTexNoise", (-900, 300))
    wn.inputs["Scale"].default_value = 1.0
    wn.inputs["Detail"].default_value = 3.0
    link(nt, wv.outputs[0], wn.inputs["Vector"])
    wob = M_("MULTIPLY", M_("SUBTRACT", wn.outputs["Fac"], 0.5), 0.42)
    rad = M_("SQRT", M_("ADD", M_("MULTIPLY", ox, ox), M_("MULTIPLY", dep, dep)))
    r = M_("ADD", M_("ADD", rad, M_("MULTIPLY", yy, 0.022)), wob)
    ring = M_("FRACT", M_("MULTIPLY", r, 15.0))
    rc = ramp(nt, [(0.0, (0.62, 0.44, 0.25)), (0.50, (0.66, 0.48, 0.28)), (0.74, (0.50, 0.33, 0.17)),
                   (0.90, (0.37, 0.22, 0.10)), (1.0, (0.60, 0.42, 0.24))], (-300, 200))
    link(nt, ring, rc.inputs[0])
    # earlywood (just after each ring line) is where the big open pores are
    early = ramp(nt, [(0.0, (1, 1, 1)), (0.30, (0.7, 0.7, 0.7)), (0.50, (0.15, 0.15, 0.15)), (0.95, (0.0, 0.0, 0.0))], (-300, -50))
    link(nt, ring, early.inputs[0])
    pv = node(nt, "ShaderNodeCombineXYZ", (-1100, -150))
    link(nt, M_("MULTIPLY", ox, 230.0), pv.inputs[0])
    link(nt, M_("MULTIPLY", yy, 9.0), pv.inputs[1])
    link(nt, M_("MULTIPLY", r2, 50.0), pv.inputs[2])
    pn = node(nt, "ShaderNodeTexNoise", (-900, -150))
    pn.inputs["Scale"].default_value = 1.0
    pn.inputs["Detail"].default_value = 2.0
    link(nt, pv.outputs[0], pn.inputs["Vector"])
    pmask = ramp(nt, [(0.56, (0, 0, 0)), (0.66, (1, 1, 1))], (-700, -150))
    link(nt, pn.outputs["Fac"], pmask.inputs[0])
    pores = M_("MULTIPLY", pmask.outputs[0], M_("ADD", M_("MULTIPLY", early.outputs[0], 0.85), 0.15))
    # ray flecks: short pale dashes across the grain
    fv = node(nt, "ShaderNodeCombineXYZ", (-1100, -450))
    link(nt, M_("MULTIPLY", ox, 9.0), fv.inputs[0])
    link(nt, M_("MULTIPLY", yy, 3.2), fv.inputs[1])
    link(nt, M_("MULTIPLY", r3, 30.0), fv.inputs[2])
    fl = node(nt, "ShaderNodeTexVoronoi", (-900, -450))
    fl.feature = "F1"
    fl.inputs["Scale"].default_value = 1.0
    link(nt, fv.outputs[0], fl.inputs["Vector"])
    flr = ramp(nt, [(0.0, (0.07, 0.06, 0.05)), (0.06, (0, 0, 0))], (-700, -450))
    link(nt, fl.outputs["Distance"], flr.inputs[0])
    # a slow tone drift along the board and a tone for each board
    tv = node(nt, "ShaderNodeCombineXYZ", (-1100, -700))
    link(nt, M_("MULTIPLY", ox, 0.8), tv.inputs[0])
    link(nt, M_("MULTIPLY", yy, 0.06), tv.inputs[1])
    tn = node(nt, "ShaderNodeTexNoise", (-900, -700))
    tn.inputs["Scale"].default_value = 1.0
    link(nt, tv.outputs[0], tn.inputs["Vector"])
    drift = ramp(nt, [(0.3, (0.90, 0.88, 0.86)), (0.7, (1.06, 1.04, 1.0))], (-700, -700))
    link(nt, tn.outputs["Fac"], drift.inputs[0])
    tone = ramp(nt, [(0.0, (0.84, 0.78, 0.72)), (0.5, (1.0, 1.0, 1.0)), (1.0, (1.07, 0.94, 0.82))], (-700, -900))
    link(nt, rnd, tone.inputs[0])

    def mix(a, b, kind, fac=1.0, loc=(0, 0)):
        n = node(nt, "ShaderNodeMix", loc)
        n.data_type = "RGBA"
        n.blend_type = kind
        if isinstance(fac, float):
            n.inputs["Factor"].default_value = fac
        else:
            link(nt, fac, n.inputs["Factor"])
        link(nt, a, n.inputs[6])
        if isinstance(b, tuple):
            n.inputs[7].default_value = (*b, 1)
        else:
            link(nt, b, n.inputs[7])
        return n.outputs[2]
    col = mix(rc.outputs[0], (0.30, 0.18, 0.08), "MIX", pores)
    col = mix(col, flr.outputs[0], "ADD")
    col = mix(col, drift.outputs[0], "MULTIPLY")
    col = mix(col, tone.outputs[0], "MULTIPLY")
    link(nt, col, bsdf.inputs["Base Color"])
    rr = math_node(nt, "MULTIPLY_ADD", pores, 0.30, (-200, -250))
    rr.inputs[2].default_value = 0.24
    link(nt, rr.outputs[0], bsdf.inputs["Roughness"])
    bsdf.inputs["Coat Weight"].default_value = 0.25
    bsdf.inputs["Coat Roughness"].default_value = 0.09
    bump = node(nt, "ShaderNodeBump", (0, -350))
    bump.inputs["Strength"].default_value = 0.035
    bump.inputs["Distance"].default_value = 0.003
    link(nt, M_("SUBTRACT", M_("MULTIPLY", ring, 0.3), pores), bump.inputs["Height"])
    link(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def needle_mat():
    """Polished steel that turns to brass as the object's colour (red channel) goes 0 -> 1."""
    m = bpy.data.materials.new("needle")
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    steel = node(nt, "ShaderNodeBsdfPrincipled", (-300, 200))
    steel.inputs["Base Color"].default_value = (0.78, 0.79, 0.81, 1)
    steel.inputs["Metallic"].default_value = 1.0
    steel.inputs["Roughness"].default_value = 0.11
    brass = node(nt, "ShaderNodeBsdfPrincipled", (-300, -300))
    brass.inputs["Base Color"].default_value = (1.0, 0.68, 0.26, 1)
    brass.inputs["Metallic"].default_value = 1.0
    brass.inputs["Roughness"].default_value = 0.16
    oi = node(nt, "ShaderNodeObjectInfo", (-600, 0))
    sep = node(nt, "ShaderNodeSeparateColor", (-450, 0))
    link(nt, oi.outputs["Color"], sep.inputs[0])
    mix = node(nt, "ShaderNodeMixShader", (0, 0))
    link(nt, sep.outputs[0], mix.inputs[0])
    link(nt, steel.outputs[0], mix.inputs[1])
    link(nt, brass.outputs[0], mix.inputs[2])
    link(nt, mix.outputs[0], out.inputs["Surface"])
    return m


def flat_mat(name, rgb, rough=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def board(k: int, y0: float, y1: float, mat, gap: float, thick: float = 0.16):
    """One plank from x = k to k + 1 (less half the gap each side), top at z = 0."""
    me = bpy.data.meshes.new(f"board{k}")
    b = bmesh.new()
    bmesh.ops.create_cube(b, size=1.0)
    b.to_mesh(me)
    b.free()
    ob = bpy.data.objects.new(f"board{k}", me)
    bpy.context.scene.collection.objects.link(ob)
    w = 1.0 - gap
    ob.scale = (w, y1 - y0, thick)
    ob.location = (k + 0.5, (y0 + y1) / 2, -thick / 2)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(scale=True)
    ob.select_set(False)
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width = 0.008
    bv.segments = 3
    bv.limit_method = "ANGLE"
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def needle_mesh():
    """A long steel needle along +X, length 1, centred on the origin: a long
    taper to a sharp point at +X, a slightly wider flattened head at -X with an
    eye cut through it."""
    R = bm_.R_NEEDLE
    seg = 28
    st = [(0.5, 0.0), (0.4985, 0.10), (0.494, 0.25), (0.485, 0.45), (0.47, 0.66), (0.45, 0.83),
          (0.42, 0.95), (0.38, 1.0), (-0.40, 1.0), (-0.425, 1.03), (-0.45, 1.10), (-0.47, 1.12),
          (-0.485, 1.06), (-0.494, 0.88), (-0.4985, 0.55), (-0.5, 0.0)]
    b = bmesh.new()
    rings = []
    for x, r in st:
        flat = min(1.0, max(0.0, (-x - 0.40) / 0.03))          # the head is pressed flat
        sy, sz = 1 + 0.30 * flat, 1 - 0.28 * flat
        if r == 0:
            rings.append([b.verts.new((x, 0, 0))])
            continue
        rings.append([b.verts.new((x, R * r * sy * math.cos(a), R * r * sz * math.sin(a)))
                      for a in (2 * math.pi * i / seg for i in range(seg))])
    for a, c in zip(rings, rings[1:]):
        if len(a) == 1:
            for i in range(seg):
                b.faces.new((a[0], c[i], c[(i + 1) % seg]))
        elif len(c) == 1:
            for i in range(seg):
                b.faces.new((a[i], c[0], a[(i + 1) % seg]))
        else:
            for i in range(seg):
                b.faces.new((a[i], c[i], c[(i + 1) % seg], a[(i + 1) % seg]))
    bmesh.ops.recalc_face_normals(b, faces=b.faces)
    me = bpy.data.meshes.new("needle")
    b.to_mesh(me)
    b.free()
    ob = bpy.data.objects.new("needle_src", me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    # the eye: a slot through the flattened head
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=R * 0.42, depth=R * 6)
    cut = bpy.context.object
    cut.scale = (5.2, 1.0, 1.0)
    cut.location = (-0.462, 0, 0)
    bo = ob.modifiers.new("eye", "BOOLEAN")
    bo.operation = "DIFFERENCE"
    bo.solver = "EXACT"
    bo.object = cut
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="eye")
    bpy.data.objects.remove(cut)
    ob.data.materials.append(needle_mat())
    return ob


def lights():
    sc = bpy.context.scene
    # low afternoon sun from the upper left: long crisp shadows of the falling needles
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = JOB.get("sun", 3.2)
    sun.angle = math.radians(1.6)
    sun.color = (1.0, 0.86, 0.68)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    el, az = math.radians(JOB.get("sun_el", 30)), math.radians(JOB.get("sun_az", 140))
    d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    so.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    # a big window: soft cool fill, and the long highlight running down every steel needle
    win = bpy.data.lights.new("window", "AREA")
    win.shape = "RECTANGLE"
    win.size, win.size_y = 14.0, 7.0
    win.energy = JOB.get("window", 9000)
    win.color = (0.86, 0.92, 1.0)
    wo = bpy.data.objects.new("window", win)
    sc.collection.objects.link(wo)
    wo.location = (-16, 22, 16)
    wo.rotation_euler = (wo.location * -1).to_track_quat("-Z", "Y").to_euler()
    # the room: warm dim surroundings (what the needles reflect away from the window)
    w = bpy.data.worlds.new("room")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    tc = node(nt, "ShaderNodeTexCoord", (-800, 0))
    sep = node(nt, "ShaderNodeSeparateXYZ", (-600, 0))
    link(nt, tc.outputs["Generated"], sep.inputs[0])
    r = ramp(nt, [(0.35, (0.050, 0.038, 0.028)), (0.62, (0.11, 0.10, 0.095)), (1.0, (0.16, 0.17, 0.19))], (-400, 0))
    link(nt, sep.outputs[2], r.inputs[0])
    link(nt, r.outputs[0], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = JOB.get("world", 1.0)


def build():
    sc = setup_render()
    lights()
    wood = oak()
    x0, x1 = JOB["floor_x"]
    for k in range(int(x0), int(x1)):
        board(k, JOB["floor_y"][0], JOB["floor_y"][1], wood, JOB.get("gap", 0.028))
    # what you see down the cracks: dark joists and dust
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -0.17))
    under = bpy.context.object
    under.scale = (200, 200, 1)
    under.data.materials.append(flat_mat("under", (0.012, 0.009, 0.007)))
    src = needle_mesh()
    src.hide_render = True
    src.location = (0, 0, -50)
    n = len(JOB["drops"]["x"])
    obs = []
    coll = bpy.data.collections.new("needles")
    sc.collection.children.link(coll)
    for i in range(n):
        o = bpy.data.objects.new(f"n{i}", src.data)
        coll.objects.link(o)
        o.location = (0, 0, -50)
        obs.append(o)
    cam = bpy.data.cameras.new("cam")
    cam.sensor_fit = "AUTO"
    cam.sensor_width = 36.0
    cam.clip_start, cam.clip_end = 0.05, 400
    cam.dof.use_dof = True
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return sc, obs, co


def main():
    sc, obs, co = build()
    d = {k: np.asarray(v, float) for k, v in JOB["drops"].items()}
    d["hit"] = d["hit"] > 0.5
    T, D = np.asarray(JOB["T"], float), np.asarray(JOB["D"], float)
    tmap = np.asarray(JOB["tmap"], float)
    keys = JOB["cam"]
    fps = JOB["fps"]
    n = len(T)
    prev = np.full((n, 13), np.nan)
    for fi in FRAMES:
        t0 = time.time()
        t = fi / fps
        s = bm_.story_time(tmap, t)
        vis, c, dirn, hot = bm_.poses(d, T, D, s)
        c = np.where(vis[:, None], c, np.array([0, 0, -50.0]))
        # orientation: x along the needle, z as close to up as it allows
        up = np.array([0, 0, 1.0]) - dirn * dirn[:, 2:3]
        up /= np.linalg.norm(up, axis=1, keepdims=True)
        side = np.cross(up, dirn)
        state = np.concatenate([c, dirn, up, side[:, :0], hot[:, None]], 1)
        state = np.concatenate([state, np.zeros((n, 13 - state.shape[1]))], 1)
        changed = np.where(~np.all(np.isclose(state, prev, atol=1e-6, equal_nan=False), axis=1))[0]
        for i in changed:
            m = Matrix(((dirn[i, 0], side[i, 0], up[i, 0], c[i, 0]),
                        (dirn[i, 1], side[i, 1], up[i, 1], c[i, 1]),
                        (dirn[i, 2], side[i, 2], up[i, 2], c[i, 2]),
                        (0, 0, 0, 1)))
            obs[i].matrix_world = m
            obs[i].color = (float(hot[i]), 0, 0, 1)
        prev = state
        pos, tgt, lens, fstop = bm_.camera(keys, t)
        co.location = Vector(pos)
        co.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        co.data.lens = lens
        co.data.dof.focus_distance = float(np.linalg.norm(np.asarray(tgt) - np.asarray(pos)))
        co.data.dof.aperture_fstop = fstop
        sc.render.filepath = f"{OUT}/{fi:05d}.png"
        bpy.ops.render.render(write_still=True)
        print(f"FRAME {fi} {time.time() - t0:.2f}s moved={len(changed)}", flush=True)


main()
