# Utils Review Plan

Review the `utils/` package and [utils.md](../architecture/utils.md).

## Review Objectives

1. **Verify Claims Against Code**: Cross-reference architecture document claims with actual utility implementation
2. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
3. **Find Bugs**: Document bugs, edge cases, or layer violations
4. **Check Purity**: Verify functions are pure (no side effects, no global state)

## Key Files

- `utils/url.py` - validate_url_safe, UnsafeURLError, normalize_url, normalize_title, TRACKING_PARAMS, clear_dns_cache
- `utils/text.py` - truncate, sanitize_html, extract_hashtags, esc_xml_text, esc_xml_attr, escape_prompt_data
- `utils/datetime.py` - parse_date, format_date, time_ago
- `utils/security.py` - generate_token, constant_time_compare
- `utils/html.py` - strip_tags, linkify, extract_text
- `utils/hash.py` - generate_hash, verify_hash

## Known Issues to Verify

- `utils/url.py` has global mutable state: _dns_cache, _dns_cache_lock, _dns_executor (not pure despite docstring)
- URL validation duplication between utils/url.py and services/url.py
- services/url.py does NOT re-export from utils/url.py - it redefines everything locally

## Review Checklist

- [ ] Verify URL validation: http/https only, blocks internal IPs, private hostnames
- [ ] Verify DNS resolution for SSRF via DNS rebinding
- [ ] Verify clear_dns_cache() exists and works
- [ ] Verify text utilities: truncate, sanitize_html, extract_hashtags, XML escaping
- [ ] Verify datetime utilities: parse_date handles multiple formats, format_date returns relative time
- [ ] Verify security utilities: generate_token (cryptographically secure), constant_time_compare
- [ ] Verify html utilities: strip_tags, linkify, extract_text (trafilatura fallback)
- [ ] Verify hash utilities: generate_hash, verify_hash with sha256 default

## Output

Save findings to `plans/utils_review.md` with sections:
- Verified Claims
- Discrepancies
- Improvement Recommendations
- Bugs Found