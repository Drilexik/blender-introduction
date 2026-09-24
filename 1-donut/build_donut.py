"""
Blender 5.0 script that builds the scene from the Blender Guru donut tutorial:
a donut with icing and sprinkles, a coffee cup and a saucer.

The modelling follows the same principles as the video:
  * donut  = torus + Subdivision Surface + "lumpy" proportional-style tweaks
  * icing  = duplicated top half of the donut + Shrinkwrap + Solidify
             + drips pulled down from the edge
  * sprinkles = Geometry Nodes (Distribute Points on Faces + Instance on Points)
                from a hidden "Sprinkles" collection, only on the top of the icing
  * cup    = cylinder profile (extrude / inset style), thickness modelled,
             handle made with Bridge Edge Loops, Subdivision Surface
  * saucer = cylinder profile with a well for the cup, Subdivision Surface

Usage (from this folder):
    blender -b -P build_donut.py            # with installed Blender 5.x
    python build_donut.py                   # with the `bpy` pip module
Outputs donut.blend and donut-preview.png next to this script.
"""

import math
import os
import random

import bpy  # must be imported before bmesh when used as a pip module
import bmesh
from mathutils import Matrix, Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "donut.blend")
PREVIEW_PATH = os.path.join(HERE, "donut-preview.png")

random.seed(7)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"
    return scene


def new_object(name, mesh, collection=None):
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def smooth_shade(mesh):
    for poly in mesh.polygons:
        poly.use_smooth = True


def add_subsurf(obj, levels=2, render_levels=3):
    mod = obj.modifiers.new("Subdivision", "SUBSURF")
    mod.levels = levels
    mod.render_levels = render_levels
    return mod


def lathe(name, profile, segments):
    """Spin an (r, z) profile around the Z axis (like Spin / Screw in Blender).
    Profile points with r == 0 become a single pole vertex."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r == 0:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([
                bm.verts.new((r * math.cos(2 * math.pi * i / segments),
                              r * math.sin(2 * math.pi * i / segments), z))
                for i in range(segments)
            ])
    for a, b in zip(rings, rings[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            if len(a) == 1:
                bm.faces.new((a[0], b[j], b[i]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[j], b[0]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    smooth_shade(mesh)
    return mesh


def principled(name, color, roughness=0.5, **inputs):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except AttributeError:
        pass
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    for key, value in inputs.items():
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = value
    mat.diffuse_color = (*color, 1.0)  # viewport (Solid mode) colour
    return mat


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------
def dough_material():
    """Browner top/bottom with the pale ring around the middle, like a fried donut."""
    mat = principled("Dough", (0.62, 0.30, 0.10), 0.55)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    absz = nt.nodes.new("ShaderNodeMath")
    absz.operation = "ABSOLUTE"
    noise_tex = nt.nodes.new("ShaderNodeTexNoise")
    noise_tex.inputs["Scale"].default_value = 60.0
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = 0.003
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.004
    ramp.color_ramp.elements[0].color = (0.85, 0.58, 0.30, 1)
    ramp.color_ramp.elements[1].position = 0.011
    ramp.color_ramp.elements[1].color = (0.50, 0.22, 0.06, 1)
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], absz.inputs[0])
    nt.links.new(noise_tex.outputs["Fac"], mix.inputs[0])
    nt.links.new(absz.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    # small bumps on the surface
    bump_noise = nt.nodes.new("ShaderNodeTexNoise")
    bump_noise.inputs["Scale"].default_value = 400.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    nt.links.new(bump_noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wood_material():
    mat = principled("Table wood", (0.35, 0.18, 0.08), 0.45)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.5, 0.25, 1.0)  # grain along Y
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 5.0
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 6.0
    wave.inputs["Detail Roughness"].default_value = 0.6
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.30, 0.15, 0.06, 1)
    ramp.color_ramp.elements[1].color = (0.42, 0.23, 0.11, 1)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# --------------------------------------------------------------------------
# donut
# --------------------------------------------------------------------------
MAJOR_R = 0.042   # 4.2 cm  -> donut ~12 cm wide
MINOR_R = 0.020   # 2 cm
DONUT_Z_SCALE = 0.85


def build_donut_mesh():
    """Torus (48 x 24) with lumpy, hand-made looking deformation."""
    bm = bmesh.new()
    nu, nv = 48, 24
    verts = []
    for i in range(nu):
        u = 2 * math.pi * i / nu
        ring = []
        for j in range(nv):
            v = 2 * math.pi * j / nv
            x = (MAJOR_R + MINOR_R * math.cos(v)) * math.cos(u)
            y = (MAJOR_R + MINOR_R * math.cos(v)) * math.sin(u)
            z = MINOR_R * math.sin(v)
            ring.append(bm.verts.new((x, y, z)))
        verts.append(ring)
    for i in range(nu):
        for j in range(nv):
            a, b = verts[i][j], verts[(i + 1) % nu][j]
            c, d = verts[(i + 1) % nu][(j + 1) % nv], verts[i][(j + 1) % nv]
            bm.faces.new((a, b, c, d))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()

    # "Proportional editing" lumps: low frequency noise along the normal,
    # a slightly squashed and not perfectly round shape.
    for v in bm.verts:
        n = noise.noise(v.co * 28.0 + Vector((3.1, 1.7, 0.4)))
        v.co += v.normal * n * MINOR_R * 0.12
        v.co.z *= DONUT_Z_SCALE
        v.co.x *= 1.03
    mesh = bpy.data.meshes.new("Donut")
    bm.to_mesh(mesh)
    bm.free()
    smooth_shade(mesh)
    return mesh


def build_icing_mesh(donut_mesh):
    """Duplicate the top half of the donut (Shift+D, P) and pull drips down."""
    bm = bmesh.new()
    bm.from_mesh(donut_mesh)
    threshold = 0.18 * MINOR_R * DONUT_Z_SCALE
    bmesh.ops.delete(bm, geom=[f for f in bm.faces
                               if f.calc_center_median().z < threshold],
                     context="FACES")

    # drips on the outer and inner edge
    boundary = [v for v in bm.verts if v.is_boundary]
    outer = [v for v in boundary if v.co.xy.length > MAJOR_R]
    inner = [v for v in boundary if v.co.xy.length <= MAJOR_R]

    def pull(edge_verts, count, depth_range, width):
        for _ in range(count):
            centre = random.uniform(0, 2 * math.pi)
            depth = random.uniform(*depth_range)
            for v in edge_verts:
                ang = math.atan2(v.co.y, v.co.x)
                d = abs((ang - centre + math.pi) % (2 * math.pi) - math.pi)
                if d < width:
                    f = 0.5 * (1 + math.cos(math.pi * d / width))
                    v.co.z -= depth * f
                    for e in v.link_edges:  # neighbour one ring up follows a bit
                        o = e.other_vert(v)
                        if not o.is_boundary:
                            o.co.z -= depth * f * 0.35

    pull(outer, 7, (0.006, 0.012), 0.14)
    pull(inner, 3, (0.002, 0.005), 0.30)

    mesh = bpy.data.meshes.new("Icing")
    bm.to_mesh(mesh)
    bm.free()
    smooth_shade(mesh)
    return mesh


def build_sprinkles_collection():
    """A few coloured sprinkles (cylinder with rounded ends) in a hidden collection."""
    coll = bpy.data.collections.new("Sprinkles")
    bpy.context.scene.collection.children.link(coll)
    colors = [
        (0.95, 0.95, 0.92),  # white
        (0.98, 0.75, 0.10),  # yellow
        (0.10, 0.45, 0.90),  # blue
        (0.15, 0.70, 0.30),  # green
        (0.90, 0.10, 0.35),  # raspberry
        (0.95, 0.40, 0.05),  # orange
    ]
    length, radius = 0.0065, 0.0008
    profile = [(0.0, -length / 2), (radius * 0.8, -length / 2),
               (radius, -length / 2 + radius * 0.8),
               (radius, length / 2 - radius * 0.8),
               (radius * 0.8, length / 2), (0.0, length / 2)]
    for idx, col in enumerate(colors):
        mesh = lathe(f"Sprinkle.{idx:03d}", profile, 8)
        mesh.transform(Matrix.Rotation(math.pi / 2, 4, "Y"))
        obj = new_object(f"Sprinkle.{idx:03d}", mesh, coll)
        add_subsurf(obj, 1, 2)
        obj.data.materials.append(principled(f"Sprinkle {idx}", col, 0.3))
        obj.location.x = idx * 0.01
    # hide the source collection like in the tutorial
    bpy.context.view_layer.layer_collection.children["Sprinkles"].exclude = True
    return coll


def sprinkles_node_group(collection):
    ng = bpy.data.node_groups.new("Sprinkles", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, link = ng.nodes, ng.links

    gin = n.new("NodeGroupInput")
    gout = n.new("NodeGroupOutput")

    # only on the top-facing part of the icing
    normal = n.new("GeometryNodeInputNormal")
    sep = n.new("ShaderNodeSeparateXYZ")
    compare = n.new("FunctionNodeCompare")
    compare.data_type = "FLOAT"
    compare.operation = "GREATER_THAN"
    compare.inputs["B"].default_value = 0.45
    link.new(normal.outputs["Normal"], sep.inputs[0])
    link.new(sep.outputs["Z"], compare.inputs["A"])

    distribute = n.new("GeometryNodeDistributePointsOnFaces")
    distribute.distribute_method = "POISSON"
    distribute.inputs["Distance Min"].default_value = 0.0035
    distribute.inputs["Density Max"].default_value = 30000.0
    distribute.inputs["Seed"].default_value = 3
    link.new(gin.outputs[0], distribute.inputs["Mesh"])
    link.new(compare.outputs["Result"], distribute.inputs["Selection"])

    # random spin around the surface normal
    rand_angle = n.new("FunctionNodeRandomValue")
    rand_angle.data_type = "FLOAT"
    rand_angle.inputs[3].default_value = 2 * math.pi  # Max (float)
    combine = n.new("ShaderNodeCombineXYZ")
    link.new(rand_angle.outputs[1], combine.inputs["Z"])  # float "Value"
    euler = n.new("FunctionNodeEulerToRotation")
    link.new(combine.outputs[0], euler.inputs[0])
    rotate = n.new("FunctionNodeRotateRotation")
    rotate.rotation_space = "LOCAL"
    link.new(distribute.outputs["Rotation"], rotate.inputs[0])
    link.new(euler.outputs[0], rotate.inputs[1])

    coll_info = n.new("GeometryNodeCollectionInfo")
    coll_info.inputs["Collection"].default_value = collection
    coll_info.inputs["Separate Children"].default_value = True
    coll_info.inputs["Reset Children"].default_value = True

    rand_idx = n.new("FunctionNodeRandomValue")
    rand_idx.data_type = "INT"
    rand_idx.inputs[4].default_value = 0     # Min (int)
    rand_idx.inputs[5].default_value = 1000  # Max (int)
    rand_idx.inputs["Seed"].default_value = 11

    rand_scale = n.new("FunctionNodeRandomValue")
    rand_scale.data_type = "FLOAT"
    rand_scale.inputs[2].default_value = 0.8  # Min (float)
    rand_scale.inputs[3].default_value = 1.1  # Max (float)
    rand_scale.inputs["Seed"].default_value = 5

    inst = n.new("GeometryNodeInstanceOnPoints")
    link.new(distribute.outputs["Points"], inst.inputs["Points"])
    link.new(coll_info.outputs[0], inst.inputs["Instance"])
    inst.inputs["Pick Instance"].default_value = True
    link.new(rand_idx.outputs[2], inst.inputs["Instance Index"])  # int "Value"
    link.new(rotate.outputs[0], inst.inputs["Rotation"])
    link.new(rand_scale.outputs[1], inst.inputs["Scale"])  # float "Value"

    join = n.new("GeometryNodeJoinGeometry")
    link.new(inst.outputs["Instances"], join.inputs[0])
    link.new(gin.outputs[0], join.inputs[0])
    link.new(join.outputs[0], gout.inputs[0])

    # tidy layout for people opening the node editor
    for x, node in enumerate([gin, normal, sep, compare, distribute, rand_angle,
                              combine, euler, rotate, coll_info, rand_idx,
                              rand_scale, inst, join, gout]):
        node.location = (x * 180, 0)
    gin.location, gout.location = (-200, 0), (1400, 0)
    normal.location, sep.location, compare.location = (-200, -250), (0, -250), (200, -250)
    distribute.location = (400, 0)
    rand_angle.location, combine.location = (400, -350), (600, -350)
    euler.location, rotate.location = (800, -350), (1000, -250)
    coll_info.location, rand_idx.location = (800, 300), (800, -550)
    rand_scale.location = (1000, -550)
    inst.location, join.location, gout.location = (1200, 0), (1400, 0), (1600, 0)
    return ng


def build_donut(collection, location):
    donut_mesh = build_donut_mesh()
    donut = new_object("Donut", donut_mesh, collection)
    add_subsurf(donut)
    donut.data.materials.append(dough_material())
    donut.location = location

    icing = new_object("Icing", build_icing_mesh(donut_mesh), collection)
    icing.parent = donut
    add_subsurf(icing)
    shrink = icing.modifiers.new("Shrinkwrap", "SHRINKWRAP")
    shrink.target = donut
    shrink.wrap_method = "NEAREST_SURFACEPOINT"
    shrink.wrap_mode = "OUTSIDE_SURFACE"
    shrink.offset = 0.0006
    solid = icing.modifiers.new("Solidify", "SOLIDIFY")
    solid.thickness = 0.0028
    solid.offset = 1.0
    solid.use_even_offset = True
    icing.data.materials.append(principled(
        "Icing", (0.88, 0.30, 0.48), 0.22,
        **{"Subsurface Weight": 0.15, "Subsurface Scale": 0.01}))

    sprinkles = build_sprinkles_collection()
    gn = icing.modifiers.new("Sprinkles", "NODES")
    gn.node_group = sprinkles_node_group(sprinkles)
    return donut


# --------------------------------------------------------------------------
# cup + saucer
# --------------------------------------------------------------------------
CUP_H = 0.068
WALL = 0.003


def cup_outer_r(z):
    t = max(0.0, min(1.0, z / CUP_H))
    return 0.027 + 0.0165 * t ** 0.55


def build_cup(collection, location):
    """Cup profile: foot ring, tapered wall, rim, inner wall and floor
    (the thickness is modelled so the handle can be bridged into the wall)."""
    outer_z = [0.004, 0.010, 0.016, 0.022, 0.030, 0.038, 0.046, 0.054, 0.061, 0.066]
    inner_z = [0.064, 0.056, 0.046, 0.036, 0.026, 0.018, 0.012]
    top_r = cup_outer_r(CUP_H)
    profile = [
        (0.0, 0.0035),                    # recessed bottom centre
        (0.018, 0.0035),
        (0.021, 0.0),                     # foot ring
        (0.025, 0.0),
    ]
    profile += [(cup_outer_r(z), z) for z in outer_z]
    profile += [
        (top_r, CUP_H),                   # rim
        (top_r - WALL * 0.5, CUP_H + 0.0012),
        (top_r - WALL, CUP_H),
    ]
    profile += [(cup_outer_r(z) - WALL, z) for z in inner_z]
    profile += [
        (cup_outer_r(0.008) - WALL - 0.002, 0.0085),  # inner floor
        (0.012, 0.0080),
        (0.0, 0.0080),
    ]
    segments = 32
    mesh = lathe("Cup", profile, segments)
    cup = new_object("Cup", mesh, collection)

    # --- handle: delete two faces on the side and Bridge Edge Loops ------
    bpy.context.view_layer.objects.active = cup
    cup.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()

    def side_face(z_lo, z_hi):
        # outer-wall face between the two heights, closest to the +X direction
        candidates = [f for f in bm.faces
                      if z_lo < f.calc_center_median().z < z_hi
                      and f.normal.xy.length > 0.5 and f.normal.x > 0
                      and f.calc_center_median().xy.length
                      > cup_outer_r(f.calc_center_median().z) - 0.001]
        return min(candidates, key=lambda f: abs(math.atan2(
            f.calc_center_median().y, f.calc_center_median().x)))

    upper = side_face(0.046, 0.054)
    lower = side_face(0.016, 0.022)
    for f in bm.faces:
        f.select = False
    for f in (upper, lower):
        f.select = True
    bmesh.update_edit_mesh(mesh)
    # extrude the two faces a little outward first, like in the video
    bpy.ops.mesh.extrude_region_shrink_fatten(
        TRANSFORM_OT_shrink_fatten={"value": 0.004})
    bpy.ops.mesh.delete(type="ONLY_FACE")
    bpy.ops.mesh.select_all(action="DESELECT")
    bm = bmesh.from_edit_mesh(mesh)
    for e in bm.edges:
        if e.is_boundary:
            e.select = True
    bmesh.update_edit_mesh(mesh)
    bpy.ops.mesh.bridge_edge_loops(number_cuts=14, interpolation="SURFACE",
                                   smoothness=1.6, profile_shape_factor=0.0)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.mesh.faces_shade_smooth()
    bpy.ops.object.mode_set(mode="OBJECT")
    cup.select_set(False)

    add_subsurf(cup)
    cup.data.materials.append(principled(
        "Ceramic", (0.90, 0.90, 0.87), 0.08, **{"Coat Weight": 0.3}))
    cup.location = location
    cup.rotation_euler.z = math.radians(-40)

    # coffee inside the cup
    coffee_z = 0.057
    coffee_r = cup_outer_r(coffee_z) - WALL + 0.0006
    coffee = new_object("Coffee", lathe("Coffee", [
        (0.0, coffee_z), (coffee_r, coffee_z), (coffee_r, coffee_z - 0.006),
        (0.0, coffee_z - 0.006)], 48), collection)
    coffee.parent = cup
    coffee.data.materials.append(principled("Coffee", (0.045, 0.018, 0.006), 0.12))
    return cup


def build_saucer(collection, location):
    profile = [
        (0.0, 0.0065),                    # top: flat well for the cup
        (0.028, 0.0065),
        (0.033, 0.0075),
        (0.040, 0.0085),                  # small ring around the well
        (0.050, 0.0110),
        (0.062, 0.0155),
        (0.071, 0.0200),
        (0.0755, 0.0215),                 # rim
        (0.0768, 0.0200),
        (0.0752, 0.0180),
        (0.068, 0.0140),                  # underside
        (0.056, 0.0090),
        (0.048, 0.0050),
        (0.045, 0.0),                     # foot ring
        (0.041, 0.0),
        (0.038, 0.0030),
        (0.0, 0.0030),
    ]
    saucer = new_object("Saucer", lathe("Saucer", profile, 48), collection)
    add_subsurf(saucer)
    saucer.data.materials.append(bpy.data.materials["Ceramic"])
    saucer.location = location
    return saucer


# --------------------------------------------------------------------------
# environment: table, lights, camera
# --------------------------------------------------------------------------
def build_environment(scene, target):
    env = bpy.data.collections.new("Environment")
    scene.collection.children.link(env)

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.5)
    table_mesh = bpy.data.meshes.new("Table")
    bm.to_mesh(table_mesh)
    bm.free()
    table = new_object("Table", table_mesh, env)
    table.data.materials.append(wood_material())

    world = bpy.data.worlds.new("World")
    scene.world = world
    try:
        world.use_nodes = True
    except AttributeError:
        pass
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.60, 0.68, 0.80, 1)
    bg.inputs["Strength"].default_value = 0.15

    def area(name, loc, energy, size, color=(1, 1, 1)):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = new_object(name, data, env)
        obj.location = loc
        direction = target - Vector(loc)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return obj

    area("Key light", (-0.45, -0.35, 0.55), 9, 0.35, (1.0, 0.95, 0.88))
    area("Fill light", (0.55, -0.30, 0.30), 2.5, 0.6, (0.85, 0.9, 1.0))
    area("Rim light", (0.10, 0.60, 0.40), 5, 0.3)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 55
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 6.0
    cam = new_object("Camera", cam_data, env)
    cam.location = (0.0, -0.46, 0.24)
    direction = target - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_data.dof.focus_distance = direction.length
    scene.camera = cam


def setup_render(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(os.environ.get("DONUT_SAMPLES", 160))
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = int(os.environ.get("DONUT_PERCENT", 100))
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass


# --------------------------------------------------------------------------
def main(render=True):
    scene = reset_scene()
    props = bpy.data.collections.new("Donut scene")
    scene.collection.children.link(props)

    build_cup(props, (0.065, 0.045, 0.0065))
    build_saucer(props, (0.065, 0.045, 0.0))
    build_donut(props, (-0.075, -0.025, MINOR_R * DONUT_Z_SCALE + 0.001))
    build_environment(scene, Vector((0.0, 0.01, 0.025)))
    setup_render(scene)

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    print("Saved", BLEND_PATH)
    if render:
        bpy.ops.render.render(write_still=True)
        print("Rendered", PREVIEW_PATH)


if __name__ == "__main__":
    import sys
    main(render="--no-render" not in sys.argv)
