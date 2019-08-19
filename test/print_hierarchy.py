#!/usr/bin/env python3

import sys
import os

# Ignore this. Only needed for this example
this_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(this_dir, "../"))


from systemrdl import RDLCompiler, RDLListener, RDLWalker, RDLCompileError
from systemrdl.node import FieldNode, RegNode, AddrmapNode, SignalNode

from ralbot.html import HTMLExporter
import markdown
from ralbot.headergen import headerGenExporter

# Collect input files from the command line arguments
input_files = sys.argv[1:]

# Create an instance of the compiler
rdlc = RDLCompiler()


try:
    # Compile all the files provided
    for input_file in input_files:
        rdlc.compile_file(input_file)
    
    # Elaborate the design
    root = rdlc.elaborate()
except RDLCompileError:
    # A compilation error occurred. Exit with error code
    sys.exit(1)


# Define a listener that will print out the register model hierarchy
class MyModelPrintingListener(RDLListener):
    def __init__(self):
        self.indent = 0
        
    def enter_Component(self, node):
        pass
        #if not isinstance(node, FieldNode):
        #    print("\t"*self.indent, node.get_path_segment())
        #    self.indent += 1
        #if isinstance(node, AddrmapNode):
        #    print("debug point1")
        #    print("\t"*self.indent, node.get_path_segment())

        #    for child in node.children():
        #        if not isinstance(child, SignalNode):
        #            print("\t"*self.indent, child.get_path_segment())
        #            self.indent += 1
        #if isinstance(node, RegNode):
        #    print("\t"*self.indent, "%0x" % node.absolute_address)
    
    #def enter_Field(self, node):
    #    # Print some stuff about the field
    #    bit_range_str = "[%d:%d]" % (node.high, node.low)
    #    sw_access_str = "sw=%s" % node.get_property("sw").name
    #    print("\t"*self.indent, bit_range_str, node.get_path_segment(), sw_access_str)
    
    def exit_Component(self, node):
        if not isinstance(node, FieldNode):
            self.indent -= 1


# Traverse the register model!
walker = RDLWalker(unroll=True)
listener = MyModelPrintingListener()
walker.walk(root, listener)

file = ""
headerfile = headerGenExporter()
headerfile.export(root, file)

#md = markdown.Markdown(
#    extensions=['admonition']
#)
#
#html = HTMLExporter(markdown_inst=md)
#html.export(
#    root,
#    os.path.join(this_dir, "./docs"),
#    home_url="https://github.com/SystemRDL/RALBot-html"
#)