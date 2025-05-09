# This file is part of project Sverchok. It's copyrighted by the contributors
# recorded in the version control history of the file, available from
# its original location https://github.com/nortikin/sverchok/commit/master
#  
# SPDX-License-Identifier: GPL3
# License-Filename: LICENSE


from math import sin, cos, radians

import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, EnumProperty

from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import updateNode, list_match_modes, list_match_func
from sverchok.utils.decorators_compilation import jit, njit

# from numba.typed import List
# @njit(cache=True)
def make_sphere_verts_combined(U, V, Radius):
    theta = radians(360 / U)
    phi = radians(180 / (V-1))

    pts = []
    pts = [[0, 0, Radius]]
    for i in range(1, V-1):
        pts_u = []
        sin_phi_i = sin(phi * i)
        for j in range(U):
            X = Radius * cos(theta * j) * sin_phi_i
            Y = Radius * sin(theta * j) * sin_phi_i
            Z = Radius * cos(phi * i)
            pts_u.append([X, Y, Z])
        pts.extend(pts_u)

    pts.append([0, 0, -Radius])
    return pts

def make_sphere_verts_separate(U, V, Radius):
    theta = radians(360/U)
    phi = radians(180/(V-1))

    pts = []
    pts = [[[0, 0, Radius] for i in range(U)]]
    for i in range(1, V-1):
        pts_u = []
        sin_phi_i = sin(phi*i)
        for j in range(U):
            X = Radius*cos(theta*j)*sin_phi_i
            Y = Radius*sin(theta*j)*sin_phi_i
            Z = Radius*cos(phi*i)
            pts_u.append([X, Y, Z])
        pts.append(pts_u)

    points_top = [[0, 0, -Radius] for i in range(U)]
    pts.append(points_top)
    return pts


# @jit(cache=True)
def sphere_verts(U, V, Radius, Separate):
    if Separate:
        return make_sphere_verts_separate(U, V, Radius)
    else:
        return make_sphere_verts_combined(U, V, Radius)

# @njit(cache=True)
def sphere_edges(U, V):
    nr_pts = U*V-(U-1)*2
    listEdg = []
    for i in range(V-2):
        listEdg.extend([[j+1+U*i, j+2+U*i] for j in range(U-1)])
        listEdg.append([U*(i+1), U*(i+1)-U+1])
    listEdg.extend([[i+1, i+1+U] for i in range(U*(V-3))])
    listEdg.extend([[0, i+1] for i in range(U)])
    listEdg.extend([[nr_pts-1, i+nr_pts-U-1] for i in range(U)])
    listEdg.reverse()
    return listEdg

# @njit(cache=True)
def sphere_faces(U, V):
    nr_pts = U*V-(U-1)*2
    listPln = []
    for i in range(V-3):
        listPln.append([U*i+2*U, 1+U*i+U, 1+U*i,  U*i+U])
        listPln.extend([[1+U*i+j+U, 2+U*i+j+U, 2+U*i+j, 1+U*i+j] for j in range(U-1)])

    for i in range(U-1):
        listPln.append([1+i, 2+i, 0])
        listPln.append([i+nr_pts-U, i+nr_pts-1-U, nr_pts-1])
    listPln.append([U, 1, 0])
    listPln.append([nr_pts-1-U, nr_pts-2, nr_pts-1])
    return listPln


class SphereNode(bpy.types.Node, SverchCustomTreeNode):
    ''' Sphere '''
    bl_idname = 'SphereNode'
    bl_label = 'Sphere'
    bl_icon = 'MESH_UVSPHERE'

    replacement_nodes = [('SvIcosphereNode', None, dict(Polygons='Faces'))]

    rad_: FloatProperty(name='Radius', description='Radius',
                         default=1.0,
                         options={'ANIMATABLE'}, update=updateNode)
    U_: IntProperty(name='U', description='U',
                     default=24, min=3,
                     options={'ANIMATABLE'}, update=updateNode)
    V_: IntProperty(name='V', description='V',
                     default=24, min=3,
                     options={'ANIMATABLE'}, update=updateNode)

    Separate: BoolProperty(name='Separate', description='Separate UV coords',
                            default=False,
                            update=updateNode)
    list_match: EnumProperty(
        name="List Match",
        description="Behavior on different list lengths, object level",
        items=list_match_modes, default="REPEAT",
        update=updateNode)

    def sv_init(self, context):
        self.inputs.new('SvStringsSocket', "Radius").prop_name = 'rad_'
        self.inputs.new('SvStringsSocket', "U").prop_name = 'U_'
        self.inputs.new('SvStringsSocket', "V").prop_name = 'V_'

        self.outputs.new('SvVerticesSocket', "Vertices")
        self.outputs.new('SvStringsSocket', "Edges")
        self.outputs.new('SvStringsSocket', "Polygons")

    def draw_buttons(self, context, layout):
        layout.prop(self, "Separate", text="Separate")
        
    def draw_buttons_ext(self, context, layout):
        layout.prop(self, "Separate", text="Separate")
        layout.prop(self, "list_match")

    def process(self):
        # inputs
        if 'Polygons' not in self.outputs:
            return

        Radius = self.inputs['Radius'].sv_get()[0]
        U = [max(int(u), 3) for u in self.inputs['U'].sv_get()[0]]
        V = [max(int(v), 3) for v in self.inputs['V'].sv_get()[0]]

        params = list_match_func[self.list_match]([U, V, Radius])

        # outputs
        if self.outputs['Vertices'].is_linked:
            verts = [sphere_verts(u, v, r, self.Separate) for u, v, r in zip(*params)]
            self.outputs['Vertices'].sv_set(verts)

        if self.outputs['Edges'].is_linked:
            edges = [sphere_edges(u, v) for u, v, r in zip(*params)]
            self.outputs['Edges'].sv_set(edges)

        if self.outputs['Polygons'].is_linked:
            faces = [sphere_faces(u, v) for u, v, r in zip(*params)]
            self.outputs['Polygons'].sv_set(faces)


def register():
    bpy.utils.register_class(SphereNode)


def unregister():
    bpy.utils.unregister_class(SphereNode)
