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
        self.uvmAddrMapContent = list()
        self.uvmRegContent = list()
        self.uvmMemContent = list()
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
        self.isSwReadable = True
        self.isSwWriteable = True
        self.isRclr = False
        self.isRset = False
        self.isWoset = False
        self.isWoclr = False

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

        for i in self.uvmRegContent:
            print(i)
        for i in self.uvmMemContent:
            print(i)
        for i in self.uvmRegBlockContent:
            print(i)    
        for i in self.uvmAddrMapContent:
            print(i)    
    #---------------------------------------------------------------------------
    def genDefineMacro(self, tag): 
        self.headerFileContent.append(self.ifnDef + " __%s__" % tag)
        self.headerFileContent.append(self.define + " __%s__" % tag)
    #---------------------------------------------------------------------------
    def add_uvm_top_content(self, indentLvl="", content=""):
        self.uvmAddrMapContent.append(indentLvl + content)
    #---------------------------------------------------------------------------
    def add_uvm_block_content(self, indentLvl="", content=""):
        self.uvmRegBlockContent.append(indentLvl + content)    
    #---------------------------------------------------------------------------
    def add_uvm_reg_content(self, indentLvl="", content=""):
        self.uvmRegContent.append(indentLvl + content)
    #---------------------------------------------------------------------------
    def add_uvm_mem_content(self, indentLvl="", content=""):
        self.uvmMemContent.append(indentLvl + content)
    #---------------------------------------------------------------------------
    def add_addressBlock(self, node):
        self._max_width = None
        regNode = list()
        regBlockNode = list()
        memNode = list()

        for child in node.children(unroll=True):
            if isinstance(child, RegNode):
                self.add_register(node, child)
                regNode.append(child);
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(node, child)
                regBlockNode.append(child)
            elif isinstance(child, MemNode):
                self.add_memFile(node, child)
                memNode.append(child)

        allNodes = regNode + regBlockNode + memNode
        self.add_uvm_top_content(content="class "+ node.inst_name + " extends uvm_reg_block;")
        for child in allNodes:
            self.add_uvm_top_content(self.indent, "rand %s %s;" %(self.get_class_name(node, child), child.inst_name));            
        self.add_uvm_top_content('''
   `uvm_object_utils("%s")
   function new(string name = "%s");
      super.new(name, UVM_NO_COVERAGE);
   endfunction ''' %(node.inst_name, node.inst_name))
        self.add_uvm_top_content(self.indent, "")
        self.add_uvm_top_content(self.indent, "virtual function void build();")        
        # TODO
        self.add_uvm_top_content(self.indent*2, "default_map = create_map(\"default_map\", `UVM_REG_ADDR_WIDTH'h0, 8, UVM_LITTLE_ENDIAN, 1);")

        for child in regNode:
            self.add_uvm_top_content(self.indent*2, child.inst_name + "=" + self.get_class_name(node, child) +"::type_id::create(\"" + child.inst_name + "\");")
            self.add_uvm_top_content(self.indent*2, "%s.configure(this,null,\"%s\");" % (child.inst_name, child.inst_name))
            self.add_uvm_top_content(self.indent*2, "%s.build();" %(child.inst_name))
            self.add_uvm_top_content(self.indent*2, "default_map.add_reg(%s, `UVM_REG_ADDR_WIDTH'h%x, " % (child.inst_name, child.address_offset) + "\"RW\", 0);" )

        for child in regBlockNode:
            self.add_uvm_top_content(self.indent*2, child.inst_name + "=" + self.get_class_name(node, child) +"::type_id::create(\"" + child.inst_name + "\",,get_full_name());")
            self.add_uvm_top_content(self.indent*2, "%s.configure(this, \"%s\");" %(child.inst_name, child.inst_name))
            self.add_uvm_top_content(self.indent*2, "%s.build();" %(child.inst_name))
            self.add_uvm_top_content(self.indent*2, "default_map.add_submap(%s.default_map, `UVM_REG_ADDR_WIDTH'h%x);" % (child.inst_name, child.address_offset))

        for child in memNode:
            self.add_uvm_top_content(self.indent*2, child.inst_name + "=" + self.get_class_name(node, child) +"::type_id::create(\"" + child.inst_name + "\",,get_full_name());")
            self.add_uvm_top_content(self.indent*2, "%s.configure(this, \"%s\");" %(child.inst_name, child.inst_name))
            self.add_uvm_top_content(self.indent*2, "default_map.add_mem(%s.default_map, `UVM_REG_ADDR_WIDTH'h%x, \"RW\");" % (child.inst_name, child.address_offset))

        self.add_uvm_top_content(self.indent, "endfunction")
        self.add_uvm_top_content(content="endclass")
    #---------------------------------------------------------------------------
    def add_registerFile(self, parent, node):
        regNode = list()
        regBlockNode = list()
        memNode = list()        
        for child in node.children(unroll=True):
            if isinstance(child, RegNode):
                self.add_register(parent, child)
                regNode.append(child);
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(parent, child)
                regBlockNode.append(child)
            elif isinstance(child, MemNode):
                self.add_memFile(parent, child)
                memNode.append(child)


    #---------------------------------------------------------------------------
    def add_memFile(self, parent, node):
        self.add_uvm_mem_content(content = "class " + self.get_class_name(parent, node) + " extends uvm_reg;")
        self.add_uvm_mem_content('''
   function new(string name = \"%s\");
      super.new(name,'h%x, %0d,"RW",UVM_NO_COVERAGE);
   endfunction
   
   `uvm_object_utils(%s)
   
endclass''' % (self.get_class_name(parent, node), node.get_property("mementries"), node.get_property("memwidth"),  self.get_class_name(parent, node)))
    #---------------------------------------------------------------------------
    def get_class_name(self, parent, node):
        regBlockName = parent.inst_name
        regName = node.inst_name
        prefixString = "reg_"
        if isinstance(parent, RegNode):
            prefixString = "reg_"
        elif isinstance(parent, (AddrmapNode, RegfileNode)):
            prefixString = "block_"
        elif isinstance(parent, MemNode):
            prefixString = "mem_"

        if node.is_array:
            regClassName = prefixString + regBlockName.lower() + "_" + regName.lower() + "_" + "%d" % node.current_idx 
        else:
            regClassName = prefixString + regBlockName.lower() + "_" + regName.lower()
        return regClassName
    #---------------------------------------------------------------------------
    def add_register(self, parent, node):
        regBlockName = parent.inst_name
        regName = node.inst_name
        if node.is_array:
            regClassName = "reg_" + regBlockName.lower() + "_" + regName.lower() + "_" + "%d" % node.current_idx 
        else:
            regClassName = "reg_" + regBlockName.lower() + "_" + regName.lower()
        self.add_uvm_reg_content(content = "class " + regClassName + " extends uvm_reg;")

        for field in node.fields():
            self.add_uvm_reg_content(self.indent, "rand uvm_reg_field " + field.inst_name + ";");

        self.add_uvm_reg_content(self.indent, "")
        self.add_uvm_reg_content(self.indent, "virtual function void build();")
        for field in node.fields():
            isRand = "1" if field.is_sw_writable else "0"
            isVolatile = "1" if field.is_volatile else "0"
            self.setSwRdWrProperty(field)
            self.add_uvm_reg_content(self.indent*2, field.inst_name + "= uvm_reg_field::type_id::create(\"" + field.inst_name + "\", null, get_full_name());")
            self.add_uvm_reg_content(self.indent*2, field.inst_name + ".configure(this," + (" %0d, " % field.width) + ("%0d, " % field.low) + "\"%s\"" % self.getFieldAccessType(field) + ", " + isVolatile + ", " + self.resetStr(field) + ", " +  isRand + ", " + self.isOnlyField(node) + ");")
        self.add_uvm_reg_content(self.indent, "endfunction")

        self.add_uvm_reg_content('''
   function new(string name = "%s");
      super.new(name, %0d, UVM_NO_COVERAGE);
   endfunction

   `uvm_object_utils("%s")
endclass''' %(regClassName, node.size*8 ,regClassName))
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
        return "1" if (i == 1) else "0"

    #set other sw read/write properties (these override sw= setting)    
    def setSwRdWrProperty(self, node):
        sw = node.get_property("sw")
        if sw == "rclr":
            self.isSwReadable = True
            self.isRclr = True
        elif sw == "rset":
            self.isSwReadable = True
            self.isRset = True
        elif sw == "woclr":
            self.isSwWriteable = True
            self.isWoclr = True
        elif sw == "woset":
            self.isSwWriteable = True
            self.isWoset = True

    def getFieldAccessType(self, node):
        accessMode = "RO"
        if self.isRclr:
            if self.isWoset:
                accessMode = "W1SRC"
            elif node.is_sw_writable:
                accessMode = "WRC"
            else:
                accessMode = "RC"
        elif self.isRset:
            if self.isWoclr:
                accessMode = "W1CRS"
            elif node.is_sw_writable:
                accessMode = "WRS"
            else:
                accessMode = "RS"
        else:
            if self.isWoclr:
                accessMode = "W1C"
            elif self.isWoset:
                accessMode = "W1S"
            elif node.is_sw_writable:
                if node.is_sw_readable:
                    accessMode = "RW"
                else:
                    accessMode = "WO"
        return accessMode

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
