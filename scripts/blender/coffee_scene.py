"""Render the coffee-cup caustic frames (run inside Blender; see graph_bot/sims/blend.py).

    blender -b --factory-startup -P scripts/blender/coffee_scene.py -- <job.json> <out_dir> <frame list>

The scene: a white glazed mug of milky coffee on a walnut table, in low morning
sun from the back left. Later a small black clip-on LED drops onto the near rim
and lights the cup from there.

The light the glazed wall reflects onto the coffee (the caustic) is not left to
Cycles' path tracer, which cannot find it cleanly from a sun or a tiny lamp. It
is traced photon by photon (graph_bot/sims/caustic_model.py, same cup, same sun
direction, same lamp position) into two irradiance maps, and the coffee emits
exactly what its colour would scatter of that light: albedo x irradiance. The
direct light, shadows and everything else are Cycles'. Cycles' own caustics are
switched off so nothing is counted twice.

Per frame the job gives: camera, sun strength (a passing cloud), the clip's
height above the rim and the LED's power.
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bkit  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
JOB = json.load(open(argv[0], encoding="utf-8"))
OUT = argv[1]
FRAMES = [int(v) for v in open(argv[2], encoding="utf-8").read().split()]
HW = JOB["hw"]
LIQ = JOB["liquid_rgb"]


# --------------------------------------------------------------------------- #
# The mug
# --------------------------------------------------------------------------- #
def mug():
    """White glazed stoneware: inside radius exactly 1 above the coffee, a rolled rim,
    a slightly thicker base with a foot ring, and a handle on the right."""
    h = HW
    prof = [(0.0, -1.95), (0.80, -1.95), (0.93, -1.92), (0.985, -1.85), (1.0, -1.70),
            (1.0, -0.6), (1.0, 0.0), (1.0, h * 0.5), (1.0, h),
            (1.004, h + 0.022), (1.016, h + 0.046), (1.036, h + 0.064), (1.062, h + 0.073),
            (1.088, h + 0.070), (1.110, h + 0.058), (1.126, h + 0.040), (1.136, h + 0.018), (1.140, h - 0.01),
            (1.140, h - 0.4), (1.136, -1.0), (1.128, -1.90), (1.118, -2.00), (1.098, -2.06),
            (1.07, -2.10), (1.03, -2.12), (0.96, -2.12), (0.93, -2.10), (0.90, -2.08), (0.0, -2.08)]
    ob = bkit.lathe("mug", prof, seg=192)
    glaze = bpy.data.materials.new("glaze")
    glaze.use_nodes = True
    b = glaze.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.86, 0.85, 0.82, 1)
    b.inputs["Roughness"].default_value = 0.045
    b.inputs["IOR"].default_value = 1.5
    b.inputs["Subsurface Weight"].default_value = 0.08
    b.inputs["Subsurface Radius"].default_value = (0.05, 0.04, 0.03)
    # a faint unevenness in the glaze so highlights are not CG-perfect
    nt = glaze.node_tree
    nz = bkit.node(nt, "ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 9.0
    nz.inputs["Detail"].default_value = 4.0
    bp = bkit.node(nt, "ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.02
    bp.inputs["Distance"].default_value = 0.01
    bkit.link(nt, nz.outputs["Fac"], bp.inputs["Height"])
    bkit.link(nt, bp.outputs["Normal"], b.inputs["Normal"])
    ob.data.materials.append(glaze)
    # handle: a curved loop, oval in section, its ends sunk into the wall
    cu = bpy.data.curves.new("handle", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("BEZIER")
    pts = [((1.06, 0, 0.05), (0.98, 0, 0.30), (1.45, 0, 0.12)),
           ((1.72, 0, -0.55), (1.80, 0, -0.10), (1.72, 0, -1.00)),
           ((1.06, 0, -1.45), (1.40, 0, -1.40), (0.98, 0, -1.48))]
    sp.bezier_points.add(len(pts) - 1)
    for bpnt, (co, hl, hr) in zip(sp.bezier_points, pts):
        bpnt.co, bpnt.handle_left, bpnt.handle_right = co, hl, hr
    cu.bevel_depth = 0.115
    cu.bevel_resolution = 8
    cu.resolution_u = 32
    hob = bpy.data.objects.new("handle", cu)
    bpy.context.scene.collection.objects.link(hob)
    hob.scale = (1, 0.62, 1)                  # oval section: wider than it is thick
    hob.data.materials.append(glaze)
    bpy.context.view_layer.objects.active = hob
    hob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    hob.select_set(False)
    for p in hob.data.polygons:
        p.use_smooth = True
    for o in (ob, hob):
        o.location.z = JOB["table_z"] + 2.12
    return ob


def coffee():
    """The coffee's surface, emitting the traced reflected light on top of what Cycles lights."""
    bpy.ops.mesh.primitive_circle_add(vertices=192, radius=1.003, fill_type="NGON", location=(0, 0, 0))
    ob = bpy.context.object
    ob.name = "coffee"
    ob.location.z = JOB["table_z"] + 2.12
    m = bpy.data.materials.new("coffee")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*LIQ, 1)
    b.inputs["Roughness"].default_value = 0.035
    b.inputs["IOR"].default_value = 1.34
    b.inputs["Subsurface Weight"].default_value = 0.15
    b.inputs["Subsurface Radius"].default_value = (0.03, 0.015, 0.008)
    tc = bkit.node(nt, "ShaderNodeTexCoord")
    mp = bkit.node(nt, "ShaderNodeMapping")
    mp.inputs["Location"].default_value = (0.5, 0.5, 0)
    mp.inputs["Scale"].default_value = (0.5, 0.5, 1)
    bkit.link(nt, tc.outputs["Object"], mp.inputs["Vector"])
    vals = {}
    acc = None
    for key in ("sun", "lamp"):
        arr = np.load(JOB["maps"][key]).astype(np.float32)
        res = arr.shape[0]
        img = bpy.data.images.new(f"map_{key}", res, res, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        px = np.zeros((res, res, 4), np.float32)
        px[..., 0] = px[..., 1] = px[..., 2] = arr
        px[..., 3] = 1
        img.pixels.foreach_set(px.ravel())
        img.pack()
        tex = bkit.node(nt, "ShaderNodeTexImage")
        tex.image = img
        tex.extension = "CLIP"
        tex.interpolation = "Cubic"
        bkit.link(nt, mp.outputs[0], tex.inputs["Vector"])
        v = bkit.node(nt, "ShaderNodeValue")
        vals[key] = v
        mul = bkit.math_node(nt, "MULTIPLY", tex.outputs["Color"], v.outputs[0])
        acc = mul.outputs[0] if acc is None else bkit.math_node(nt, "ADD", acc, mul.outputs[0]).outputs[0]
    col = bkit.node(nt, "ShaderNodeMix")
    col.data_type = "RGBA"
    col.blend_type = "MULTIPLY"
    col.inputs["Factor"].default_value = 1.0
    col.inputs[6].default_value = (*LIQ, 1)
    comb = bkit.node(nt, "ShaderNodeCombineColor")
    for i in range(3):
        bkit.link(nt, acc, comb.inputs[i])
    bkit.link(nt, comb.outputs[0], col.inputs[7])
    bkit.link(nt, col.outputs[2], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = JOB.get("emit_k", 1.0)
    ob.data.materials.append(m)
    # the meniscus: coffee creeping a hair up the glaze all round the edge
    bpy.ops.mesh.primitive_torus_add(major_radius=0.992, minor_radius=0.011, major_segments=192, minor_segments=16,
                                     location=(0, 0, ob.location.z - 0.004))
    men = bpy.context.object
    men.data.materials.append(m)
    for p in men.data.polygons:
        p.use_smooth = True
    # a few small bubbles against the wall, on the shaded side
    bub = bpy.data.materials.new("bubble")
    bub.use_nodes = True
    bb = bub.node_tree.nodes["Principled BSDF"]
    bb.inputs["Base Color"].default_value = (0.80, 0.66, 0.50, 1)       # milky foam: pale, with a wet shine
    bb.inputs["Roughness"].default_value = 0.06
    bb.inputs["Coat Weight"].default_value = 1.0
    bb.inputs["Coat Roughness"].default_value = 0.02
    bb.inputs["Subsurface Weight"].default_value = 0.4
    bb.inputs["Subsurface Radius"].default_value = (0.02, 0.012, 0.008)
    rng = np.random.default_rng(11)
    for i in range(11):
        a = math.radians(rng.uniform(150, 215))
        r = rng.uniform(0.010, 0.026) * (1.5 if i < 3 else 1.0)
        rr = 0.985 - r - rng.uniform(0, 0.05)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=r,
                                             location=(rr * math.cos(a), rr * math.sin(a), ob.location.z))
        o = bpy.context.object
        o.scale = (1, 1, 0.55)
        o.data.materials.append(bub)
        for p in o.data.polygons:
            p.use_smooth = True
    return vals


def table():
    """Walnut planks running away from the camera."""
    mat = bkit.wood("walnut", bkit.WALNUT, scale=3.4, bump=0.03)
    z = JOB["table_z"]
    w = 3.4
    for k in range(-4, 4):
        bpy.ops.mesh.primitive_cube_add(size=1)
        ob = bpy.context.object
        ob.scale = (w - 0.012, 60, 0.6)
        ob.location = ((k + 0.5) * w + 0.9, 12, z - 0.3)
        bpy.ops.object.transform_apply(scale=True)
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = 0.02
        bv.segments = 3
        ob.data.materials.append(mat)


def clip():
    """A small clip-on LED: a matt black U that hugs the rim, the LED on its inner arm."""
    parts = []
    blk = bkit.flat_mat("clip", (0.018, 0.018, 0.02), rough=0.38)
    alu = bkit.flat_mat("alu", (0.75, 0.75, 0.77), rough=0.25, metallic=1.0)
    th = math.radians(JOB["lamp_angle"])
    zr = JOB["table_z"] + 2.12

    def box(name, r0, r1, z0, z1, wdt, mat, bev=0.016):
        bpy.ops.mesh.primitive_cube_add(size=1)
        ob = bpy.context.object
        ob.name = name
        ob.scale = (r1 - r0, wdt, z1 - z0)
        ob.location = ((r0 + r1) / 2, 0, (z0 + z1) / 2)
        bpy.ops.object.transform_apply(scale=True, location=True)
        b = ob.modifiers.new("bevel", "BEVEL")
        b.width = bev
        b.segments = 3
        ob.data.materials.append(mat)
        for p in ob.data.polygons:
            p.use_smooth = True
        parts.append(ob)
        return ob
    box("outer", 1.145, 1.19, HW - 0.42, HW + 0.12, 0.24, blk)
    box("bridge", 0.955, 1.19, HW + 0.075, HW + 0.125, 0.24, blk)
    box("inner", 0.955, 0.985, HW - 0.16, HW + 0.12, 0.24, blk)
    for k in range(6):                                   # ribs to grip
        zc = HW - 0.36 + k * 0.045
        box(f"rib{k}", 1.185, 1.205, zc, zc + 0.018, 0.20, blk, bev=0.006)
    # the LED head: a short metal barrel on the inner arm, lens facing the middle of the cup
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.055, depth=0.05)
    hd = bpy.context.object
    hd.rotation_euler = (0, math.pi / 2, 0)
    hd.location = (0.935, 0, JOB["lamp_z"])
    bpy.ops.object.transform_apply(rotation=True, location=True)
    hd.data.materials.append(alu)
    for p in hd.data.polygons:
        p.use_smooth = True
    parts.append(hd)
    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=0.042, fill_type="NGON")
    lens = bpy.context.object
    lens.rotation_euler = (0, -math.pi / 2, 0)
    lens.location = (0.9085, 0, JOB["lamp_z"])
    bpy.ops.object.transform_apply(rotation=True, location=True)
    lm = bpy.data.materials.new("lens")
    lm.use_nodes = True
    lb = lm.node_tree.nodes["Principled BSDF"]
    lb.inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1)
    lb.inputs["Roughness"].default_value = 0.1
    lb.inputs["Emission Color"].default_value = (1.0, 0.93, 0.82, 1)
    lb.inputs["Emission Strength"].default_value = 0.0
    lens.data.materials.append(lm)
    parts.append(lens)
    root = bpy.data.objects.new("clip_root", None)
    bpy.context.scene.collection.objects.link(root)
    for p in parts:
        p.parent = root
    root.rotation_euler = (0, 0, th)
    root.location = (0, 0, zr)
    return root, lb


def lights():
    sc = bpy.context.scene
    sun = bpy.data.lights.new("sun", "SUN")
    sun.angle = math.radians(0.6)
    sun.color = (1.0, 0.84, 0.66)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    el, az = math.radians(JOB["sun_el"]), math.radians(JOB["sun_az"])
    d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    so.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    spot = bpy.data.lights.new("led", "SPOT")
    spot.spot_size = math.radians(2 * JOB["lamp_cone"])
    spot.spot_blend = 0.0
    spot.shadow_soft_size = 0.012
    spot.color = (1.0, 0.93, 0.82)
    spot.energy = 0.0
    lo = bpy.data.objects.new("led", spot)
    sc.collection.objects.link(lo)
    lo.location = Vector(JOB["lamp_pos"]) + Vector((0, 0, JOB["table_z"] + 2.12))
    lo.rotation_euler = (-Vector(JOB["lamp_aim"])).to_track_quat("Z", "Y").to_euler()
    # the room: soft daylight from the window side, warm dim walls elsewhere
    w = bpy.data.worlds.new("room")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    tc = bkit.node(nt, "ShaderNodeTexCoord")
    sep = bkit.node(nt, "ShaderNodeSeparateXYZ")
    bkit.link(nt, tc.outputs["Generated"], sep.inputs[0])
    r = bkit.ramp(nt, [(0.35, (0.045, 0.035, 0.028)), (0.62, (0.10, 0.092, 0.085)), (1.0, (0.15, 0.16, 0.18))])
    bkit.link(nt, sep.outputs[2], r.inputs[0])
    bkit.link(nt, r.outputs[0], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = JOB.get("world", 1.0)
    # a back wall far behind, so the top of the frame is a lit room, not a void
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 26, JOB["table_z"] + 6))
    wall = bpy.context.object
    wall.scale = (80, 30, 1)
    wall.rotation_euler = (math.pi / 2, 0, 0)
    wall.data.materials.append(bkit.flat_mat("wall", (0.55, 0.50, 0.44), rough=0.9))
    return sun, spot


def main():
    sc = bkit.setup_render(JOB)
    table()
    mug()
    vals = coffee()
    root, lens = clip()
    sun, spot = lights()
    co = bkit.camera()
    keys = JOB["frames"]
    zr = JOB["table_z"] + 2.12
    for fi in FRAMES:
        t0 = time.time()
        st = keys[str(fi)]
        bkit.look_at(co, st["pos"], st["tgt"])
        co.data.lens = st["lens"]
        co.data.dof.focus_distance = float(np.linalg.norm(np.subtract(st["tgt"], st["pos"])))
        co.data.dof.aperture_fstop = st["fstop"]
        sun.energy = JOB["sun_strength"] * st["sun"]
        vals["sun"].outputs[0].default_value = JOB["sun_strength"] * st["sun"]
        intensity = JOB["lamp_intensity"] * st["lamp"]          # W/sr
        spot.energy = 4 * math.pi * intensity
        vals["lamp"].outputs[0].default_value = intensity
        lens.inputs["Emission Strength"].default_value = 40.0 * st["lamp"]
        hidden = st["clip"] is None
        for ch in root.children:
            ch.hide_render = hidden
        if not hidden:
            out_r, up = st["clip"]
            th = math.radians(JOB["lamp_angle"])
            root.location = (out_r * math.cos(th), out_r * math.sin(th), zr + up)
        sc.render.filepath = f"{OUT}/{fi:05d}.png"
        bpy.ops.render.render(write_still=True)
        print(f"FRAME {fi} {time.time() - t0:.2f}s", flush=True)


main()
