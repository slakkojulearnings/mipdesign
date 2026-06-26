from __future__ import annotations

import unittest

from mip_intel.reference_parser import antlr4_ready, copybook_resolver, parse_cobol, parse_cobol_deep


class LocalAntlrParserTests(unittest.TestCase):
    def test_baseline_parser_expands_copy_replacing_without_antlr(self) -> None:
        program = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDADV.
       PROCEDURE DIVISION.
           COPY CALLBOOK REPLACING ==:SUBPGM:== BY ==REALSUB==.
           STOP RUN.
"""
        copybooks = {
            "CALLBOOK": """
           CALL ':SUBPGM:'.
"""
        }
        payload = parse_cobol(program, resolver=copybook_resolver(copybooks))

        self.assertEqual(payload["parser"]["source"], "mip_intel.cobol_antlr")
        self.assertNotEqual(payload["parser"]["effective"], "local-antlr4-full-grammar")
        self.assertIn("REALSUB", {call["target"] for call in payload["calls"]})
        self.assertIn("CALLBOOK", {copy["name"] for copy in payload["copies"]})
        self.assertTrue(payload["copy_replacing"])

    def test_deep_parser_is_explicit_antlr_path(self) -> None:
        program = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDADV.
       PROCEDURE DIVISION.
           STOP RUN.
"""
        payload = parse_cobol_deep(program)

        self.assertTrue(antlr4_ready())
        self.assertEqual(payload["parser"]["requested"], "local-antlr4")


if __name__ == "__main__":
    unittest.main()
