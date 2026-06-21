from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .api import IntelligenceApi, create_fastapi_app

DEFAULT_DB = "data/mip-intel.db"


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def add_run_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", default=None, help="Analysis run id; defaults to latest run")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mip-intel")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-demo", help="Create a small demo graph")

    analyze = sub.add_parser("analyze", help="Run analysis or demo seeding")
    analyze.add_argument("source_root", nargs="?", default=None)
    analyze.add_argument("--demo", action="store_true", help="Seed the demo estate")
    analyze.add_argument("--config", default="{}", help="JSON config passed to ingestion backend")

    stats = sub.add_parser("stats", help="Show latest run statistics")
    add_run_id(stats)

    run_status = sub.add_parser("run-status", help="Show run lifecycle status")
    add_run_id(run_status)

    validate = sub.add_parser("validate", help="Validate evidence and confidence coverage")
    add_run_id(validate)

    performance = sub.add_parser("performance", help="Show scan telemetry and slow file report")
    add_run_id(performance)
    performance.add_argument("--limit", type=int, default=25)

    corrections = sub.add_parser("corrections", help="List discovery correction feedback")
    add_run_id(corrections)
    corrections.add_argument("--entity-kind", default="")
    corrections.add_argument("--all", action="store_true", help="Include inactive corrections")

    correction_add = sub.add_parser("correction-add", help="Add discovery correction feedback")
    add_run_id(correction_add)
    correction_add.add_argument("--entity-kind", required=True, choices=("MEMBER", "ASSET", "RELATIONSHIP"))
    correction_add.add_argument("--selector", required=True, help="Path, technical name, or source|type|target selector")
    correction_add.add_argument("--action", required=True, help="OVERRIDE_TYPE, OVERRIDE, RENAME, CLASSIFY_AS, or SUPPRESS")
    correction_add.add_argument("--corrected-type", default="")
    correction_add.add_argument("--corrected-name", default="")
    correction_add.add_argument("--corrected-status", default="")
    correction_add.add_argument("--corrected-confidence", type=float, default=None)
    correction_add.add_argument("--reason", default="")

    scorecard = sub.add_parser("scorecard", help="Run a ground-truth scorecard manifest")
    add_run_id(scorecard)
    scorecard.add_argument("manifest", help="Path to scorecard JSON")

    scorecards = sub.add_parser("scorecards", help="List persisted scorecard results")
    add_run_id(scorecards)
    scorecards.add_argument("--limit", type=int, default=50)

    roots = sub.add_parser("roots", help="Show root driver portfolio")
    add_run_id(roots)
    roots.add_argument("--limit", type=int, default=200)

    clusters = sub.add_parser("clusters", help="Show application clusters")
    add_run_id(clusters)
    clusters.add_argument("--limit", type=int, default=200)

    domains = sub.add_parser("domains", help="Show DDD bounded context candidates")
    add_run_id(domains)
    domains.add_argument("--limit", type=int, default=50)

    services = sub.add_parser("service-candidates", help="Show Java service candidates from graph evidence")
    add_run_id(services)
    services.add_argument("--limit", type=int, default=50)

    roadmap = sub.add_parser("roadmap", help="Show modernization roadmap work packages")
    add_run_id(roadmap)
    roadmap.add_argument("--limit", type=int, default=50)

    search = sub.add_parser("search", help="Search assets")
    add_run_id(search)
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--offset", type=int, default=0)

    nodes = sub.add_parser("nodes", help="List selectable graph nodes")
    add_run_id(nodes)
    nodes.add_argument("--scope", choices=("roots", "programs", "normal_programs", "jobs", "tables", "copybooks", "transactions", "all"), default="programs")
    nodes.add_argument("--query", default="")
    nodes.add_argument("--limit", type=int, default=200)
    nodes.add_argument("--offset", type=int, default=0)

    graph = sub.add_parser("graph-slice", help="Return bounded graph slice")
    add_run_id(graph)
    graph.add_argument("--root", required=True, help="Seed node asset id or technical name")
    graph.add_argument("--mode", default="neighborhood")
    graph.add_argument("--direction", choices=("upstream", "downstream", "both"), default="both")
    graph.add_argument("--depth", type=int, default=1)
    graph.add_argument("--limit", type=int, default=500)
    graph.add_argument("--relationship-types", default="")
    graph.add_argument("--confidence-min", type=float, default=0.0)

    node = sub.add_parser("node", help="Show node profile")
    add_run_id(node)
    node.add_argument("asset_id", help="Asset id or technical name")

    coverage = sub.add_parser("coverage", help="Show parser and graph coverage for one node")
    add_run_id(coverage)
    coverage.add_argument("asset", help="Asset id or technical name")

    edge = sub.add_parser("edge", help="Show edge profile")
    add_run_id(edge)
    edge.add_argument("relationship_id")

    heatmap = sub.add_parser("heatmap", help="Show compact matrix cells")
    add_run_id(heatmap)
    heatmap.add_argument("left_type")
    heatmap.add_argument("right_type")
    heatmap.add_argument("relationship_type")

    call_graph = sub.add_parser("call-graph", help="Show upstream/downstream/360 call graph")
    add_run_id(call_graph)
    call_graph.add_argument("asset", help="Asset id or technical name")
    call_graph.add_argument("--direction", choices=("upstream", "downstream", "both"), default="both")
    call_graph.add_argument("--depth", type=int, default=8)
    call_graph.add_argument("--limit", type=int, default=1500)

    dependency = sub.add_parser("dependency-graph", help="Show bounded dependency graph")
    add_run_id(dependency)
    dependency.add_argument("asset", help="Asset id or technical name")
    dependency.add_argument("--direction", choices=("upstream", "downstream", "both"), default="both")
    dependency.add_argument("--depth", type=int, default=4)
    dependency.add_argument("--limit", type=int, default=1500)

    required = sub.add_parser("required-files", help="List files required for reverse engineering")
    add_run_id(required)
    required.add_argument("asset", help="Asset id or technical name")
    required.add_argument("--depth", type=int, default=8)
    required.add_argument("--limit", type=int, default=5000)

    ast = sub.add_parser("ast-tree", help="Show parsed AST tree for a program asset")
    add_run_id(ast)
    ast.add_argument("asset", help="Asset id or technical name")

    bundle = sub.add_parser("export-bundle", help="Write reverse-engineering bundle to a folder")
    add_run_id(bundle)
    bundle.add_argument("asset", help="Asset id or technical name")
    bundle.add_argument("--output", required=True, help="Output folder")
    bundle.add_argument("--depth", type=int, default=8)
    bundle.add_argument("--limit", type=int, default=5000)
    bundle.add_argument("--no-sources", action="store_true", help="Write JSON only; do not copy source files")

    export = sub.add_parser("export", help="Export graph data")
    add_run_id(export)
    export.add_argument("--format", choices=("json", "cytoscape", "csv"), default="json")
    export.add_argument("--limit", type=int, default=5000)
    export.add_argument("--output", default="", help="Optional output file")

    insights = sub.add_parser("insights", help="Generate enterprise graph insights")
    add_run_id(insights)
    insights.add_argument("--limit", type=int, default=50)

    serve = sub.add_parser("serve", help="Serve FastAPI app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def normalize_global_args(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    normalized = list(argv)
    if "--db" not in normalized:
        return normalized
    index = normalized.index("--db")
    if index + 1 >= len(normalized):
        return normalized
    db_path = normalized[index + 1]
    del normalized[index : index + 2]
    return ["--db", db_path, *normalized]


def parse_config_arg(value: str) -> dict[str, Any]:
    text = (value or "").strip()
    if not text:
        return {}
    if text.startswith("@"):
        return json.loads(Path(text[1:]).read_text(encoding="utf-8"))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _parse_relaxed_config(text)
    if not isinstance(parsed, dict):
        raise ValueError("--config must be a JSON object")
    return parsed


def _parse_relaxed_config(text: str) -> dict[str, Any]:
    body = text.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]
    if not body:
        return {}
    result: dict[str, Any] = {}
    for part in re.split(r"\s*,\s*", body):
        if not part:
            continue
        if ":" in part:
            key, raw = part.split(":", 1)
        elif "=" in part:
            key, raw = part.split("=", 1)
        else:
            raise ValueError(f"Invalid --config entry: {part}")
        key = key.strip().strip("'\"")
        result[key] = _parse_config_value(raw.strip().strip("'\""))
    return result


def _parse_config_value(value: str) -> Any:
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"none", "null"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def main(argv: list[str] | None = None) -> int:
    selected_argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(normalize_global_args(selected_argv))
    api = IntelligenceApi(Path(args.db))
    if args.command == "init-demo":
        print_json(api.init_demo())
    elif args.command == "analyze":
        config = parse_config_arg(args.config)
        print_json(api.analyze(args.source_root, demo=args.demo, config=config))
    elif args.command == "stats":
        print_json(api.stats(args.run_id))
    elif args.command == "run-status":
        print_json(api.run_status(args.run_id))
    elif args.command == "validate":
        print_json(api.validate(args.run_id))
    elif args.command == "performance":
        print_json(api.performance(args.run_id, limit=args.limit))
    elif args.command == "corrections":
        print_json(
            api.corrections(
                args.run_id,
                entity_kind=args.entity_kind or None,
                active_only=not args.all,
            )
        )
    elif args.command == "correction-add":
        print_json(
            api.add_correction(
                run_id=args.run_id,
                entity_kind=args.entity_kind,
                selector=args.selector,
                action=args.action,
                corrected_type=args.corrected_type or None,
                corrected_name=args.corrected_name or None,
                corrected_status=args.corrected_status or None,
                corrected_confidence=args.corrected_confidence,
                reason=args.reason,
            )
        )
    elif args.command == "scorecard":
        print_json(api.run_scorecard(args.manifest, args.run_id))
    elif args.command == "scorecards":
        print_json(api.scorecards(args.run_id, limit=args.limit))
    elif args.command == "roots":
        print_json(api.roots(args.run_id, limit=args.limit))
    elif args.command == "clusters":
        print_json(api.clusters(args.run_id, limit=args.limit))
    elif args.command == "domains":
        print_json(api.domain_contexts(args.run_id, limit=args.limit))
    elif args.command == "service-candidates":
        print_json(api.service_candidates(args.run_id, limit=args.limit))
    elif args.command == "roadmap":
        print_json(api.modernization_roadmap(args.run_id, limit=args.limit))
    elif args.command == "search":
        print_json(api.search(args.query, args.run_id, limit=args.limit, offset=args.offset))
    elif args.command == "nodes":
        print_json(api.nodes(args.run_id, scope=args.scope, q=args.query, limit=args.limit, offset=args.offset))
    elif args.command == "graph-slice":
        rels = tuple(item.strip() for item in args.relationship_types.split(",") if item.strip())
        print_json(
            api.graph_slice(
                args.root,
                args.run_id,
                mode=args.mode,
                direction=args.direction,
                depth=args.depth,
                limit=args.limit,
                relationship_types=rels,
                confidence_min=args.confidence_min,
            )
        )
    elif args.command == "node":
        print_json(api.node(args.asset_id, args.run_id))
    elif args.command == "coverage":
        print_json(api.coverage(args.asset, args.run_id))
    elif args.command == "edge":
        print_json(api.edge(args.relationship_id, args.run_id))
    elif args.command == "heatmap":
        print_json(api.heatmap(args.left_type, args.right_type, args.relationship_type, args.run_id))
    elif args.command == "call-graph":
        print_json(
            api.call_graph(
                args.asset,
                args.run_id,
                direction=args.direction,
                depth=args.depth,
                limit=args.limit,
            )
        )
    elif args.command == "dependency-graph":
        print_json(
            api.dependency_graph(
                args.asset,
                args.run_id,
                direction=args.direction,
                depth=args.depth,
                limit=args.limit,
            )
        )
    elif args.command == "required-files":
        print_json(api.required_files(args.asset, args.run_id, depth=args.depth, limit=args.limit))
    elif args.command == "ast-tree":
        print_json(api.ast_tree(args.asset, args.run_id))
    elif args.command == "export-bundle":
        print_json(
            api.export_bundle(
                args.asset,
                args.output,
                args.run_id,
                depth=args.depth,
                limit=args.limit,
                include_sources=not args.no_sources,
            )
        )
    elif args.command == "export":
        payload = api.export(args.run_id, format=args.format, limit=args.limit)
        if args.output:
            path = Path(args.output)
            if isinstance(payload, str):
                path.write_text(payload, encoding="utf-8", newline="")
            else:
                path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
            print_json({"output": str(path), "format": args.format})
        elif isinstance(payload, str):
            print(payload, end="")
        else:
            print_json(payload)
    elif args.command == "insights":
        print_json(api.insights(args.run_id, args.limit))
    elif args.command == "serve":
        import uvicorn

        uvicorn.run(create_fastapi_app(Path(args.db)), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
