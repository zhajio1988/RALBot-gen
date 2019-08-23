import os
import re
import json
import math
import shutil
import hashlib
import distutils.dir_util
import xml.dom.minidom
from collections import OrderedDict

import jinja2 as jj
import markdown

from systemrdl.node import RootNode, AddressableNode, RegNode, RegfileNode, AddrmapNode, MemNode

class HTMLExporter:
    def __init__(self, markdown_inst=None, user_template_dir=None, user_context={}):
        """
        Constructor for the HTML exporter class

        Parameters
        ----------
        markdown_inst: ``markdown.Markdown``
            Override the class instance of the Markdown processor.
            See the `Markdown module <https://python-markdown.github.io/reference/#Markdown>`_
            for more details.
        user_template_dir: str
            Path to a directory where user-defined template overrides are stored.
        user_context: dict
            Additional context variables to load into the template namespace.
        """
        self.output_dir = None
        self.RALIndex = []
        self.current_id = -1
        self.footer = None
        self.title = None
        self.home_url = None
        self.user_context = user_context

        if markdown_inst is None:
            self.markdown_inst = markdown.Markdown()
        else:
            self.markdown_inst = markdown_inst

        if user_template_dir:
            loader = jj.ChoiceLoader([
                jj.FileSystemLoader(user_template_dir),
                jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
            ])
        else:
            loader = jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))

        self.jj_env = jj.Environment(
            loader=loader,
            autoescape=jj.select_autoescape(['html']),
            undefined=jj.StrictUndefined
        )

    def export(self, node, output_dir, **kwargs):
        """
        Perform the export!

        Parameters
        ----------
        node: systemrdl.Node
            Top-level node to export. Can be the top-level `RootNode` or any
            internal `AddrmapNode`.
        output_dir: str
            HTML output directory.
        footer: str
            (optional) Override footer text.
        title: str
            (optional) Override title text.
        home_url: str
            (optional) If a URL is specified, adds a home button to return to a
            parent home page.
        """

        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            node = node.top

        self.footer = kwargs.pop("footer", "Generated by RALBot HTML")
        self.title = kwargs.pop("title", "%s Reference" % node.get_property("name"))
        self.home_url = kwargs.pop("home_url", None)

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

        self.output_dir = output_dir
        self.RALIndex = []
        self.current_id = -1

        # Copy static files
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        distutils.dir_util.copy_tree(static_dir, self.output_dir, preserve_mode=0, preserve_times=0)

        # Make sure output directory structure exists
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "content"), exist_ok=True)

        # Traverse tree
        self.visit_addressable_node(node)

        # Write out RALIndex and other data to js file
        self.write_ral_data()

        # Write main index.html
        self.write_index_page()


    def visit_addressable_node(self, node, parent_id=None):
        self.current_id += 1
        this_id = self.current_id
        child_ids = []

        ral_entry = {
            'parent'    : parent_id,
            'children'  : child_ids,
            'name'      : node.inst.inst_name,
            'offset'    : BigInt(node.inst.addr_offset),
            'size'      : BigInt(node.size),
        }
        if node.inst.is_array:
            ral_entry['dims'] = node.inst.array_dimensions
            ral_entry['stride'] = BigInt(node.inst.array_stride)
            ral_entry['idxs'] = [0] * len(node.inst.array_dimensions)

        if isinstance(node, RegNode):
            ral_fields = []
            for field in node.fields():
                ral_field = {
                    'name' : field.inst.inst_name,
                    'lsb'  : field.inst.lsb,
                    'msb'  : field.inst.msb,
                    'reset': BigInt(field.get_property("reset", default=0)),
                    'disp' : 'H'
                }

                field_enum = field.get_property("encode")
                if field_enum is not None:
                    encode = OrderedDict()
                    for member in field_enum:
                        encode[member.name] = BigInt(member.value)
                    ral_field['encode'] = encode

                ral_fields.append(ral_field)

            ral_entry['fields'] = ral_fields

        # Insert entry now to ensure proper position in list
        self.RALIndex.append(ral_entry)

        # Recurse to children
        children = OrderedDict()
        for child in node.children():
            if not isinstance(child, AddressableNode):
                continue
            child_id = self.visit_addressable_node(child, this_id)
            child_ids.append(child_id)
            children[child_id] = child

        # Generate page for this node
        self.write_page(this_id, node, children)

        return this_id


    def write_ral_data(self):
        PageInfo = {
            "title" : self.title
        }
        path = os.path.join(self.output_dir, "js/data.js")
        with open(path, 'w') as fp:
            fp.write("var RALIndex = ")
            fp.write(RALBotJSEncoder(separators=(',', ':')).encode(self.RALIndex))
            fp.write(";")

            fp.write("var PageInfo = ")
            fp.write(RALBotJSEncoder(separators=(',', ':')).encode(PageInfo))
            fp.write(";")


    _template_map = {
        AddrmapNode : "addrmap.html",
        RegfileNode : "regfile.html",
        MemNode     : "mem.html",
        RegNode     : "reg.html",
    }

    def write_page(self, this_id, node, children):
        context = {
            'this_id': this_id,
            'node' : node,
            'children' : children,
            'has_description' : has_description,
            'has_enum_encoding' : has_enum_encoding,
            'get_enum_desc': self.get_enum_html_desc,
            'get_node_desc': self.get_node_html_desc,
            'get_child_addr_digits': self.get_child_addr_digits,
            'reversed': reversed,
            'list': list,
        }
        context.update(self.user_context)

        template = self.jj_env.get_template(self._template_map[type(node)])
        stream = template.stream(context)
        output_path = os.path.join(self.output_dir, "content", "%d.html" % this_id)
        stream.dump(output_path)


    def write_index_page(self):
        context = {
            'title': self.title,
            'footer_text': self.footer,
            'home_url': self.home_url
        }
        context.update(self.user_context)

        template = self.jj_env.get_template("index.html")
        stream = template.stream(context)
        output_path = os.path.join(self.output_dir, "index.html")
        stream.dump(output_path)

    def get_child_addr_digits(self, node):
        return math.ceil(math.log2(node.size + 1) / 4)

    def get_node_html_desc(self, node, increment_heading=0):
        """
        Wrapper function to get HTML description
        If no description, returns None

        Performs the following transformations on top of the built-in HTML desc
        output:
        - Increment any heading tags
        - Transform img paths that point to local files. Copy referenced image to output
        """

        desc = node.get_html_desc(self.markdown_inst)
        if desc is None:
            return desc

        # Keep HTML semantically correct by promoting heading tags if desc ends
        # up as a child of existing headings.
        if increment_heading > 0:
            def heading_replace_callback(m):
                new_heading = "<%sh%d>" % (
                    m.group(1),
                    min(int(m.group(2)) + increment_heading, 6)
                )
                return new_heading
            desc = re.sub(r'<(/?)[hH](\d)>', heading_replace_callback, desc)

        # Transform image references
        # If an img reference points to a file on the local filesystem, then
        # copy it to the output and transform the reference
        if increment_heading > 0:
            def img_transform_callback(m):
                dom = xml.dom.minidom.parseString(m.group(0))
                img_src = dom.childNodes[0].attributes["src"].value

                if os.path.isabs(img_src):
                    # Absolute local path, or root URL
                    pass
                elif re.match(r'(https?|file)://', img_src):
                    # Absolute URL
                    pass
                else:
                    # Looks like a relative path
                    # See if it points to something relative to the source file
                    new_path = self.try_resolve_rel_path(node.inst.def_src_ref, img_src)
                    if new_path is not None:
                        img_src = new_path

                if os.path.exists(img_src):
                    md5 = hashlib.md5(open(img_src,'rb').read()).hexdigest()
                    new_path = os.path.join(
                        self.output_dir, "content",
                        "%s_%s" % (md5[0:8], os.path.basename(img_src))
                    )
                    shutil.copyfile(img_src, new_path)
                    dom.childNodes[0].attributes["src"].value = os.path.join(
                        "content",
                        "%s_%s" % (md5[0:8], os.path.basename(img_src))
                    )
                    return dom.childNodes[0].toxml()

                return m.group(0)

            desc = re.sub(r'<\s*img.*/>', img_transform_callback, desc)
        return desc

    def get_enum_html_desc(self, enum_member):
        s = enum_member.get_html_desc(self.markdown_inst)
        if s:
            return s
        else:
            return ""

    def try_resolve_rel_path(self, src_ref, relpath):
        """
        Test if the source reference's base path + the relpath points to a file
        If it works, returns the new path.
        If not, return None
        """
        if src_ref is None:
            return None

        src_ref.derive_coordinates()
        if src_ref.filename is None:
            return None

        path = os.path.join(os.path.dirname(src_ref.filename), relpath)
        if not os.path.exists(path):
            return None

        return path

def has_description(node):
    """
    Test if node has a description defined
    """
    return "desc" in node.list_properties()

def has_enum_encoding(field):
    """
    Test if field is encoded with an enum
    """
    return "encode" in field.list_properties()

class BigInt:
    def __init__(self, v):
        self.v = v

class RALBotJSEncoder(json.JSONEncoder):
    def default(self, o): # pylint: disable=method-hidden
        if isinstance(o, BigInt):
            return "@@bigInt('%x',16)@@" % o.v
        else:
            return super().default(o)

    def encode(self, o):
        s = super().encode(o)
        s = s.replace('"@@', '')
        s = s.replace('@@"', '')
        return s
