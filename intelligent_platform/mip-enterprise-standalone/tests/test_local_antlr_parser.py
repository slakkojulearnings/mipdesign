from __future__ import annotations

import unittest

from mip_intel.reference_parser import antlr4_ready, copybook_resolver, parse_cobol


class LocalAntlrParserTests(unittest.TestCase):
    def test_vendored_antlr_parser_is_active_and_expands_copy_replacing(self) -> None:
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
        self.assertTrue(antlr4_ready())

        payload = parse_cobol(program, resolver=copybook_resolver(copybooks))

        self.assertEqual(payload["parser"]["source"], "mip_intel.cobol_antlr")
        self.assertEqual(payload["parser"]["effective"], "local-antlr4-full-grammar")
        self.assertIn("REALSUB", {call["target"] for call in payload["calls"]})
        self.assertIn("CALLBOOK", {copy["name"] for copy in payload["copies"]})
        self.assertTrue(payload["copy_replacing"])


if __name__ == "__main__":
    unittest.main()
