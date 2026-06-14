"""JCL extractor (v0.1, regex) — the source of root-driver discovery.

Extracts the JOB name and each step's EXEC PGM= target:
  //NAME JOB ...            -> Job
  //STEP EXEC PGM=PROG      -> JobStep + EXECUTES edge (Job -> Program)

A step's program may name a program whose source is absent; it is kept as a name and
resolved to a Program by the store/graph when one exists (Principle 2: resilience).
"""

from __future__ import annotations

import re

from .records import Edge, Evidence, Job, JobStep, make_id

_JOB = re.compile(r"(?mi)^//(\w+)\s+JOB\b")
_STEP = re.compile(r"(?mi)^//(\w+)\s+EXEC\s+PGM=([A-Z0-9$#@]+)")


def job_name(text: str) -> str | None:
    m = _JOB.search(text)
    return m.group(1).upper() if m else None


def parse_jcl(text: str, artifact_id: str, rel_path: str) -> tuple[Job | None, list[JobStep], list[Edge]]:
    jname = job_name(text)
    if not jname:
        return None, [], []
    job = Job(job_id=jname, job_name=jname, artifact_id=artifact_id,
              evidence=Evidence.confirmed(f"{rel_path}:1"))
    steps: list[JobStep] = []
    edges: list[Edge] = []
    for order, m in enumerate(_STEP.finditer(text), start=1):
        step_name, prog = m.group(1).upper(), m.group(2).upper()
        line_no = text.count("\n", 0, m.start()) + 1
        ev = Evidence.confirmed(f"{rel_path}:{line_no}")
        steps.append(JobStep(step_id=make_id(jname, step_name), job_id=jname,
                             step_name=step_name, program_name=prog,
                             step_order=order, evidence=ev))
        edges.append(Edge.build("job", jname, "EXECUTES", "program", prog, ev))
    return job, steps, edges
