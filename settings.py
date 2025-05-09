import sys
import os
import subprocess

import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, FloatVectorProperty, EnumProperty, IntProperty, FloatProperty, StringProperty
from sverchok.dependencies import sv_dependencies, pip, ensurepip, draw_message, get_icon
from sverchok import data_structure
from sverchok.core import tasks # don't remove this should fix #4229 (temp solution)
from sverchok.core import handlers
from sverchok.utils import logging
from sverchok.utils.sv_gist_tools import TOKEN_HELP_URL
from sverchok.utils.sv_extra_addons import draw_extra_addons
from sverchok.ui import color_def
from sverchok.ui.utils import message_on_layout

if bpy.app.version >= (2, 91, 0):
    PYPATH = sys.executable
else:
    PYPATH = bpy.app.binary_path_python

def get_params(prop_names_and_fallbacks, direct=False):
    """
    This function returns an object which you can use the . op on.
    example usage:

        from sverchok.settings import get_params

        props = get_params({'prop_name_1': 20, 'prop_name_2': 30})
        # props.prop_name_1    20
        # props.prop_name_2    30

    example usage using direct=True
        props = get_params({'prop_name_1': 20, 'prop_name_2': 30}, direct=True)
        # props[0]   20
        # props[1]   30 
    """
    from sverchok.utils.context_managers import sv_preferences

    props = lambda: None

    with sv_preferences() as prefs:
        for k, v in prop_names_and_fallbacks.items():
            try:
                value = getattr(prefs, k)
            except:
                print(f'returning a default for {k}')
                value = v
            setattr(props, k, value)

    if direct:
        return [getattr(props, k) for k in prop_names_and_fallbacks.keys()]

    return props

def get_param(prop_name, fallback):
    """
    for getting a single parameter from sv preferences
    example usage:

        from sverchok.settings import get_params
        prop = get_param("render_scale", 1.0)
        # prop = 1.0 if settings wasn't available, or else the current value
    """
    from sverchok.utils.context_managers import sv_preferences
    with sv_preferences() as prefs:
        try:
            value = getattr(prefs, prop_name)
        except:
            print(f'returning a default for {prop_name}')
            value = fallback
        return value

def apply_theme_if_necessary():
    if get_param("apply_theme_on_open", False):
        color_def.apply_theme()    
        print("applied theme.")

# getDpiFactor and getDpi are lifted from Animation Nodes :)

def get_dpi_factor():
    return get_dpi() / 72

def get_dpi():
    systemPreferences = bpy.context.preferences.system
    retinaFactor = getattr(systemPreferences, "pixel_size", 1)
    return systemPreferences.dpi * retinaFactor

class SvExPipInstall(bpy.types.Operator):
    """Install the package by calling pip install"""
    bl_idname = 'node.sv_ex_pip_install'
    bl_label = "Install the package"
    bl_options = {'REGISTER', 'INTERNAL'}

    package : bpy.props.StringProperty(name = "Package names")

    def execute(self, context):
        # https://github.com/robertguetzkow/blender-python-examples/tree/master/add_ons/install_dependencies
        environ_copy = dict(os.environ)
        environ_copy["PYTHONNOUSERSITE"] = "1"  # is set to disallow pip from checking the user site-packages
        cmd = [PYPATH, '-m', 'pip', 'install', '--upgrade'] + self.package.split(" ")
        ok = subprocess.call(cmd, env=environ_copy) == 0
        if ok:
            first_install = self.package in sv_dependencies and sv_dependencies[self.package] is None
            if first_install:
                self.report({'INFO'}, "%s installed successfully. Please restart Blender to see effect." % self.package)
            else:
                self.report({'INFO'}, "%s upgraded successfully. Please restart Blender to see effect." % self.package)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Cannot install %s, see console output for details" % self.package)
            return {'CANCELLED'}

class SvExEnsurePip(bpy.types.Operator):
    """Install PIP by using ensurepip module"""
    bl_idname = "node.sv_ex_ensurepip"
    bl_label = "Install PIP"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        cmd = [PYPATH, '-m', 'ensurepip']
        ok = subprocess.call(cmd) == 0
        if ok:
            self.report({'INFO'}, "PIP installed successfully. Please restart Blender to see effect.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Cannot install PIP, see console output for details")
            return {'CANCELLED'}

class SvSelectFreeCadPath(bpy.types.Operator):
    """Select a directory with FreeCAD Python API libraries"""
    bl_idname = "node.sv_select_freecad_path"
    bl_label = "Select FreeCAD Path"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory : bpy.props.StringProperty(
            name = "FreeCAD path",
            description = "Path to FreeCAD Python API libraries",
            subtype = 'DIR_PATH'
        )

    def execute(self, context):
        from sverchok.utils.context_managers import sv_preferences
        with sv_preferences() as prefs:
            prefs.FreeCAD_folder = self.directory
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class SvSetFreeCadPath(bpy.types.Operator):
    """Save FreeCAD path in system"""
    bl_idname = "node.sv_set_freecad_path"
    bl_label = "Set FreeCAD path"
    bl_options = {'REGISTER', 'INTERNAL'}
    FreeCAD_folder: bpy.props.StringProperty(name="FreeCAD python 3.7 folder")
    def execute(self, context):
        import sys
        import os
        site_packages = ''
        for p in sys.path:
            if 'site-packages' in p:
                site_packages = p
                break

        file_path = open(os.path.join(site_packages, "freecad_path.pth"), "w+")
        file_path.write(self.FreeCAD_folder)
        file_path.close()

        self.report({'INFO'}, "FreeCad path saved successfully. Please restart Blender to see effect.")
        return {'FINISHED'}

class SverchokPreferences(AddonPreferences):

    bl_idname = __package__

    def update_debug_mode(self, context):
        data_structure.DEBUG_MODE = self.show_debug

    def set_frame_change(self, context):
        handlers.set_frame_change(self.frame_change_mode)

    def update_theme(self, context):
        color_def.rebuild_color_cache()
        if self.auto_apply_theme:
            color_def.apply_theme()

    tab_modes = data_structure.enum_item_4(["General", "Node Defaults", "Extra Nodes", "Theme"])

    selected_tab: bpy.props.EnumProperty(
        items=tab_modes,
        description="pick viewing mode",
        default="General"
    )

    #  debugish...
    show_debug: BoolProperty(
        name="Debug mode",  # todo to remove, there is logging level for this
        description="Deprecated",
        default=False, subtype='NONE',
        update=update_debug_mode)

    no_data_color: FloatVectorProperty(
        name="No data", description='When a node can not get data',
        size=3, min=0.0, max=1.0,
        default=(1, 0.3, 0), subtype='COLOR',
    )

    exception_color: FloatVectorProperty(
        name="Error", description='When node has an exception',
        size=3, min=0.0, max=1.0,
        default=(0.8, 0.0, 0), subtype='COLOR',
    )

    # Profiling settings
    profiling_sections = [
        ("NONE", "Disable", "Disable profiling", 0),
        ("MANUAL", "Marked methods only", "Profile only methods that are marked with @profile decorator", 1),
        ("UPDATE", "Node tree update", "Profile whole node tree update process", 2)
    ]

    profile_mode: EnumProperty(name = "Profiling mode",
            items = profiling_sections,
            default = "NONE",
            description = "Performance profiling mode")

    developer_mode: BoolProperty(name = "Developer mode",
            description = "Show some additional panels or features useful for Sverchok developers only",
            default = False)

    #  theme settings

    sv_theme: EnumProperty(
        items=color_def.themes,
        name="Theme preset",
        description="Select a theme preset",
        update=color_def.color_callback,
        default="default_theme")

    auto_apply_theme: BoolProperty(
        name="Apply theme", description="Apply theme automatically",
        default=False)

    apply_theme_on_open: BoolProperty(
        name="Apply theme", description="Apply theme automatically",
        default=False)

    color_viz: FloatVectorProperty(
        name="Visualization", description='',
        size=3, min=0.0, max=1.0,
        default=(1, 0.589, 0.214), subtype='COLOR',
        update=update_theme)

    color_tex: FloatVectorProperty(
        name="Text", description='',
        size=3, min=0.0, max=1.0,
        default=(0.5, 0.5, 1), subtype='COLOR',
        update=update_theme)

    color_sce: FloatVectorProperty(
        name="Scene", description='',
        size=3, min=0.0, max=1.0,
        default=(0, 0.5, 0.2), subtype='COLOR',
        update=update_theme)

    color_lay: FloatVectorProperty(
        name="Layout", description='',
        size=3, min=0.0, max=1.0,
        default=(0.674, 0.242, 0.363), subtype='COLOR',
        update=update_theme)

    color_gen: FloatVectorProperty(
        name="Generator", description='',
        size=3, min=0.0, max=1.0,
        default=(0, 0.5, 0.5), subtype='COLOR',
        update=update_theme)

    #  frame change
    frame_change_modes = [
        ("PRE", "Pre", "Update Sverchok before frame change", 0),
        ("POST", "Post", "Update Sverchok after frame change", 1),
        ("NONE", "None", "Sverchok doesn't update on frame change", 2)
    ]

    frame_change_mode: EnumProperty(
        items=frame_change_modes,
        name="Frame change",
        description="Select frame change handler",
        default="POST",
        update=set_frame_change)

    #  Menu settings

    show_icons: BoolProperty(
        name="Show icons in Shift-A menu",
        default=False,
        description="Use icons in Shift-A menu")

    over_sized_buttons: BoolProperty(
        default=False, name="Big buttons", description="Very big buttons")

    node_panel_modes = [
            ("X", "Do not show", "Do not show node buttons", 0),
            ("T", "T panel", "Show node buttons under the T panel", 1),
            ("N", "N panel", "Show node under the N panel", 2)
        ]

    node_panels: EnumProperty(
        items = node_panel_modes,
        name = "Display node buttons",
        description = "Where to show node insertion buttons. Restart Blender to apply changes.",
        default = "T")

    node_panels_icons_only : BoolProperty(
            name = "Display icons only",
            description = "Show node icon only when icon has an icon, otherwise show it's name",
            default = True
        )

    node_panels_columns : IntProperty(
            name = "Columns",
            description = "Number of icon panels per row; Set to 0 for automatic selection",
            default = 0,
            min = 0, max = 12
        )

    input_links_options = [
            ('NONE', "Do not show", "Do not show", 0),
            ('QUICKLINK', "Show single option only",
                "Show the button only for cases when there is only one node to be created can be suggested; do not show the menu", 1),
            ('ALL', "Show `Create parameter' options",
                "Show the button with a menu with options to create parameter nodes", 2)
        ]

    show_input_menus : EnumProperty(
            name = "Show input menus",
            description = "Whether to display buttons near node socket inputs to automatically create parameter nodes",
            items = input_links_options,
            default = 'QUICKLINK'
        )

    ##  BLF/BGL/GPU  scale and location props

    render_scale: FloatProperty(
        default=1.0, min=0.01, step=0.01, description='default render scale')

    render_location_xy_multiplier: FloatProperty(
        default=1.0, min=0.01, step=0.01, description='default render location scale')


    stethoscope_view_scale: FloatProperty(
        default=1.0, min=0.01, step=0.01, description='default stethoscope scale')

    index_viewer_scale: FloatProperty(
        default=1.0, min=0.01, step=0.01, description='default index viewer scale')

    auto_update_angle_values: BoolProperty(
        default=True,
        description="Auto update angle values when angle units are changed to preserve the angle")

    def set_nodeview_render_params(self, context):
        self.render_scale = get_dpi_factor()   # this was intended as a general draw scale multiplier, not location but size.
        self.render_location_xy_multiplier = get_dpi_factor()

    ##
    datafiles = os.path.join(bpy.utils.user_resource('DATAFILES', path='sverchok', create=True))

    external_editor: StringProperty(description='which external app to invoke to view sources')
    real_sverchok_path: StringProperty(description='use with symlinked to get correct src->dst')

    github_token : StringProperty(name = "GitHub API Token",
                    description = "GitHub API access token. Should have 'gist' OAuth scope.",
                    subtype="PASSWORD")

    # Logging settings

    def update_log_level(self, context):
        logging.info("Setting log level to %s", self.log_level)
        logging.setLevel(self.log_level)

    log_levels = [
            ("DEBUG", "Debug", "Debug output", 0),
            ("INFO", "Information", "Informational output", 1),
            ("WARNING", "Warnings", "Show only warnings and errors", 2),
            ("ERROR", "Errors", "Show errors only", 3)
        ]

    log_level: EnumProperty(name = "Logging level",
            description = "Minimum events severity level to output. All more severe messages will be logged as well.",
            items = log_levels,
            update = update_log_level,
            default = "INFO")

    log_to_buffer: BoolProperty(name = "Log to text buffer",
            description = "Enable log output to internal Blender's text buffer (requires restart)",
            default = True)
    log_to_buffer_clean: BoolProperty(name = "Clear buffer at startup",
            description = "Clear text buffer at each Blender startup (requires restart)",
            default = False)
    log_to_file: BoolProperty(name = "Log to file",
            description = "Enable log output to external file (requires restart)",
            default = False)
    log_to_console: BoolProperty(name = "Log to console",
            description = "Enable log output to console / terminal / standard output (requires restart)",
            default = True)

    log_buffer_name: StringProperty(name = "Buffer name", default = "sverchok.log")
    log_file_name: StringProperty(name = "File path", default = os.path.join(datafiles, "sverchok.log"))


    # updating sverchok
    dload_archive_name: StringProperty(name="archive name", default="master") # default = "master"
    dload_archive_path: StringProperty(name="archive path", default="https://github.com/nortikin/sverchok/archive/")
    available_new_version: bpy.props.BoolProperty(default=False)

    FreeCAD_folder: StringProperty(
            name="FreeCAD python 3.7 folder",
            description = "Path to FreeCAD Python API library files (FreeCAD.so on Linux and MacOS, FreeCAD.dll on Windows). On Linux the usual location is /usr/lib/freecad/lib, on Windows it can be something like E:\programs\conda-0.18.3\\bin"
        )

    def general_tab(self, layout):
        col = layout.row().column()
        col_split = col.split(factor=0.5)
        col1 = col_split.column()

        toolbar_box = col1.box()
        toolbar_box.label(text="Node toolbars")
        toolbar_box.prop(self, "node_panels")
        if self.node_panels != "X":
            toolbar_box.prop(self, "node_panels_icons_only")
            if self.node_panels_icons_only:
                toolbar_box.prop(self, "node_panels_columns")

        col1.prop(self, "external_editor", text="Ext Editor")
        col1.prop(self, "real_sverchok_path", text="Src Directory")

        box = col1.box()
        box.label(text="Export to Gist")
        box.prop(self, "github_token")
        box.label(text="To export node trees to gists, you have to create a GitHub API access token.")
        box.label(text="For more information, visit " + TOKEN_HELP_URL)
        box.operator("node.sv_github_api_token_help", text="Visit documentation page")

        col2 = col_split.split().column()
        col2.label(text="Frame change handler:")
        col2.row().prop(self, "frame_change_mode", expand=True)
        col2.separator()

        col2box = col2.box()
        col2box.label(text="Debug:")
        col2box.prop(self, "show_debug")
        col2box.prop(self, "developer_mode")

        log_box = col2.box()
        log_box.label(text="Logging:")
        log_box.prop(self, "log_level")

        buff_row = log_box.row()
        buff_row.prop(self, "log_to_buffer")
        if self.log_to_buffer:
            buff_row.prop(self, "log_buffer_name")
            log_box.prop(self, "log_to_buffer_clean")

        file_row = log_box.row()
        file_row.prop(self, "log_to_file")
        if self.log_to_file:
            file_row.prop(self, "log_file_name")

        log_box.prop(self, "log_to_console")

    def node_defaults_tab(self, layout):
        row = layout.row()
        col = row.column(align=True)
        row_sub1 = col.row().split(factor=0.5)
        box_sub1 = row_sub1.box()
        box_sub1_col = box_sub1.column(align=True)

        box_sub1_col.label(text='Render Scale & Location')
        box_sub1_col.label(text=f'xy multiplier: {self.render_location_xy_multiplier}')

        box_sub1_col.label(text='Stethoscope')
        box_sub1_col.prop(self, 'stethoscope_view_scale', text='scale')

        box_sub1_col.label(text='Index Viewer')
        box_sub1_col.prop(self, 'index_viewer_scale', text='scale')

        box_sub2 = box_sub1.box()
        box_sub2_col = box_sub2.column(align=True)
        box_sub2_col.label(text='Angle Units')
        box_sub2_col.prop(self, 'auto_update_angle_values', text="Auto Update Angle Values")

        col3 = row_sub1.split().column()

    def theme_tab(self, layout):
        row = layout.row()
        col = row.column(align=True)
        split = col.row().split(factor=0.66)
        split2 = col.row().split(factor=0.66)
        left_split = split.row()
        right_split = split.row()

        split_viz_colors = left_split.column().split(factor=0.5, align=True)

        if True:
            col1 = split_viz_colors.column()
            for name in ['color_viz', 'color_tex', 'color_sce']:
                r = col1.row()
                r.prop(self, name)

            col2 = split_viz_colors.column()
            for name in ['color_lay', 'color_gen']:
                r = col2.row()
                r.prop(self, name)

        split_extra_colors = split2.column().split()
        col_x1 = split_extra_colors.column()
        col_x1.label(text="Error colors: ( error / no data )")
        row_x1 = col_x1.row()
        row_x1.prop(self, "exception_color", text='')
        row_x1.prop(self, "no_data_color", text='')

        col_x2 = split_extra_colors.split().column()

        col3 = right_split.column()
        col3.label(text='Theme:')
        col3.prop(self, 'sv_theme', text='')
        col3.separator()
        col3.prop(self, 'auto_apply_theme', text="Auto apply theme changes")
        col3.prop(self, 'apply_theme_on_open', text="Apply theme when opening file")
        col3.operator('node.sverchok_apply_theme', text="Apply theme to layouts")

    def extra_nodes_tab(self, layout):

        def draw_freecad_ops():
            dependency = sv_dependencies['freecad']
            col = box.column(align=True)
            col.label(text=dependency.message, icon=get_icon(dependency.module))
            row = col.row(align=True)
            row.operator('wm.url_open', text="Visit package website").url = dependency.url
            if dependency.module is None:
                tx = "Set path"
            else:
                tx = "Reset path"
            row.prop(self, 'FreeCAD_folder')
            row.operator('node.sv_select_freecad_path', text="Browse...").directory = self.FreeCAD_folder
            row.operator('node.sv_set_freecad_path', text=tx).FreeCAD_folder = self.FreeCAD_folder
            return row

        message_on_layout(layout, """Sverchok can use several external libraries, that provide \
some mathematical or other functions. We call such libraries "Dependencies". \
When these libraries are available, you will be able to use much more nodes \
in Sverchok. If you do not need all these features, you can skip installation of \
dependencies, or install only some of them.""")

        box = layout.box()
        box.label(text="Dependencies:")

        row = draw_message(box, "pip")
        if pip is not None:
            row.operator('node.sv_ex_pip_install', text="Upgrade PIP").package = "pip setuptools wheel"
        else:
            if ensurepip is not None:
                row.operator('node.sv_ex_ensurepip', text="Install PIP")
            else:
                row.operator('wm.url_open', text="Installation instructions").url = "https://pip.pypa.io/en/stable/installing/"

        draw_message(box, "scipy")
        draw_message(box, "geomdl")
        draw_message(box, "skimage")
        draw_message(box, "mcubes")
        draw_message(box, "circlify")
        draw_message(box, "cython")
        draw_message(box, "numba")

        draw_freecad_ops()

        if any(package.module is None for package in sv_dependencies.values()):
            box.operator('wm.url_open', text="Read installation instructions for missing dependencies").url = "https://github.com/nortikin/sverchok/wiki/Dependencies"
        draw_extra_addons(layout)

    def draw(self, context):

        layout = self.layout
        layout.row().prop(self, 'selected_tab', expand=True)

        if self.selected_tab == "General":
            self.general_tab(layout)


        if self.selected_tab == "Node_Defaults":
            self.node_defaults_tab(layout)

        if self.selected_tab == "Extra_Nodes":
            self.extra_nodes_tab(layout)

        if self.selected_tab == "Theme":
            self.theme_tab(layout)

        # FOOTER

        row = layout.row()
        col = row.column(align=True)
        col.label(text="Links:")
        row1 = col.row(align=True)
        row1.scale_y = 2.0
        row1.operator('wm.url_open', text='Sverchok home page').url = 'http://nikitron.cc.ua/blend_scripts.html'
        row1.operator('wm.url_open', text='Documentation').url = 'http://nikitron.cc.ua/sverch/html/main.html'

        if self.available_new_version:
            row1.operator('node.sverchok_update_addon', text='Upgrade Sverchok addon')
        else:
            row1.operator('node.sverchok_check_for_upgrades_wsha', text='Check for new version')


def register():
    bpy.utils.register_class(SvExPipInstall)
    bpy.utils.register_class(SvExEnsurePip)
    bpy.utils.register_class(SvSetFreeCadPath)
    bpy.utils.register_class(SvSelectFreeCadPath)
    bpy.utils.register_class(SverchokPreferences)


def unregister():
    bpy.utils.unregister_class(SverchokPreferences)
    bpy.utils.unregister_class(SvSelectFreeCadPath)
    bpy.utils.unregister_class(SvSetFreeCadPath)
    bpy.utils.unregister_class(SvExEnsurePip)
    bpy.utils.unregister_class(SvExPipInstall)

if __name__ == '__main__':
    register()
