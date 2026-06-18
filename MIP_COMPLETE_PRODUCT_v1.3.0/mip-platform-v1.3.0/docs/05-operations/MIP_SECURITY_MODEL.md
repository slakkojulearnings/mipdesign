# MIP Security Model

## Data classification

Legacy source, data layouts, rules, and generated graphs may be confidential even when the platform code is public.

## Controls

- `mfcode/`, `data/`, `output/`, and logs are ignored by default.
- Source is opened read-only by the analyzer.
- The API is unauthenticated for local v1 use and must not be exposed to untrusted networks.
- Enterprise deployment must add authentication, authorization, TLS, audit logging, rate limits, and repository-level access controls.
- LLM/ADK use is optional; organizations must approve what context may leave the local environment.
- Secrets are never stored in prompts, skills, source files, or SQLite metadata.
