# Wave 2 Medium Priority Verification

## Item: DeepSeek rate in cost_tracker.py
- Status: NOT_IMPLEMENTED
- Evidence: Line 24 shows `"deepseek/deepseek-chat": {"input": 0.27, "output": 1.10}` but batch files specify output should be `0.42` not `1.10`
- Location: `services/cost_tracker.py:24`

## Item: Missing model pricing in cost_tracker.py
- Status: NOT_IMPLEMENTED
- Evidence: Batch files (plan5/Item 3, plan7-Item2) list models that should have pricing but are missing from `_DEFAULT_RATES`:
  - `ollama-local/qwen3:8b` (plan5/Item 3)
  - `anthropic/claude-sonnet-4-5-20250929` (plan5/Item 3)
  - `opencode/opencode` (plan5/Item 3)
  - `gemini/gemini-2.5-flash` (plan7-Item2)
- Location: `services/cost_tracker.py:17-34`

## Item: share-a11y.js file exists
- Status: IMPLEMENTED
- Evidence: File exists at `static/js/share-a11y.js` (17 lines). Contains toggle event handler for share-details with focus management. Referenced in batch2 plan as needing to be merged into app.js then deleted.
- Location: `static/js/share-a11y.js`

## Item: app.js share dropdown event handlers and aria-expanded
- Status: NOT_IMPLEMENTED
- Evidence:
  - Lines 56-76: Toggle handler sets `aria-expanded` to boolean (`e.target.open`) instead of string
  - share-a11y.js line 9 correctly uses `e.target.open.toString()` for ARIA compliance
  - app.js line 61 does NOT call `.toString()` - this is the bug
- Location: `static/js/app.js:56-76`

## Item: app.js console.log statements
- Status: NOT_IMPLEMENTED
- Evidence: Lines 327-331 contain `console.log` for service worker registration debug output. Batch files (plan6-Item3) specify these should be removed.
- Location: `static/js/app.js:327-331`

## Item: share_macro.html |safe_href filter usage
- Status: NOT_IMPLEMENTED
- Evidence: Line 21 uses `href="{{ share_href }}"` directly without `|safe_href` filter. The batch files (plan3/H3) mark this as pending and requiring the filter. The `safe_href` filter exists (`app.py:237-252`) and is used in other templates (article_card.html, condensed_article.html, article_edit.html) but NOT in share_macro.html.
- Location: `templates/partials/share_macro.html:21`

## Item: trigger_event function in webhooks.py
- Status: IMPLEMENTED
- Evidence: `trigger_event` function exists at line 289 of services/webhooks.py. Function signature: `def trigger_event(event_type: str, event_data: dict[str, Any], idempotency_key: str | None = None) -> None`. However, batch files note that `article.failed` and `newsletter.failed` events are defined in `KNOWN_WEBHOOK_EVENTS` but never actually called via `trigger_event()`.
- Location: `services/webhooks.py:289`
