import os
import sys
import argparse
import collections
from systemrdl.messages import MessagePrinter
from systemrdl.messages import RDLCompileError
from systemrdl.messages import Severity
import systemrdl.warnings as warnings

from rdlcompiler import RdlCompiler
from ralbot.uvmgen import uvmGenExporter
from ralbot.headergen import headerGenExporter
from ralbot.html import HTMLExporter
from ralbot.ipxact import IPXACTExporter

import markdown

class RDLArgumentError(RDLCompileError):
    """ Command line argument error """
    pass
    NONE = 0
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    FATAL = 5

class RDLMessagePrinter(MessagePrinter):

    def __init__(self):
        self.severity_desc = { "error" : Severity.ERROR, "warning" : Severity.WARNING, "info" : Severity.INFO, "debug" : Severity.DEBUG}

    def enable(self, severity):
        self.severity_desc[severity] = True

    def disable(self, severity):
        self.severity_desc[severity] = False

    def print_message(self, severity, text, src_ref=None):

        if severity in self.severity_desc :
            if (severity == "warning" or severity == "error"):
                # use built in support for these severities
                lines = self.format_message(self.severity_desc[severity], text, src_ref)
                self.emit_message(lines)
            else:
                # just emit simple message
                self.emit_message([str.format("{0}: {1}", severity, text)])


class ralbotGenerator:

    def __init__(self, printer):
        self.printer = printer

    def createArgumentParser(self):
        ap = argparse.ArgumentParser()
        ap.add_argument(
            '-i', '--include-dir',
            metavar='<dir>',
            type=str,
            action='append',
            dest='incl_search_paths',
            help="Include search path."
        )
        ap.add_argument(
            '-t', '--top',
            metavar='<addrmap>',
            type=str,
            dest='top_def_name',
            help="Explicitly choose which addrmap in the root namespace will be the top-level component. "
            "If unset, the last addrmap defined will be chosen"
        )
        ap.add_argument(
            '-o', '--output',
            metavar='<file>',
            type=str,
            required=True,
            dest='output',
            help="Compile output artifact."
        )
        ap.add_argument(
            'src_files',
            metavar='src',
            nargs='+',
            type=str,
            help="List of input files"
        )
        ap.add_argument('-header', 
            dest='gen_header', 
            const='all', 
            nargs='?',
            choices=['all', 'verilog', 'c'], 
            help='generate systemverilog or C header file(default all of them).'
        )
        ap.add_argument(
            '-uvmregs', 
            action='store_true',
            dest='gen_uvm',
            help="generate UVM reg model."
        )
        ap.add_argument(
            '-doc', 
            action='store_true',
            dest='gen_docs',
            help="generate register html documents."
        )
        ap.add_argument(
            '-verilog', 
            action='store_true',
            dest='gen_verilog',
            help="generate register verilog module."
        )
        ap.add_argument(
            '-xml', 
            action='store_true',
            dest='gen_xml',
            help="generate IP-XACT xml file."
        )
        ap.add_argument(
            '-s', '--skip-not-present',
            action='store_true',
            dest='skip_not_present',
            help="If set, compiler skips nodes whose ‘ispresent’ property is set to False."
        )
        ap.add_argument(
            '-w',
            metavar='<warning/no-warning>',
            type=str,
            action='append',
            dest='warning_spec',
            help="Enable warnings (-w warning-name) or disable (-w no-warning-name)"
        )
        ap.add_argument(
            '-v', '--verbose',
            action='store_true',
            dest='verbose_mode',
            help="Enable verbose compilation status print out."
        )
        ap.add_argument(
            '--debug',
            action='store_true',
            dest='debug_mode',
            help="Enable compiler debug mode (with yet more compiler status print out)."
        )
        return ap

    def getWarningMask(self, warning_flags):
        w_bits = {
            'all': warnings.ALL,
            'missing-reset': warnings.MISSING_RESET,
            'implicit': warnings.IMPLICIT_ADDR | warnings.IMPLICIT_FIELD_POS,
            'implicit-addr': warnings.IMPLICIT_FIELD_POS,
            'implicit-field-pos': warnings.IMPLICIT_ADDR
        }
        mask = 0
        for wf, suppressed in warning_flags.items():
            bits = w_bits[wf]
            if suppressed:
                self.printer.print_message(
                    "warning", str.format("suppress warning '{}'", wf))
                mask &= ~bits
            else:
                self.printer.print_message(
                    "warning", str.format("enable warning '{}'", wf))
                mask |= bits
        return mask

    def warnAboutDuplicateFlag(self, flagName, curSuppressed, prevSuppressed):
        state = {False: '', True: 'no-'}
        self.printer.print_message("warning", str.format(
            "duplicated warning flag '-W{1}{0}'", flagName, state[curSuppressed]), None)
        if curSuppressed != prevSuppressed:
            self.printer.print_message("warning", str.format(
                "current flag '-W{1}{0}' will supersede previous flag '-W{2}{0}", flagName, state[curSuppressed], state[prevSuppressed]), None)

    def getWarningFlags(self, warning_spec):

        supported = ['all', 'missing-reset', 'implicit',
                     'implicit-addr', 'implicit-field-pos']
        suppressed = collections.OrderedDict()

        # Note: OrderedDict is useful to preserve sane behavior in something
        # like: "-Wall -Wno-missing-reset"

        if warning_spec:
            for flag in warning_spec:  # type: str
                isNo = flag.startswith('no-')
                flagName = flag[3:] if isNo else flag

                if flagName not in supported:
                    raise RDLArgumentError(str.format(
                        "Unsupported warning flag '-W{0}'", flag))

                if flagName in suppressed:
                    self.warnAboutDuplicateFlag(
                        flagName, suppressed[flagName], isNo)
                suppressed[flagName] = isNo
        return suppressed

    def export(self):

        try:
            parser = self.createArgumentParser()
            cfg = parser.parse_args()
            cfg.warning_flags = self.getWarningFlags(cfg.warning_spec)

            if cfg.debug_mode:
                self.printer.enable('info')
                self.printer.enable('debug')
            elif cfg.verbose_mode:
                self.printer.enable('info')

            rdl_compiler = RdlCompiler(
                printer=self.printer,
                incl_search_paths=cfg.incl_search_paths,
                top_def_name=cfg.top_def_name,
                skip_not_present=cfg.skip_not_present,
                warning_flags=cfg.warning_flags,
                src_files=cfg.src_files
            )

            self.printer.print_message("info", "Start code generation...")
            rdl_root = rdl_compiler.compile()

            if not (cfg.gen_header or cfg.gen_uvm or cfg.gen_docs or cfg.gen_verilog or cfg.gen_xml):
                self.printer.print_message("error", "At least one type(-header, -uvmregs, -doc, -verilog, -xml) generate")
                sys.exit(1)
            elif cfg.gen_verilog:
                self.printer.print_message("warning", "Not yet implemented, Coming soon!!!", None)
                sys.exit(1)

            if cfg.gen_header == "all":
                self.printer.print_message("info", "Generating header...")
                headerGen = headerGenExporter(languages="cpp")
                headerGen.export(rdl_root, cfg.output)
                headerGen = headerGenExporter(languages="verilog")
                headerGen.export(rdl_root, cfg.output)
                self.printer.print_message("info", "Generating header done...")
            elif cfg.gen_header == "verilog":
                headerGen = headerGenExporter(languages="verilog")
                headerGen.export(rdl_root, cfg.output)
            elif cfg.gen_header == "c":
                headerGen = headerGenExporter(languages="cpp")
                headerGen.export(rdl_root, cfg.output)

            if cfg.gen_uvm:
                self.printer.print_message("info", "Generating uvm regmodel...")
                uvmGen= uvmGenExporter()
                uvmGen.export(rdl_root, cfg.output)
                self.printer.print_message("info", "Generating uvm regmodel done...")

            if cfg.gen_docs:
                self.printer.print_message("info", "Generating reg html documents...")
                md = markdown.Markdown(
                    extensions=['admonition']
                )
                
                html = HTMLExporter(markdown_inst=md)
                html.export(
                    rdl_root,
                    os.path.join(cfg.output, "./docs"),
                    home_url="https://github.com/SystemRDL/RALBot-html"
                )
                self.printer.print_message("info", "Generating reg html documents done...")

            if cfg.gen_verilog:
                self.printer.print_message("info", "Generating reg verilog module...")
                sys.exit(1)

            if cfg.gen_xml:
                exporter = IPXACTExporter()
                exporter.export(rdl_root, cfg.output + ".xml")                

        except RDLCompileError as e:
            message = str(e)
            if hasattr(e, '__cause__') and e.__cause__:
                message = "%s Details: %s" % (message, e.__cause__)
            self.printer.print_message("error", message, None)

if __name__ == "__main__":
    ralbotGenerator(RDLMessagePrinter()).export()
