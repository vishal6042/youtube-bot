"""Shared Blender helpers for the Blender-rendered sims (imported by scene scripts in this folder).

Render setup (Cycles on the GPU, denoised, AgX), shader-node helpers, and the
procedural wood: real growth-ring geometry round a pith under the board's face,
so flat-sawn boards show arches ("cathedrals"), with pores, flecks and a tone
per board. Palettes: OAK (light, varnished floor) and WALNUT (dark tabletop).
"""
import math

import bpy


def setup_render(job: dict):
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
    sc.cycles.samples = int(job.get("samples", 64))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.012
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPTIX"
        sc.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    except Exception:
        pass
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 0.5
    sc.cycles.filter_width = 1.2
    sc.render.use_persistent_data = True
    sc.render.resolution_x, sc.render.resolution_y = job["width"], job["height"]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.compression = 15
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = job.get("look", "AgX - Medium High Contrast")
    except Exception:
        pass
    sc.view_settings.exposure = job.get("exposure", 0.0)
    return sc


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


def mix_rgb(nt, a, b, kind, fac=1.0, loc=(0, 0)):
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


OAK = dict(rings=[(0.0, (0.62, 0.44, 0.25)), (0.50, (0.66, 0.48, 0.28)), (0.74, (0.50, 0.33, 0.17)),
                  (0.90, (0.37, 0.22, 0.10)), (1.0, (0.60, 0.42, 0.24))],
           pore=(0.30, 0.18, 0.08), ring_density=15.0, coat=0.25, rough=0.24)
WALNUT = dict(rings=[(0.0, (0.25, 0.14, 0.075)), (0.50, (0.28, 0.16, 0.085)), (0.74, (0.19, 0.10, 0.05)),
                     (0.90, (0.13, 0.07, 0.035)), (1.0, (0.24, 0.135, 0.07))],
              pore=(0.08, 0.045, 0.025), ring_density=11.0, coat=0.45, rough=0.20)


def wood(name="wood", pal=OAK, scale=1.0, bump=0.035):
    """Flat-sawn wood whose figure is ring geometry (see the module doc).
    Coordinates are the object's own, divided by `scale` (1 = boards about 1 unit wide)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    M_ = lambda op, a, b=None: math_node(nt, op, a, b).outputs[0]
    tc = node(nt, "ShaderNodeTexCoord")
    oi = node(nt, "ShaderNodeObjectInfo")
    xyz = node(nt, "ShaderNodeSeparateXYZ")
    sc_ = node(nt, "ShaderNodeVectorMath")
    sc_.operation = "SCALE"
    sc_.inputs["Scale"].default_value = 1.0 / scale
    link(nt, tc.outputs["Object"], sc_.inputs[0])
    link(nt, sc_.outputs[0], xyz.inputs[0])
    rnd = oi.outputs["Random"]
    r1 = M_("FRACT", M_("MULTIPLY", rnd, 13.71))
    r2 = M_("FRACT", M_("MULTIPLY", rnd, 71.37))
    r3 = M_("FRACT", M_("MULTIPLY", rnd, 5.913))
    ox = M_("ADD", xyz.outputs["X"], M_("MULTIPLY", M_("SUBTRACT", r1, 0.5), 1.7))
    dep = M_("ADD", M_("MULTIPLY", r2, 2.0), 0.30)
    yy = M_("ADD", xyz.outputs["Y"], M_("MULTIPLY", r3, 60.0))
    wv = node(nt, "ShaderNodeCombineXYZ")
    link(nt, M_("MULTIPLY", yy, 0.11), wv.inputs[0])
    link(nt, M_("MULTIPLY", ox, 0.9), wv.inputs[1])
    link(nt, M_("MULTIPLY", r1, 17.0), wv.inputs[2])
    wn = node(nt, "ShaderNodeTexNoise")
    wn.inputs["Scale"].default_value = 1.0
    wn.inputs["Detail"].default_value = 3.0
    link(nt, wv.outputs[0], wn.inputs["Vector"])
    wob = M_("MULTIPLY", M_("SUBTRACT", wn.outputs["Fac"], 0.5), 0.42)
    rad = M_("SQRT", M_("ADD", M_("MULTIPLY", ox, ox), M_("MULTIPLY", dep, dep)))
    r = M_("ADD", M_("ADD", rad, M_("MULTIPLY", yy, 0.022)), wob)
    ring = M_("FRACT", M_("MULTIPLY", r, pal["ring_density"]))
    rc = ramp(nt, pal["rings"])
    link(nt, ring, rc.inputs[0])
    early = ramp(nt, [(0.0, (1, 1, 1)), (0.30, (0.7, 0.7, 0.7)), (0.50, (0.15, 0.15, 0.15)), (0.95, (0.0, 0.0, 0.0))])
    link(nt, ring, early.inputs[0])
    pv = node(nt, "ShaderNodeCombineXYZ")
    link(nt, M_("MULTIPLY", ox, 230.0), pv.inputs[0])
    link(nt, M_("MULTIPLY", yy, 9.0), pv.inputs[1])
    link(nt, M_("MULTIPLY", r2, 50.0), pv.inputs[2])
    pn = node(nt, "ShaderNodeTexNoise")
    pn.inputs["Scale"].default_value = 1.0
    pn.inputs["Detail"].default_value = 2.0
    link(nt, pv.outputs[0], pn.inputs["Vector"])
    pmask = ramp(nt, [(0.56, (0, 0, 0)), (0.66, (1, 1, 1))])
    link(nt, pn.outputs["Fac"], pmask.inputs[0])
    pores = M_("MULTIPLY", pmask.outputs[0], M_("ADD", M_("MULTIPLY", early.outputs[0], 0.85), 0.15))
    fv = node(nt, "ShaderNodeCombineXYZ")
    link(nt, M_("MULTIPLY", ox, 9.0), fv.inputs[0])
    link(nt, M_("MULTIPLY", yy, 3.2), fv.inputs[1])
    link(nt, M_("MULTIPLY", r3, 30.0), fv.inputs[2])
    fl = node(nt, "ShaderNodeTexVoronoi")
    fl.feature = "F1"
    fl.inputs["Scale"].default_value = 1.0
    link(nt, fv.outputs[0], fl.inputs["Vector"])
    flr = ramp(nt, [(0.0, (0.07, 0.06, 0.05)), (0.06, (0, 0, 0))])
    link(nt, fl.outputs["Distance"], flr.inputs[0])
    tv = node(nt, "ShaderNodeCombineXYZ")
    link(nt, M_("MULTIPLY", ox, 0.8), tv.inputs[0])
    link(nt, M_("MULTIPLY", yy, 0.06), tv.inputs[1])
    tn = node(nt, "ShaderNodeTexNoise")
    tn.inputs["Scale"].default_value = 1.0
    link(nt, tv.outputs[0], tn.inputs["Vector"])
    drift = ramp(nt, [(0.3, (0.90, 0.88, 0.86)), (0.7, (1.06, 1.04, 1.0))])
    link(nt, tn.outputs["Fac"], drift.inputs[0])
    tone = ramp(nt, [(0.0, (0.84, 0.78, 0.72)), (0.5, (1.0, 1.0, 1.0)), (1.0, (1.07, 0.94, 0.82))])
    link(nt, rnd, tone.inputs[0])
    col = mix_rgb(nt, rc.outputs[0], tuple(pal["pore"]), "MIX", pores)
    col = mix_rgb(nt, col, flr.outputs[0], "ADD")
    col = mix_rgb(nt, col, drift.outputs[0], "MULTIPLY")
    col = mix_rgb(nt, col, tone.outputs[0], "MULTIPLY")
    link(nt, col, bsdf.inputs["Base Color"])
    rr = math_node(nt, "MULTIPLY_ADD", pores, 0.30)
    rr.inputs[2].default_value = pal["rough"]
    link(nt, rr.outputs[0], bsdf.inputs["Roughness"])
    bsdf.inputs["Coat Weight"].default_value = pal["coat"]
    bsdf.inputs["Coat Roughness"].default_value = 0.09
    bp = node(nt, "ShaderNodeBump")
    bp.inputs["Strength"].default_value = bump
    bp.inputs["Distance"].default_value = 0.003 * scale
    link(nt, M_("SUBTRACT", M_("MULTIPLY", ring, 0.3), pores), bp.inputs["Height"])
    link(nt, bp.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def flat_mat(name, rgb, rough=0.8, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    return m


def look_at(ob, pos, target):
    from mathutils import Vector
    ob.location = Vector(pos)
    ob.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()


def camera(clip=(0.02, 200)):
    cam = bpy.data.cameras.new("cam")
    cam.sensor_fit = "AUTO"
    cam.sensor_width = 36.0
    cam.clip_start, cam.clip_end = clip
    cam.dof.use_dof = True
    co = bpy.data.objects.new("cam", cam)
    bpy.context.scene.collection.objects.link(co)
    bpy.context.scene.camera = co
    return co


def lathe(name, profile, seg=96, smooth=True):
    """A solid of revolution round Z from a closed or open (r, z) profile list."""
    import bmesh
    b = bmesh.new()
    rings = []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([b.verts.new((0, 0, z))])
        else:
            rings.append([b.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z))
                          for i in range(seg)])
    for a, c in zip(rings, rings[1:]):
        if len(a) == 1 and len(c) == 1:
            continue
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
    me = bpy.data.meshes.new(name)
    b.to_mesh(me)
    b.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob
