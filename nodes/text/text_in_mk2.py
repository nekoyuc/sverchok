# This file is part of project Sverchok. It's copyrighted by the contributors
# recorded in the version control history of the file, available from
# its original location https://github.com/nortikin/sverchok/commit/master
#  
# SPDX-License-Identifier: GPL3
# License-Filename: LICENSE

# made by: Linus Yng, haxed by zeffii to mk2
# pylint: disable=c0326

import locale
import io
import sys
import csv
import collections
import json
import ast

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty, IntProperty, PointerProperty

from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import node_id, multi_socket, updateNode

from sverchok.utils.sv_text_io_common import (
    FAIL_COLOR, READY_COLOR, TEXT_IO_CALLBACK,
    get_socket_type,
    new_output_socket,
    name_dict,
    text_modes,
)


class SvTextInFileImporterOp(bpy.types.Operator):

    bl_idname = "node.sv_textin_file_importer"
    bl_label = "File Importer"

    filepath: StringProperty(
        name="File Path",
        description="Filepath used for importing the file",
        maxlen=1024, default="", subtype='FILE_PATH')

    def execute(self, context):
        n = self.node
        t = bpy.data.texts.load(self.filepath)
        n.file_pointer = t
        return {'FINISHED'}

    def invoke(self, context, event):
        self.node = context.node
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}



# call structure
# op load->load->load-mode->get_data
# op reset-> reset. remove outputs, any data. as new
# op reload -> reload file without changing socket
# update if current_text and text cache:
#           get data and dispatch to sockets
# update if current_text and not text cache
#               try to reload()
# Test for one case and the others

def pop_all_data(node, n_id):
    node.csv_data.pop(n_id, None)
    node.list_data.pop(n_id, None)
    node.json_data.pop(n_id, None)


class SvTextInNodeMK2(bpy.types.Node, SverchCustomTreeNode):
    """
    Triggers: Text in from datablock
    Tooltip: Quickly load text from datablock into NodeView
    """

    bl_idname = 'SvTextInNodeMK2'
    bl_label = 'Text in+'
    bl_icon = 'PASTEDOWN'

    csv_data = {}
    list_data = {}
    json_data = {}

    def pointer_update(self, context):
        if self.file_pointer:
            self.text = self.file_pointer.name
        else:
            self.text = ""
        # need to do other stuff?

    # general settings
    n_id: StringProperty(default='')
    force_input: BoolProperty()

    textmode: EnumProperty(items=text_modes, default='CSV', update=updateNode, name='textmode')

    # name of loaded text, to support reloading
    text: StringProperty(default="")
    current_text: StringProperty(default="") # <----- what does this do again?
    file_pointer: bpy.props.PointerProperty(type=bpy.types.Text, poll=lambda s, o: True, update=pointer_update)

    # external file
    file: StringProperty(subtype='FILE_PATH')

    # csv standard dialect as defined in http://docs.python.org/3.3/library/csv.html
    # below are csv settings, user defined are set to 10 to allow more settings be added before
    # user defined to add ; as delimiter and , as decimal mark

    csv_dialects = [
        ('excel',      'Excel',        'Standard excel',   1),
        ('excel-tab',  'Excel tabs',   'Excel tab format', 2),
        ('unix',       'Unix',         'Unix standard',    3),
        ('semicolon',  'Excel ;,',     'Excel ; ,',        4),
        ('user',       'User defined', 'Define settings', 10)]

    csv_delimiters = [
        (',',      ',',      "Comma: ,",     1),
        ('\t',     'tab',    "Tab",          2),
        (';',      ';',      "Semi-colon ;", 3),
        ('CUSTOM', 'custom', "Custom",      10)]

    csv_decimalmarks = [
        ('.',       ".",        "Dot",            1),
        (',',       ',',        "Comma",          2),
        ('LOCALE',  'Locale',   "Follow locale",  3),
        ('CUSTOM',  'custom',   "Custom",        10)]

    socket_types = [
        ('v', 'Vertices',  "Point, vector or vertices data", 1),
        ('s', 'Data',      "Generals numbers or edge polygon data", 2),
        ('m', 'Matrix',    "Matrix data", 3)]

    csv_dialect: EnumProperty(
        items=csv_dialects, name="Dialect",
        description="Choose csv dialect", default='excel', update=updateNode)

    csv_header: BoolProperty(default=False, name='Header fields')
    csv_delimiter: EnumProperty(items=csv_delimiters, name="Delimiter", default=',')
    csv_custom_delimiter: StringProperty(default=':', name="Custom")
    csv_decimalmark: EnumProperty(items=csv_decimalmarks, default='LOCALE', name="Decimalmark")
    csv_custom_decimalmark: StringProperty(default=',', name="Custom")

    csv_skip_header_lines: IntProperty(default=0, name='skip n lines', description='some csv need n skips', min=0)
    csv_extended_mode: BoolProperty(name='extended mode')

    # Sverchok list options
    # choose which socket to interpret data as
    socket_type: EnumProperty(items=socket_types, default='s')

    def set_animatable(self, context):
        self.is_animatable = self.autoreload
    #interesting but dangerous, TODO
    autoreload: BoolProperty(default=False, description="Reload text file on every update", name='auto reload', update=set_animatable)

    # to have one socket output
    one_sock: BoolProperty(name='one socket', default=False)
    def sv_init(self, context):
        self.is_animatable = False

    def draw_buttons_ext(self, context, layout):
        if self.textmode == 'CSV':
            layout.prop(self, 'force_input')
            layout.prop(self, 'csv_skip_header_lines', text='Skip n header lines')
            layout.label(text="extra mode")
            layout.prop(self, "csv_extended_mode", toggle=True)

    def draw_buttons(self, context, layout):

        col = layout.column(align=True)
        col.prop(self, 'autoreload', toggle=True)  # reload() not work properly somehow 2016.10.07 | really? 2017.12.21
        if self.current_text:
            col.label(text="File: {0} loaded".format(self.current_text))
            row = col.row(align=True)

            if not self.autoreload:
                row.scale_y = 4.0 if self.prefs_over_sized_buttons else 1
                row.operator(TEXT_IO_CALLBACK, text='R E L O A D').fn_name = 'reload'
            col.operator(TEXT_IO_CALLBACK, text='R E S E T').fn_name = 'reset'

        else:
            row = col.row(align=True)
            row.prop_search(self, 'file_pointer', bpy.data, 'texts', text="Read")
            row.operator("node.sv_textin_file_importer", text='', icon='EMPTY_SINGLE_ARROW')

            row = col.row(align=True)
            row.prop(self, 'textmode', expand=True)
            col.prop(self, 'one_sock')
            if self.textmode == 'CSV':

                row = col.row(align=True)
                row.prop(self, 'csv_header', toggle=True)
                row.prop(self, 'csv_skip_header_lines', text='Skip n')
                row.prop(self, 'csv_dialect', text='')

                if self.csv_dialect == 'user':
                    col.label(text="Delimiter")
                    row = col.row(align=True)
                    row.prop(self, 'csv_delimiter', expand=True)
                    if self.csv_delimiter == 'CUSTOM':
                        col.prop(self, 'csv_custom_delimiter')

                    col.label(text="Decimalmark")
                    row = col.row(align=True)
                    row.prop(self, 'csv_decimalmark', expand=True)
                    if self.csv_decimalmark == 'CUSTOM':
                        col.prop(self, 'csv_custom_decimalmark')

            if self.textmode == 'SV':
                col.label(text="Select data type")
                row = col.row(align=True)
                row.prop(self, 'socket_type', expand=True)

            col.operator(TEXT_IO_CALLBACK, text='Load').fn_name = 'load'

    def sv_copy(self, node):
        self.n_id = ''

    def sv_free(self):
        # free potentially lots of data
        n_id = node_id(self)
        pop_all_data(self, n_id)

    def reset(self):
        n_id = node_id(self)
        self.outputs.clear()
        self.current_text = ''
        pop_all_data(self, n_id)


    def reload(self):
        # reload should ONLY be called from operator on ui change
        if self.textmode == 'CSV':
            self.reload_csv()
        elif self.textmode == 'SV':
            self.reload_sv()
        elif self.textmode == 'JSON':
            self.reload_json()

        # if we turn on reload on update we need a safety check for this to work.
        updateNode(self, None)

    def process(self):  # dispatch based on mode

        # upgrades older versions of ProfileMK3 to the version that has self.file_pointer
        if self.text and not self.file_pointer:
            text = self.get_bpy_data_from_name(self.text, bpy.data.texts)
            if text:
                self.file_pointer = text

        if not self.current_text:
            return
        if self.textmode == 'CSV':
            self.update_csv()
        elif self.textmode == 'SV':
            self.update_sv()
        elif self.textmode == 'JSON':
            self.update_json()
        elif self.textmode == 'TEXT':
            self.update_text()


    def load(self):
        if self.textmode == 'CSV':
            self.load_csv()
        elif self.textmode == 'SV':
            self.load_sv()
        elif self.textmode == 'JSON':
            self.load_json()
        elif self.textmode == 'TEXT':
            self.load_text()


    #
    # CSV methods.
    #

    def update_csv(self):
        n_id = node_id(self)

        if self.autoreload:
            self.reload_csv()

        if self.current_text and n_id not in self.csv_data:
            self.reload_csv()

            if n_id not in self.csv_data:
                print("CSV auto reload failed, press update")
                self.color = FAIL_COLOR
                return

        self.color = READY_COLOR
        csv_data = self.csv_data[n_id]
        if not self.one_sock:
            for name in csv_data.keys():
                if name in self.outputs and self.outputs[name].is_linked:
                    self.outputs[name].sv_set([csv_data[name]])
        else:
            name = 'one_sock'
            self.outputs['one_sock'].sv_set(list(csv_data.values()))

    def reload_csv(self):
        n_id = node_id(self)
        self.load_csv_data()

    def load_csv(self):
        n_id = node_id(self)
        self.load_csv_data()
        if not n_id in self.csv_data:
            print("Error, no data loaded")
        else:
            if not self.one_sock:
                for name in self.csv_data[n_id]:
                    self.outputs.new('SvStringsSocket', name)
            else:
                name = 'one_sock'
                self.outputs.new('SvStringsSocket', name)


    def load_csv_data(self):
        n_id = node_id(self)

        csv_data = collections.OrderedDict()

        if n_id in self.csv_data:
            del self.csv_data[n_id]

        f = io.StringIO(bpy.data.texts[self.text].as_string())

        # setup CSV options

        if self.csv_dialect == 'user':
            if self.csv_delimiter == 'CUSTOM':
                d = self.csv_custom_delimiter
            else:
                d = self.csv_delimiter

            reader = csv.reader(f, delimiter=d)
        elif self.csv_dialect == 'semicolon':
            self.csv_decimalmark = ','
            reader = csv.reader(f, delimiter=';')
        else:
            reader = csv.reader(f, dialect=self.csv_dialect)
            self.csv_decimalmark = '.'

        # setup parse decimalmark

        if self.csv_decimalmark == ',':
            get_number = lambda s: float(s.replace(',', '.'))
        elif self.csv_decimalmark == 'LOCALE':
            get_number = locale.atof
        elif self.csv_decimalmark == 'CUSTOM':
            if self.csv_custom_decimalmark:
                get_number = lambda s: float(s.replace(self.csv_custom_decimalmark, '.'))
        else:  # . default
            get_number = float

        # some csv contain a number of must-skip lines, these csv break the csv standard. but we still
        # want to be able to read them :)
        if self.csv_skip_header_lines:
            for _ in range(self.csv_skip_header_lines):
                next(reader)

        # load data
        for i, row in enumerate(reader):

            if i == 0:  # setup names
                if self.csv_header:
                    for name in row:
                        tmp = name
                        c = 1
                        while tmp in csv_data:
                            tmp = name+str(c)
                            c += 1
                        csv_data[str(tmp)] = []
                    continue  # first row is names
                else:
                    for j in range(len(row)):
                        csv_data["Col "+str(j)] = []

            for j, name in enumerate(csv_data):
                if not self.csv_extended_mode:
                    try:
                        n = get_number(row[j])
                        csv_data[name].append(n)
                    except Exception as err:
                        error = str(err)

                        if "could not convert string to float" in error:
                            if self.force_input:
                                csv_data[name].append(row[j])
                        else:
                            print('unhandled error:', error)

                else:
                    csv_data[name].append(row[j])

        if csv_data:
            if not csv_data[list(csv_data.keys())[0]]:
                return

            self.current_text = self.text
            self.csv_data[n_id] = csv_data


    #
    # Sverchok list data
    #
    # loads a python list using ast.literal_eval
    # any python list is considered valid input and you
    # have know which socket to use it with.

    def load_sv(self):
        n_id = node_id(self)
        self.load_sv_data()

        if n_id in self.list_data:
            new_output_socket(self, name_dict[self.socket_type], self.socket_type)

    def reload_sv(self):
        self.load_sv_data()

    def load_sv_data(self):
        data = None
        n_id = node_id(self)

        if n_id in self.list_data:
            del self.list_data[n_id]

        f = bpy.data.texts[self.text].as_string()

        try:
            data = ast.literal_eval(f)
        except Exception as err:
            sys.stderr.write('ERROR: %s\n' % str(err))
            print(sys.exc_info()[-1].tb_frame.f_code)
            pass

        if isinstance(data, (list, tuple)):
            self.list_data[n_id] = data
            self.color = READY_COLOR
            self.current_text = self.text
        else:
            self.color = FAIL_COLOR

    def update_sv(self):
        n_id = node_id(self)

        if self.autoreload:
            self.reload_sv()

        # nothing loaded, try to load and if it doesn't *work* -- then fail it.
        if n_id not in self.list_data and self.current_text:
            self.reload_sv()

        if n_id not in self.list_data:
            self.color = FAIL_COLOR
            return

        # load data into selected socket
        for item in ['Vertices', 'Data', 'Matrix']:
            if item in self.outputs and self.outputs[item].links:
                self.outputs[item].sv_set(self.list_data[n_id])
    #
    # JSON
    #
    # Loads JSON data
    #
    # format dict {socket_name : (socket type in {'v','m','s'", list data)
    #              socket_name1 :etc.
    # socket_name must be unique

    def load_json(self):
        n_id = node_id(self)
        self.load_json_data()
        json_data = self.json_data.get(n_id, [])
        if not json_data:
            self.current_text = ''
            return

        socket_order = json_data.get('socket_order')
        if socket_order:
            # avoid arbitrary socket assignment order
            def iterate_socket_order():
                for named_socket in socket_order:
                    data = json_data.get(named_socket)
                    yield named_socket, data

            socket_iterator = iterate_socket_order()
        else:
            socket_iterator = sorted(json_data.items())

        for named_socket, data in socket_iterator:
            if len(data) == 2 and data[0] in {'v', 's', 'm'}:
                new_output_socket(self, named_socket, data[0])
            else:
                self.color = FAIL_COLOR
                return


    def reload_json(self):
        n_id = node_id(self)
        self.load_json_data()

        if n_id in self.json_data:
            self.color = READY_COLOR

    def load_json_data(self):
        json_data = {}
        n_id = node_id(self)
        # reset data
        if n_id in self.json_data:
            del self.json_data[n_id]

        f = io.StringIO(bpy.data.texts[self.text].as_string())
        try:
            json_data = json.load(f)
        except:
            print("Failed to load JSON data")

        if not json_data:
            self.color = FAIL_COLOR
            return

        self.current_text = self.text
        self.json_data[n_id] = json_data

    def update_json(self):
        n_id = node_id(self)

        if self.autoreload:
            self.reload_json()

        if n_id not in self.json_data and self.current_text:
            self.reload_json()

        if n_id not in self.json_data:
            self.color = FAIL_COLOR
            return

        self.color = READY_COLOR
        json_data = self.json_data[n_id]
        for item in json_data:
            if item in self.outputs and self.outputs[item].is_linked:
                out = json_data[item][1]
                self.outputs[item].sv_set(out)


    def load_text(self):
        n_id = node_id(self)
        self.load_text_data()

        if n_id in self.list_data:
            new_output_socket(self, 'Text', 'SvTextSocket')

    def reload_text(self):
        self.load_text_data()

    def load_text_data(self):
        data = None
        n_id = node_id(self)

        if n_id in self.list_data:
            del self.list_data[n_id]

        data = [bpy.data.texts[self.text].as_string()]

        # try:
        #     data = ast.literal_eval(f)
        # except Exception as err:
        #     sys.stderr.write('ERROR: %s\n' % str(err))
        #     print(sys.exc_info()[-1].tb_frame.f_code)
        #     pass

        self.list_data[n_id] = data
        self.color = READY_COLOR
        self.current_text = self.text
        # else:
        #     self.color = FAIL_COLOR

    def update_text(self):
        n_id = node_id(self)

        if self.autoreload:
            self.reload_text()

        # nothing loaded, try to load and if it doesn't *work* -- then fail it.
        if n_id not in self.list_data and self.current_text:
            self.reload_text()

        if n_id not in self.list_data:
            self.color = FAIL_COLOR
            return

        # load data into selected socket
        self.outputs[0].sv_set(self.list_data[n_id])

    def save_to_json(self, node_data: dict):
        if not self.text:
            return  # empty node, nothing to do
        texts = bpy.data.texts

        node_data['current_text'] = self.text
        node_data['textmode'] = self.textmode
        if self.textmode == 'JSON':
            # add the json as full member to the tree :)
            text_str = texts[self.text].as_string()
            json_as_dict = json.loads(text_str)
            node_data['text_lines'] = {}
            node_data['text_lines']['stored_as_json'] = json_as_dict
        else:
            node_data['text_lines'] = texts[self.text].as_string()

    def load_from_json(self, node_data: dict, import_version: float):
        '''
        as it's a beta service, old IO json may not be compatible - in this interest
        of neat code we assume it finds everything.
        '''
        if import_version < 1.0:
            params = node_data.get('params')

            # original textin used 'current_text', textin+ uses 'text'
            current_text = params.get('current_text', params.get('text'))

            # it's not clear from the exporter code why textmode parameter isn't stored
            # in params.. for now this lets us look in both places. ugly but whatever.
            textmode = params.get('textmode')
            if not textmode:
                textmode = node_data.get('textmode')
            self.textmode = textmode
        else:
            current_text = self.current_text

        texts = bpy.data.texts
        if not current_text:
            self.info("`%s' doesn't store a current_text in params", self.name)

        elif not current_text in texts:
            new_text = texts.new(current_text)
            text_line_entry = node_data['text_lines']

            if self.textmode == 'JSON':
                if isinstance(text_line_entry, str):
                    self.debug('loading old text json content / backward compatibility mode')

                elif isinstance(text_line_entry, dict):
                    text_line_entry = json.dumps(text_line_entry['stored_as_json'])

            new_text.from_string(text_line_entry)

        else:
            # reaches here if  (current_text) and (current_text in texts)
            # can probably skip this..
            # texts[current_text].from_string(node_ref['text_lines'])
            self.debug('%s seems to reuse a text block loaded by another node - skipping', self.name)

        self.load()


def register():
    bpy.utils.register_class(SvTextInFileImporterOp)
    bpy.utils.register_class(SvTextInNodeMK2)


def unregister():
    bpy.utils.unregister_class(SvTextInNodeMK2)
    bpy.utils.unregister_class(SvTextInFileImporterOp)
