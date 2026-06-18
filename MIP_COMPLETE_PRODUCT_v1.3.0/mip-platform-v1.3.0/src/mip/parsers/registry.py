from __future__ import annotations

from mip.models import ArtifactType
from mip.parsers.assembler import AssemblerParser
from mip.parsers.base import ArtifactParser
from mip.parsers.bms import BmsParser
from mip.parsers.cobol import CobolParser
from mip.parsers.copybook import CopybookParser
from mip.parsers.ims import ImsParser
from mip.parsers.jcl import JclParser
from mip.parsers.mq import MqParser
from mip.parsers.pl1 import Pl1Parser
from mip.parsers.scheduler import SchedulerParser
from mip.parsers.sql import SqlParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[ArtifactType, ArtifactParser] = {
            ArtifactType.COBOL: CobolParser(),
            ArtifactType.JCL: JclParser(),
            ArtifactType.COPYBOOK: CopybookParser(),
            ArtifactType.SQL: SqlParser(),
            ArtifactType.BMS: BmsParser(),
            ArtifactType.IMS: ImsParser(),
            ArtifactType.MQ: MqParser(),
            ArtifactType.ASSEMBLER: AssemblerParser(),
            ArtifactType.PL1: Pl1Parser(),
            ArtifactType.SCHEDULER: SchedulerParser(),
        }

    def get(self, artifact_type: ArtifactType) -> ArtifactParser | None:
        return self._parsers.get(artifact_type)
