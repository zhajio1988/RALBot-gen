import enum

from xml.dom import minidom
from systemrdl.node import AddressableNode, RootNode
from systemrdl.node import AddrmapNode, MemNode
from systemrdl.node import RegNode, RegfileNode, FieldNode

from . import typemaps

class Standard(enum.IntEnum):
    SPIRIT_1_0 = 1.0
    SPIRIT_1_1 = 1.1
    SPIRIT_1_2 = 1.2
    SPIRIT_1_4 = 1.4
    SPIRIT_1_5 = 1.5
    IEEE_1685_2009 = 2009
    IEEE_1685_2014 = 2014

#===============================================================================
class uvmGenExporter:
    def __init__(self, **kwargs):
        self.msg = None

        self.vendor = kwargs.pop("vendor", "example.org")
        self.library = kwargs.pop("library", "mylibrary")
        self.version = kwargs.pop("version", "1.0")
        self.standard = kwargs.pop("standard", Standard.IEEE_1685_2014)
        self.indentLvl = kwargs.pop("indentLvl", "  ")
        self.doc = None
        self._max_width = None
        self.uvmFileContent = list()
        self.uvmRegContent = list()
        self.uvmRegBlockContent = list()

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

    def genPkgImports(self): 
        uvmFileContent.add(indentLvl + 'import uvm_pkg::*;');
	uvmFileContent.add(indentLvl + '`include "uvm_macros.svh"');

    def extendsUvmReg(slef):
        return 'extends uvm_reg;'

    def extendsUvmRegBlock(self):
        return ' extends uvm_reg_block;'
    #---------------------------------------------------------------------------
    def genTopUvmRegBlock(self, node):
        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            node = node.top

    def export(self, node, path):
        self.msg = node.env.msg

        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            node = node.top

        if not isinstance(node, (AddrmapNode, MemNode)):
            raise TypeError("'node' argument expects type AddrmapNode or MemNode. Got '%s'" % type(node).__name__)

        # Determine if top-level node should be exploded across multiple
        # addressBlock groups
        explode = False

        # If top node is an addrmap, and it contains 1 or more children that
        # are:
        # - exclusively addrmap or mem
        # - and None of them are arrays
        # ... then it makes more sense to "explode" the
        # top-level node and make each of it's children their own addressBlock
        # (explode --> True)
        #
        # Otherwise, do not "explode" the top-level node
        # (explode --> False)
        if isinstance(node, AddrmapNode):
            addrblockable_children = 0
            non_addrblockable_children = 0

            for child in node.children(skip_not_present=False):
                if not isinstance(child, AddressableNode):
                    continue

                if isinstance(child, (AddrmapNode, MemNode)) and not child.is_array:
                    addrblockable_children += 1
                else:
                    non_addrblockable_children += 1

            if (non_addrblockable_children == 0) and (addrblockable_children >= 1):
                explode = True

        # Do the export!
        if explode:
            # top-node becomes the memoryMap
            print("debug point1", node.inst_name, node.get_property("name", default=None), node.get_property("desc"))

            # Top-node's children become their own addressBlocks
            for child in node.children(skip_not_present=False):
                if not isinstance(child, AddressableNode):
                    continue

                #TODO mmap
                self.add_addressBlock(mmap, child)
        else:
            # Not exploding apart the top-level node

            # Wrap it in a dummy memoryMap that bears it's name
            print("debug point2 ", "%s_mmap" % node.inst_name)

            # Export top-level node as a single addressBlock
            #TODO mmap
            self.add_addressBlock(mmap, node)

        # Write out UVM RegModel file
        #with open(path, "w") as f:
             

    #---------------------------------------------------------------------------
    def add_value(self, parent, tag, value):
        el = self.doc.createElement(tag)
        txt = self.doc.createTextNode(value)
        el.appendChild(txt)
        parent.appendChild(el)

    #---------------------------------------------------------------------------
    def add_nameGroup(self, parent, name, displayName=None, description=None):
        self.add_value(parent, "ipxact:name", name)
        if displayName is not None:
            self.add_value(parent, "ipxact:displayName", displayName)
        if description is not None:
            self.add_value(parent, "ipxact:description", description)

    #---------------------------------------------------------------------------
    def add_addressBlock(self, parent, node):
        self._max_width = None

        addressBlock = self.doc.createElement("ipxact:addressBlock")
        parent.appendChild(addressBlock)

        print("debug point3", node.inst_name, node.get_property("name", default=None), node.get_property("desc"))

        if not node.get_property("ispresent"):
            self.add_value(addressBlock, "ipxact:isPresent", "0")

        self.add_value(addressBlock, "ipxact:baseAddress", "'h%x" % node.absolute_address)

        # DNE: <ipxact:typeIdentifier>

        self.add_value(addressBlock, "ipxact:range", "'h%x" % node.size)

        # RDL only encodes the bus-width at the register level, but IP-XACT
        # only encodes this at the addressBlock level!
        # Insert the with element for now, but leave contents blank until it is
        # determined later.
        # Exporter has no choice but to enforce a constant width throughout
        width_el = self.doc.createElement("ipxact:width")
        addressBlock.appendChild(width_el)

        if isinstance(node, MemNode):
            self.add_value(addressBlock, "ipxact:usage", "memory")
            access = typemaps.access_from_sw(node.get_property("sw"))
            self.add_value(addressBlock, "ipxact:access", access)

        # DNE: <ipxact:volatile>
        # DNE: <ipxact:access>
        # DNE: <ipxact:parameters>

        for child in node.children(skip_not_present=False):
            if isinstance(child, RegNode):
                self.add_register(addressBlock, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(addressBlock, child)
            elif isinstance(child, MemNode):
                self.msg.warning(
                    "IP-XACT does not support 'mem' nodes that are nested in hierarchy. Discarding '%s'"
                    % child.get_path(),
                    child.inst.inst_src_ref
                )

        # Width should be known by now
        # If mem, and width isn't known, check memwidth
        if isinstance(node, MemNode) and (self._max_width is None):
            self._max_width = node.get_property("memwidth")

        if self._max_width is not None:
            width_el.appendChild(self.doc.createTextNode("%d" % self._max_width))
        else:
            width_el.appendChild(self.doc.createTextNode("32"))

        vendorExtensions = self.doc.createElement("ipxact:vendorExtensions")
        self.addressBlock_vendorExtensions(vendorExtensions, node)
        if vendorExtensions.hasChildNodes():
            parent.appendChild(vendorExtensions)

    #---------------------------------------------------------------------------
    def add_registerFile(self, parent, node):
        registerFile = self.doc.createElement("ipxact:registerFile")
        parent.appendChild(registerFile)

        self.add_nameGroup(registerFile,
            node.inst_name,
            node.get_property("name", default=None),
            node.get_property("desc")
        )

        if not node.get_property("ispresent"):
            self.add_value(registerFile, "ipxact:isPresent", "0")

        if node.is_array:
            for dim in node.array_dimensions:
                self.add_value(registerFile, "ipxact:dim", "%d" % dim)

        self.add_value(registerFile, "ipxact:addressOffset", "'h%x" % node.raw_address_offset)

        # DNE: <ipxact:typeIdentifier>

        if node.is_array:
            # For arrays, ipxact:range also defines the increment between indexes
            # Must use stride instead
            self.add_value(registerFile, "ipxact:range", "'h%x" % node.array_stride)
        else:
            self.add_value(registerFile, "ipxact:range", "'h%x" % node.size)

        for child in node.children(skip_not_present=False):
            if isinstance(child, RegNode):
                self.add_register(registerFile, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(registerFile, child)
            elif isinstance(child, MemNode):
                self.msg.warning(
                    "IP-XACT does not support 'mem' nodes that are nested in hierarchy. Discarding '%s'"
                    % child.get_path(),
                    child.inst.inst_src_ref
                )

        # DNE: <ipxact:parameters>

        vendorExtensions = self.doc.createElement("ipxact:vendorExtensions")
        self.registerFile_vendorExtensions(vendorExtensions, node)
        if vendorExtensions.hasChildNodes():
            parent.appendChild(vendorExtensions)

    #---------------------------------------------------------------------------
    def add_register(self, parent, node):
        register = self.doc.createElement("ipxact:register")
        parent.appendChild(register)

        self.add_nameGroup(register,
            node.inst_name,
            node.get_property("name", default=None),
            node.get_property("desc")
        )

        if not node.get_property("ispresent"):
            self.add_value(register, "ipxact:isPresent", "0")

        if node.is_array:
            if node.array_stride != (node.get_property("regwidth") / 8):
                self.msg.fatal(
                    "IP-XACT does not support register arrays whose stride is larger then the register's size",
                    node.inst.inst_src_ref
                )
            for dim in node.array_dimensions:
                self.add_value(register, "ipxact:dim", "%d" % dim)

        self.add_value(register, "ipxact:addressOffset", "'h%x" % node.raw_address_offset)

        # DNE: <ipxact:typeIdentifier>

        self.add_value(register, "ipxact:size", "%d" % node.get_property("regwidth"))

        if self._max_width is None:
            self._max_width = max(node.get_property("accesswidth"), node.get_property("regwidth"))
        else:
            self._max_width = max(node.get_property("accesswidth"), node.get_property("regwidth"), self._max_width)

        # DNE: <ipxact:volatile>
        # DNE: <ipxact:access>

        for field in node.fields(skip_not_present=False):
            self.add_field(register, field)

        # DNE <ipxact:alternateRegister> [...]
        # DNE: <ipxact:parameters>

        vendorExtensions = self.doc.createElement("ipxact:vendorExtensions")
        self.register_vendorExtensions(vendorExtensions, node)
        if vendorExtensions.hasChildNodes():
            parent.appendChild(vendorExtensions)

    #---------------------------------------------------------------------------
    def add_field(self, parent, node):
        field = self.doc.createElement("ipxact:field")
        parent.appendChild(field)

        self.add_nameGroup(field,
            node.inst_name,
            node.get_property("name", default=None),
            node.get_property("desc")
        )

        if not node.get_property("ispresent"):
            self.add_value(field, "ipxact:isPresent", "0")

        self.add_value(field, "ipxact:bitOffset", "%d" % node.low)

        reset = node.get_property("reset")
        if reset is not None:
            resets_el = self.doc.createElement("ipxact:resets")
            field.appendChild(resets_el)
            reset_el = self.doc.createElement("ipxact:reset")
            resets_el.appendChild(reset_el)
            self.add_value(reset_el, "ipxact:value", "'h%x" % reset)

        # DNE: <ipxact:typeIdentifier>

        self.add_value(field, "ipxact:bitWidth", "%d" % node.width)

        if node.is_volatile:
            self.add_value(field, "ipxact:volatile", "true")

        sw = node.get_property("sw")
        self.add_value(
            field,
            "ipxact:access",
            typemaps.access_from_sw(sw)
        )

        encode = node.get_property("encode")
        if encode is not None:
            enum_values_el = self.doc.createElement("ipxact:enumeratedValues")
            field.appendChild(enum_values_el)
            for enum_value in encode:
                enum_value_el = self.doc.createElement("ipxact:enumeratedValue")
                enum_values_el.appendChild(enum_value_el)
                self.add_nameGroup(enum_value_el,
                    enum_value.name,
                    enum_value.rdl_name,
                    enum_value.rdl_desc
                )
                self.add_value(enum_value_el, "ipxact:value", "'h%x" % enum_value.value)
                # DNE <ipxact:vendorExtensions>

        onwrite = node.get_property("onwrite")
        if onwrite:
            self.add_value(
                field,
                "ipxact:modifiedWriteValue",
                typemaps.mwv_from_onwrite(onwrite)
            )

        # DNE: <ipxact:writeValueConstraint>

        onread = node.get_property("onread")
        if onread:
            self.add_value(
                field,
                "ipxact:readAction",
                typemaps.readaction_from_onread(onread)
            )

        if node.get_property("donttest"):
            self.add_value(field, "ipxact:testable", "false")

        # DNE: <ipxact:reserved>

        # DNE: <ipxact:parameters>

        vendorExtensions = self.doc.createElement("ipxact:vendorExtensions")
        self.field_vendorExtensions(vendorExtensions, node)
        if vendorExtensions.hasChildNodes():
            parent.appendChild(vendorExtensions)

    #---------------------------------------------------------------------------
    def addressBlock_vendorExtensions(self, parent:minidom.Element, node:AddressableNode):
        pass

    def registerFile_vendorExtensions(self, parent:minidom.Element, node:AddressableNode):
        pass

    def register_vendorExtensions(self, parent:minidom.Element, node:RegNode):
        pass

    def field_vendorExtensions(self, parent:minidom.Element, node:FieldNode):
        pass
