import os
from systemrdl.node import AddressableNode, RootNode
from systemrdl.node import AddrmapNode, MemNode
from systemrdl.node import RegNode, RegfileNode, FieldNode

#===============================================================================
class uvmGenExporter:
    def __init__(self, **kwargs):
        self.msg = None

        self.languages = kwargs.pop("languages", "verilog")
        self.indent = kwargs.pop("indentLvl", "   ")
        self.headerFileContent = list()
        self.uvmFileContent = list()
        self.uvmRegContent = list()
        self.uvmRegBlockContent = list()

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

        if self.languages == 'verilog':
            self.definePrefix = '`'
        elif self.languages == 'c' or self.languages == 'cpp':
            self.definePrefix = '#'

        self.define = self.definePrefix + 'define '
        self.ifnDef = self.definePrefix + 'ifndef '
        self.ifDef = self.definePrefix + 'ifdef '
        self.endIf = self.definePrefix + 'endif'

    def genPkgImports(self):
        self.uvmFileContent.append('import uvm_pkg::*;')
        self.uvmFileContent.append('`include "uvm_macros.svh"')
    #---------------------------------------------------------------------------
    def export(self, node, path):
        self.msg = node.env.msg
        # Make sure output directory structure exists
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        filename = os.path.basename(path)
        filename = filename.upper().replace('.', '_')
        self.genDefineMacro(filename)

        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            node = node.top

        if not isinstance(node, AddrmapNode):
            raise TypeError("'node' argument expects type AddrmapNode. Got '%s'" % type(node).__name__)

        # Determine if top-level node should be exploded across multiple
        # addressBlock groups
        explode = False

        if isinstance(node, AddrmapNode):
            addrblockable_children = 0
            non_addrblockable_children = 0

            for child in node.children(unroll=False):
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
            # Top-node's children become their own addressBlocks
            for child in node.children(unroll=True):
                if not isinstance(child, AddressableNode):
                    continue
                self.add_addressBlock(child)
        else:
            # Not exploding apart the top-level node
            # Wrap it in a dummy memoryMap that bears it's name
            # Export top-level node as a single addressBlock
            self.add_addressBlock(node)

        self.headerFileContent.append(self.endIf)
        # Write out UVM RegModel file
        with open(path, "w") as f:
            f.write('\n'.join(self.headerFileContent))
    
    #---------------------------------------------------------------------------
    def genDefineMacro(self, tag): 
        self.headerFileContent.append(self.ifnDef + " __%s__" % tag)
        self.headerFileContent.append(self.define + " __%s__" % tag)
    #---------------------------------------------------------------------------
    def add_content(self, content):
        self.headerFileContent.append(self.define + content)
    #---------------------------------------------------------------------------
    def add_addressBlock(self, node):
        self._max_width = None

        for child in node.children(unroll=True):
            if isinstance(child, RegNode):
                self.add_register(node, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(child)

    def add_registerFile(self, node):
        for child in node.children(unroll=True):
            if isinstance(child, RegNode):
                self.add_register(node, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(child)

    #---------------------------------------------------------------------------
    def add_register(self, parent, node):
        regBlockName = parent.inst_name
        regName = node.inst_name
        if node.is_array:
            regClassName = "reg_" + regBlockName.lower() + "_" + regName.lower() + "_" + "%d" % node.current_idx 
        else:
            regClassName = "reg_" + regBlockName.lower() + "_" + regName.lower()
        print("class", regClassName, "extends uvm_reg;")
        for field in node.fields():
            print(self.indent, "rand uvm_reg_field", field.inst_name + ";");

        print()
        print(self.indent, "virtual function void build();")
        for field in node.fields():
            print(self.indent*2, field.inst_name, "= uvm_reg_field::type_id::create(" + field.inst_name + ", null, get_full_name());")
            isRand = 1 if field.is_sw_writable else 0
            isVolatile = 1 if field.is_volatile else 0
            print(self.indent*2, field.inst_name, ".configure(this,", "%0d," % field.width, "%0d," % field.low, 
            self.getFieldAccessType(field), ", ", isVolatile, self.resetStr(field), ",",  isRand, ", ", self.isOnlyField(node), ");")
        print(self.indent, "endfunction")
        #self.add_content(regClassName + " 'h%x" % node.absolute_address)

        print('''
   function new(string name = "%s");
      super.new(name, %0d, UVM_NO_COVERAGE);
   endfunction

   `uvm_object_utils("%s")
endclass''' %(regClassName, node.size*8 ,regClassName)
                )
        #for field in node.fields():
        #    self.add_field(node, field)

    def resetStr(self, node):
        reset = node.get_property("reset")
        if reset is not None:
            return  "'h%x, " % reset + "1" 
        else:
            return "0, 0"


    def isOnlyField(self, node):
        i = 0;
        for field in node.fields():
            i += 1;
        return 1 if (i == 1) else 0

    def getFieldAccessType(self, node):
        return "WO"

    #---------------------------------------------------------------------------
    def add_field(self, parent, node):
        regName = parent.inst_name
        fieldName = node.inst_name
        regFieldOffsetMacro = regName.upper() + "_" + fieldName.upper() + "_" + "OFFSET"
        #print("header file content ", "#define ", regFieldOffsetMacro, " %d" % node.low)
        self.add_content(regFieldOffsetMacro + " %d" % node.low)

        regFieldMaskMacro = regName.upper() + "_" + fieldName.upper() + "_" + "MASK"
        maskValue = hex(int('1' * node.width, 2) << node.low).replace("0x", "") 
        #print("header file content ", "#define ", regFieldMaskMacro, " 'h%s" % maskValue)
        self.add_content(regFieldMaskMacro + " 'h%s" % maskValue)

        encode = node.get_property("encode")
        if encode is not None:
            for enum_value in encode:
                print("debug point enum ", enum_value.name, enum_value.rdl_name, enum_value.rdl_desc)
                print("debug point ", "enum value", "'h%x" % enum_value.value)
