from systemrdl import RDLCompiler, RDLListener, RDLWalker, RDLCompileError
from systemrdl.node import FieldNode
from systemrdl.messages import MessagePrinter, Severity
import systemrdl.warnings as warnings

import sys

class RdlCompiler:

    def __init__(self, printer=MessagePrinter(), **kwargs):
        """ Init compiler. TODO: doc parameters """

        self.printer = printer
        self.incl_search_paths = kwargs.pop('incl_search_paths', None)
        self.top_def_name = kwargs.pop('top_def_name', None)
        self.skip_not_present = kwargs.pop('skip_not_present', False)
        self.warning_flags = kwargs.pop('warning_flags', [])
        self.src_files = kwargs.pop('src_files', [])

    def print_message(self, severity, text, src_ref=None):
        """ Wrapper to printer.print_message allowing default `src_ref` """
        self.printer.print_message(severity, text, src_ref)

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
                self.print_message(
                    Severity.NONE, str.format("suppress warning '{}'", wf))
                mask &= ~bits
            else:
                self.print_message(
                    Severity.NONE, str.format("enable warning '{}'", wf))
                mask |= bits
        return mask

    def compile(self):

        warning_mask = self.getWarningMask(self.warning_flags)
        self.print_message(Severity.NONE, str.format(
            "warning_mask: {0}", warning_mask), None)

        rdlc = RDLCompiler(message_printer=self.printer,
                           warning_flags=warning_mask)

        for input_file in self.src_files:
            self.print_message(
                Severity.NONE, str.format("Compiling {0} ...", input_file))
            rdlc.compile_file(input_file, self.incl_search_paths)

        self.print_message(Severity.NONE, "Elaborating ...")
        root = rdlc.elaborate(top_def_name=self.top_def_name)

        return root
