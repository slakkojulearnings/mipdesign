# MIP Memory Model

## catalog.txt

Purpose: canonical artifact registry and name translation.

Format:

```text
TYPE|ID|READABLE_NAME|CATEGORY|SOURCE_PATH|DOC_PATH|CONTENT_HASH|CONFIDENCE|REVIEW_STATUS
```

## relationships.txt

Purpose: canonical portable relationship index.

Format:

```text
RELATION_TYPE|FROM_TYPE|FROM_ID|TO_TYPE|TO_ID|SOURCE_PATH|LINE_RANGE|CONFIDENCE|NOTES
```

## todo.list

Purpose: work claiming, deduplication, and completeness.

Format:

```text
STATUS|ARTIFACT_TYPE|ARTIFACT_ID|SOURCE_PATH|CONTENT_HASH|OWNER|STARTED_AT|COMPLETED_AT|OUTPUT_PATH|ERROR
```

Statuses:

- PENDING
- IN_PROGRESS
- DONE
- BLOCKED
- STALE

## processed.log

Append-only audit trail.

Format:

```text
TIMESTAMP|RUN_ID|AGENT|ACTION|ARTIFACT_ID|RESULT|DETAILS
```

## Idempotency

An item marked `DONE` remains complete while its content hash is unchanged. A changed hash marks it `STALE` and creates a new processing event.

## Concurrency

Workers must claim items through the claim script or a transactional database equivalent. Direct manual edits during parallel execution are discouraged.
