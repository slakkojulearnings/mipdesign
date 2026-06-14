# MIP_PROMPT_LIBRARY.md

# Prompt Library Structure

```text
prompts/

├── architecture/
│   ├── platform_architecture.md
│   ├── service_design.md
│   ├── domain_model_review.md
│   └── architecture_review.md
│
├── discovery/
│   ├── repository_scan.md
│   ├── artifact_classification.md
│   └── inventory_generation.md
│
├── parsing/
│   ├── cobol_parser.md
│   ├── jcl_parser.md
│   ├── copybook_parser.md
│   ├── db2_parser.md
│   └── cics_parser.md
│
├── metadata/
│   ├── entity_model_design.md
│   ├── metadata_review.md
│   └── schema_evolution.md
│
├── graph/
│   ├── build_call_graph.md
│   ├── build_copybook_graph.md
│   ├── build_data_lineage_graph.md
│   └── graph_query_design.md
│
├── testing/
│   ├── parser_tests.md
│   ├── integration_tests.md
│   ├── graph_tests.md
│   └── performance_tests.md
│
├── review/
│   ├── architecture_review.md
│   ├── code_review.md
│   ├── security_review.md
│   └── scalability_review.md
│
└── modernization/
    ├── service_discovery.md
    ├── api_discovery.md
    ├── event_discovery.md
    └── modernization_recommendations.md
```

Example Prompt: discovery/repository_scan.md

```text
Act as a Principal Software Architect.

Design a repository discovery framework.

Requirements:
- Python 3.13
- Recursive scanning
- SQLite persistence
- Extensible classification
- Unit testing

Do not generate code.

Provide:
1. Architecture
2. Components
3. Risks
4. Scalability Considerations
5. Testing Strategy
```

Example Prompt: parsing/cobol_parser.md

```text
Act as a Senior COBOL Analyst.

Design a metadata extraction framework.

Extract:
- PROGRAM-ID
- CALL statements
- COPY statements

Ignore:
- Business Rules
- SQL
- CICS

Do not generate code.

Provide:
1. Architecture
2. Parsing Strategy
3. Edge Cases
4. Testing Approach
```

Example Prompt: graph/build_call_graph.md

```text
Act as a Knowledge Graph Architect.

Design a CALL relationship graph.

Input:
Program Metadata
CALL Relationships

Output:
NetworkX Graph

Provide:
1. Node Design
2. Edge Design
3. Traversal Queries
4. Scalability Considerations
```
