# Quality Reports

Quality reports (`QualityReport` model, `services/quality_report.py`) provide deterministic editorial quality verification for articles.

## Quality Report Model

| Field | Type | Description |
|-------|------|-------------|
| `article_id` | FK | Article being assessed |
| `article_version_id` | FK | Article version at time of assessment |
| `stage` | string | Pipeline stage that triggered assessment (default: "edit") |
| `overall_score` | float | Weighted average (40% quality + 30% citation + 30% claim) |
| `groundedness` | float | Factual alignment with sources (0-1) |
| `coherence` | float | Logical flow and readability (0-1) |
| `completeness` | float | Coverage of key points (0-1) |
| `safety` | float | Absence of harmful content (0-1) |
| `citation_score` | float | Citation verification score (0-1) |
| `claim_score` | float | Unsupported claim score (0-1) |
| `passed` | bool | True if article passes all quality thresholds |
| `needs_review` | bool | True if article should route to manual review |
| `findings` | JSON | List of `QualityFinding` objects |
| `meta` | JSON | Counts of finding types |

## Scoring

### Quality Signals

`lightweight_quality_signals()` provides fast heuristic assessment without LLM calls:
- **groundedness**: Source attribution and citation markers
- **coherence**: Sentence structure and transition words
- **completeness**: Content length (100-600+ words)
- **safety**: Keyword filtering for harmful patterns

### Citation Verification

`_verify_citations()` checks that all citation URLs in the final article appear in:
- `research_brief.external_sources`
- `research_brief.key_claims.source`
- `article.original_url`
- Existing `Citation` rows

Citation score penalty: 0.3 per error, 0.1 per warning.

### Claim Verification

`_check_unsupported_claims()` flags claims with:
- Dates not appearing in source text
- Numeric quantities (percent, million, etc.) without source overlap
- Named entities (multi-word capitalized) without source support

Claim score penalty: 0.1 per warning.

### Overall Score

```python
overall = quality_signals.overall * 0.4 + citation_score * 0.3 + claim_score * 0.3
```

## Pass/Fail Rules

Article **fails** (passed=False) on:
- Any error-level finding
- `citation_score < 0.3`
- `claim_score < 0.3`
- `safety < 0.3`

Article **needs review** (needs_review=True) on:
- `citation_score < 0.6`
- `claim_score < 0.6`
- Any warning finding

## Finding Types

| Code | Severity | Description |
|------|----------|-------------|
| `unsupported_claim` | warning | Numeric/date/entity claim without source overlap |
| `missing_citation` | warning | Citation at index has no URL |
| `unknown_citation_url` | warning | Citation URL not in research sources |
| `quote_mismatch` | warning | Direct quote not found in research brief |
| `stale_date` | warning | Date reference may be outdated |
| `unsafe_content` | error | Harmful content detected |
| `schema_error` | error | final_article JSON invalid |

## Citation Verification Rules

Citations are validated by URL. URL comparison is case-insensitive with trailing slash normalization.

Sources considered valid for citation:
1. Original article URL
2. Any URL in `research_brief.external_sources`
3. Any URL in `research_brief.key_claims[x].source`
4. Any URL in `research_brief.direct_quotes[x].source_url`
5. Any URL in existing `Citation` rows for the article

## Review Workflow

1. Article completes the `edit` stage
2. `build_quality_report()` runs citation, claim, and quote verification
3. Quality report is persisted via `persist_quality_report()`
4. If `passed=False`, article routes to `review` status
5. Admin reviews findings in UI at `/admin/articles/<id>`
6. Admin approves (→ `done`) or rejects (→ `failed`)

API endpoints:
- `GET /api/v1/articles/<id>/quality-reports` — List reports for article
- `GET /api/v1/quality-reports?passed=false` — All failed reports
- `GET /api/v1/quality-reports?needs_review=true` — All articles needing review