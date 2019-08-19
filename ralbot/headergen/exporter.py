import enum

from systemrdl.node import AddressableNode, RootNode
from systemrdl.node import AddrmapNode, MemNode
from systemrdl.node import RegNode, RegfileNode, FieldNode

#===============================================================================
class headerGenExporter:
    def __init__(self, **kwargs):
        self.msg = None

        self.indentLvl = kwargs.pop("indentLvl", "  ")
        self._max_width = None
        self.headerFileContent = list()

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

    def genDefineMacro(self): 
        headerFileContent.append(self.indentLvl + 'import uvm_pkg::*;')
        headerFileContent.append(self.indentLvl + '`include "uvm_macros.svh"')
    #---------------------------------------------------------------------------
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

            for child in node.children(skip_not_present=False, unroll=True):
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
            for child in node.children(skip_not_present=False, unroll=True):
                if not isinstance(child, AddressableNode):
                    continue

                #TODO mmap
                self.add_addressBlock(child)
        else:
            # Not exploding apart the top-level node

            # Wrap it in a dummy memoryMap that bears it's name
            print("debug point2 ", "%s_mmap" % node.inst_name)

            # Export top-level node as a single addressBlock
            #TODO mmap
            self.add_addressBlock(node)

        # Write out UVM RegModel file
        #with open(path, "w") as f:
             

    #---------------------------------------------------------------------------
    def add_value(self, parent, tag, value):
        el = self.doc.createElement(tag)
        txt = self.doc.createTextNode(value)
        el.appendChild(txt)
        parent.appendChild(el)

    #---------------------------------------------------------------------------
    def add_addressBlock(self, node):
        self._max_width = None

        print("debug point3", node.inst_name, node.get_property("name", default=None), node.get_property("desc"))

        #if not node.get_property("ispresent"):
        #    return

        print("debug point4", node.absolute_address, node.size)

        # DNE: <ipxact:volatile>
        # DNE: <ipxact:access>
        # DNE: <ipxact:parameters>

        for child in node.children(skip_not_present=False, unroll=True):
            if isinstance(child, RegNode):
                self.add_register(node, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(child)

    def add_registerFile(self, node):
        print("debug point1 registerFile", node.inst_name, node.get_property("name", default=None), node.get_property("desc"))

        #if not node.get_property("ispresent"):
        #    self.add_value(registerFile, "ipxact:isPresent", "0")

        if node.is_array:
            for dim in node.array_dimensions:
                print("debug point dim", "%d" % dim)

        print("debug point ", "'h%x" % node.raw_address_offset)
        print("debug point registerFile absolute_address ", "'h%x" % node.absolute_address)

        if node.is_array:
            # For arrays, ipxact:range also defines the increment between indexes
            # Must use stride instead
            print("debug point array_stride", "'h%x" % node.array_stride)
        else:
            print("debug point size", "'h%x" % node.size)

        for child in node.children(skip_not_present=False, unroll=True):
            if isinstance(child, RegNode):
                self.add_register(node, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(child)

    #---------------------------------------------------------------------------
    def add_register(self, parent, node):
        print("debug point register", parent.inst_name, node.inst_name, node.get_property("name", default=None), node.get_property("desc"))

        #if not node.get_property("ispresent"):
        #    self.add_value(register, "ipxact:isPresent", "0")

        if node.is_array:
            if node.array_stride != (node.get_property("regwidth") / 8):
                # TODO fatal
                self.msg.warning(
                    "IP-XACT does not support register arrays whose stride is larger then the register's size",
                    node.inst.inst_src_ref
                )
            for dim in node.array_dimensions:
                print("debug point dim1", "%d" % dim, "%d" % node.current_idx)

        print("debug point reg raw_address_offset ", "'h%x" % node.raw_address_offset)
        print("debug point reg absolute_address ", "'h%x" % node.absolute_address)

        regBlockName = parent.inst_name
        regName = node.inst_name
        if node.is_array:
            regMacro = regBlockName.upper() + "_" + regName.upper() + "_" + "%d" % node.current_idx 
        else:
            regMacro = regBlockName.upper() + "_" + regName.upper()
        print("header file content ", "#define ", regMacro, " 'h%x" % node.absolute_address)

        print("debug point regwidth ", "%d" % node.get_property("regwidth"))

        if self._max_width is None:
            self._max_width = max(node.get_property("accesswidth"), node.get_property("regwidth"))
        else:
            self._max_width = max(node.get_property("accesswidth"), node.get_property("regwidth"), self._max_width)

        for field in node.fields(skip_not_present=False):
            self.add_field(node, field)

    #---------------------------------------------------------------------------
    def add_field(self, parent, node):
        print("debug point field", parent.inst_name, node.inst_name, node.get_property("name", default=None), node.get_property("desc"))

        #if not node.get_property("ispresent"):
        #    self.add_value(field, "ipxact:isPresent", "0")

        print("debug point field offset ", "%d" % node.low)

        regName = parent.inst_name
        regFieldOffsetMacro = regName.upper() + "_" + node.inst_name
        print("header file content ", "#define ", regFieldOffsetMacro, " %d" % node.low)

        reset = node.get_property("reset")
        if reset is not None:
            print("debug point reset ", "'h%x" % reset)

        print("debug point width ", "%d" % node.width)

        encode = node.get_property("encode")
        if encode is not None:
            for enum_value in encode:
                print("debug point enum ", enum_value.name, enum_value.rdl_name, enum_value.rdl_desc)
                print("debug point ", "ipxact:value", "'h%x" % enum_value.value)
                # DNE <ipxact:vendorExtensions>
