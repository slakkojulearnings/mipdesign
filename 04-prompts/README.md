# MIP Enterprise Prompt Library (V2 — live)

These are the live, editable Markdown versions of the V2 Prompt Library
(source PDFs in `../'batch3/prompt_library/`). Each prompt follows the Prompt
Library Strategy — **Role/Skill · Purpose · Context · Inputs · Instructions ·
Expected Output · Constraints · Success Criteria · Review Checklist** — and every
prompt honors the shared
[MIP Engineering Principles](../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md)
and names the [skill](../batch2/skills_framework/) that owns it.

The pipeline runs in order — each stage feeds the next:

```
Discovery → Parsing → Metadata → Knowledge Graph → (Modernization Intelligence)
```

## Discovery — `discovery/` (what exists)
| Prompt | File | Owning skill |
|---|---|---|
| 01 Enterprise Repository Discovery | [repository_scan.md](discovery/repository_scan.md) | mainframe-code-analyst |
| 02 COBOL Program Discovery | [program_inventory.md](discovery/program_inventory.md) | mainframe-code-analyst |
| 03 Batch / Operational Flow Discovery | [jcl_inventory.md](discovery/jcl_inventory.md) | mainframe-code-analyst · resilience-engineer |
| 04 Enterprise Data Structure Discovery | [copybook_inventory.md](discovery/copybook_inventory.md) | mainframe-code-analyst · security-compliance-analyst |
| 05 Database Dependency Discovery | [db2_dependency_discovery.md](discovery/db2_dependency_discovery.md) | mainframe-code-analyst · security-compliance-analyst |
| 05A Root Program Discovery | [root_program_discovery.md](discovery/root_program_discovery.md) | mainframe-code-analyst · graph-engineer |
| 05B Business Capability Discovery | [business_capability_discovery.md](discovery/business_capability_discovery.md) | business-capability-analyst |
| 05C Resilience & Operational Risk Discovery | [resilience_discovery.md](discovery/resilience_discovery.md) | resilience-engineer |

## Parsing — `parsing/` (source → structured metadata)
| Prompt | File | Owning skill |
|---|---|---|
| 06 COBOL Parser Architecture | [cobol_parser.md](parsing/cobol_parser.md) | mainframe-code-analyst |
| 07 JCL Parser Architecture | [jcl_parser.md](parsing/jcl_parser.md) | mainframe-code-analyst |
| 08 Copybook Parser Architecture | [copybook_parser.md](parsing/copybook_parser.md) | mainframe-code-analyst |
| 09 DB2 SQL Parser Architecture | [db2_sql_parser.md](parsing/db2_sql_parser.md) | mainframe-code-analyst |
| 10 VSAM Parser Architecture | [vsam_parser.md](parsing/vsam_parser.md) | mainframe-code-analyst |

## Metadata — `metadata/` (canonical model)
| Prompt | File | Owning skill |
|---|---|---|
| 11 Program Metadata Model | [program_entity.md](metadata/program_entity.md) | metadata-modeler |
| 12 Job Metadata Model | [job_entity.md](metadata/job_entity.md) | metadata-modeler |
| 13 Dataset Metadata Model | [dataset_entity.md](metadata/dataset_entity.md) | metadata-modeler · security-compliance-analyst |
| 14 DB2 Metadata Model | [db2_entity.md](metadata/db2_entity.md) | metadata-modeler |
| 15 Relationship Metadata Model | [relationship_model.md](metadata/relationship_model.md) | metadata-modeler |

## Knowledge Graph — `graph/` (understanding & reasoning)
| Prompt | File | Owning skill |
|---|---|---|
| 16 Call Graph Construction | [build_call_graph.md](graph/build_call_graph.md) | graph-engineer |
| 17 Batch Execution Graph | [build_batch_graph.md](graph/build_batch_graph.md) | graph-engineer · resilience-engineer |
| 18 Data Lineage Graph | [build_data_lineage_graph.md](graph/build_data_lineage_graph.md) | graph-engineer · security-compliance-analyst |
| 19 Impact Analysis Graph | [impact_analysis.md](graph/impact_analysis.md) | graph-engineer |
| 20 Root Program Detection | [root_program_detection.md](graph/root_program_detection.md) | graph-engineer |
| 21 Business Capability Detection | [business_capability_detection.md](graph/business_capability_detection.md) | business-capability-analyst |
| 22 Application Boundary Detection | [application_boundary_detection.md](graph/application_boundary_detection.md) | business-capability-analyst |
| 23 Critical Asset Discovery | [critical_asset_discovery.md](graph/critical_asset_discovery.md) | graph-engineer · resilience-engineer |
| 24 Dead Code & Orphan Detection | [dead_code_detection.md](graph/dead_code_detection.md) | graph-engineer |

---

### How prompts and skills relate
- **Skills** are the personas/capabilities (the *who* and the *how it behaves*) — see `../batch2/skills_framework/`.
- **Prompts** are the tasks (the *what to do*) — they invoke a skill and produce a defined output.
- Both share the same foundation: evidence + confidence, graceful degradation
  (resilience), explainability, and graph-ready output. A prompt should never ask
  for behavior its owning skill is not chartered to perform — if it does, the skill
  needs updating first.

> The one-line stubs under `MIP/MIP_Complete_Hackathon_Pack/prompts/` are the older,
> un-filled versions of these prompts. This `prompts/` tree is the live V2 library.
