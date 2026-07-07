# Milestone A.2: API Token Redesign

## Objective

Replace the current API-token implementation with a clear, secure, and testable token lifecycle. The inspected implementation returns a token shaped like `plain_token.token_hash`, but verification effectively ignores `plain_token` and validates only the second component. It also records `expires_at` but does not enforce expiration during verification.

The desired outcome is a conventional bearer-token model with explicit prefix lookup, secret verification, expiration enforcement, revocation/deletion behavior, and database fields sized for real verifier data.

## Current behavior to replace

Current creation flow in `routes/admin/api_tokens.py`:

- Generate `plain_token = secrets.token_urlsafe(32)`.
- Generate `token_hash = secrets.token_hex(32)`.
- Store `generate_password_hash(token_hash)`.
- Store `raw_token_hash=token_hash` only to derive `token_prefix`.
- Return `plain_token + "." + token_hash`.

Current verification flow in `routes/admin/__init__.py`:

- Split token on the first dot.
- Ignore the first component.
- Take the second component as `provided_hash`.
- Lookup by the first 16 characters of the second component.
- Verify the stored hash against the second component.
- Update `last_used_at`.

Problems:

- One returned token component is unused.
- Expiry is not enforced.
- There is no explicit revocation field.
- `ApiToken.token_hash = db.String(64)` is too small for Werkzeug password hashes in stricter databases.
- Token naming is confusing: `token_hash` is sometimes raw secret material and sometimes a password-hash verifier.

## Target design

Use a token format like:

```text
ak_<prefix>.<secret>
```

Example conceptual fields:

- `token_prefix`: short lookup prefix, indexed and non-secret.
- `token_hash`: verifier for the secret, never raw token material.
- `name`: operator-provided display name.
- `created_at`: creation timestamp.
- `last_used_at`: updated after successful verification.
- `expires_at`: optional expiration timestamp.
- `revoked_at`: optional revocation timestamp, if soft revocation is preferred over delete-only.

The exact prefix format can be simpler if desired, but the important invariant is this: lookup uses non-secret prefix, verification uses secret material, and stored verifier cannot authenticate directly if leaked.

## Affected files

Likely files:

- `models/auth.py`
- `routes/admin/api_tokens.py`
- `routes/admin/__init__.py`
- `routes/decorators.py` if auth result handling changes
- `migrations/`
- `tests/`
- `docs/security.md`
- `docs/configuration.md`

## Implementation plan

### Step 1: Define token constants and helper functions

Add a small helper module or local helpers. Prefer a dedicated module if this logic is used in multiple places.

Candidate module:

- `services/api_tokens.py`

Candidate functions:

```python
def generate_api_token() -> tuple[str, str, str]:
    """Return public token, prefix, and raw secret."""


def hash_api_token_secret(secret: str) -> str:
    """Return password/hash verifier for the secret."""


def verify_api_token_secret(stored_hash: str, provided_secret: str) -> bool:
    """Constant-time verification through Werkzeug or HMAC-based verifier."""


def parse_api_token(token: str) -> tuple[str, str] | None:
    """Return prefix and secret or None for malformed tokens."""
```

Keep token parsing strict. Reject empty components, tokens with too many/few separators if using a fixed format, overlong tokens, non-printable data, and unsupported prefixes.

### Step 2: Update database model

Update `models/auth.py`.

Recommended model changes:

- Widen `token_hash` to at least `db.String(255)` or `db.Text`.
- Keep `token_prefix = db.Column(db.String(32), nullable=False, index=True)` or similar.
- Add `revoked_at = db.Column(db.DateTime, nullable=True)` if soft revocation is wanted.
- Keep `expires_at`.

If the project remains SQLite-only for now, still write portable constraints because docs mention possible future DB strategy changes.

### Step 3: Add migration

Create an Alembic migration for the model changes.

Migration considerations:

- Widening a string column in SQLite may require batch operations depending on migration setup.
- Existing tokens should be considered invalid after the redesign unless a compatibility verifier is explicitly needed.
- For a pre-public repo, prefer invalidating old tokens and documenting regeneration.
- If preserving old tokens, add a `token_version` field and support legacy verification temporarily, but this likely adds unnecessary risk.

Recommended path:

- Add/alter columns.
- Set a release note: existing API tokens must be regenerated.
- Do not preserve legacy token verification unless required.

### Step 4: Rewrite token creation

In `routes/admin/api_tokens.py`:

- Validate `name` length and type.
- Validate `expires_in` type, maximum, and minimum.
- Generate `public_token`, `prefix`, and `secret`.
- Store only `prefix` and hashed secret/verifier.
- Return the public token exactly once.
- Avoid returning raw verifier material.

Recommended validation:

- `name`: optional, string, max 128 chars.
- `expires_in`: optional integer seconds, positive, bounded. Suggested maximum: 366 days unless config allows longer.

### Step 5: Rewrite token verification

In `routes/admin/__init__.py` or preferably `services/api_tokens.py`:

Verification should:

1. Parse the bearer token.
2. Return false for malformed tokens.
3. Lookup candidate tokens by prefix.
4. Reject missing candidates.
5. Reject expired tokens.
6. Reject revoked tokens if `revoked_at` exists.
7. Verify provided secret against stored verifier.
8. Update `last_used_at` only after successful verification.
9. Commit safely; failure to update `last_used_at` should not necessarily fail authentication unless DB consistency requires it.

Do not leak whether the prefix exists via different error messages in externally visible responses.

### Step 6: Delete versus revoke semantics

Current delete removes the token row. That is acceptable. Adding `revoked_at` is still useful for auditability, but it is not mandatory if the UI means permanent delete.

Choose one:

- Hard delete: simple, no revoked-token audit trail.
- Soft revoke: preserves metadata and prevents reuse.

Recommendation: use soft revoke for public release if audit logging is already a project goal. If implementation time is tight, keep hard delete but test that deleted tokens fail.

### Step 7: Update auth decorator behavior if needed

`require_auth` currently calls `verify_api_token(token)` and returns `Invalid API token` for bearer-token failure. Preserve that external behavior unless changing API response format deliberately.

If the token route moves under `/api/v1`, ensure auth failure remains JSON.

### Step 8: Add tests

Minimum tests:

- Creating a token returns a token once and stores no raw token material.
- Valid token authenticates.
- Wrong secret fails.
- Malformed tokens fail.
- Expired token fails.
- Deleted/revoked token fails.
- `last_used_at` updates on successful verification.
- `last_used_at` does not update on failed verification.
- Token hash/verifier column can hold generated verifier value.
- Token prefix lookup works with multiple tokens sharing no prefix collision.

Add route tests:

- Bearer token can access a protected API endpoint.
- Invalid bearer token receives 401 JSON.
- Expired bearer token receives 401 JSON.

### Step 9: Update docs

Update security/configuration docs to describe:

- API-token format at a high level, without exposing internals as a guarantee.
- Expiration behavior.
- Token creation endpoint behavior.
- Token storage guarantees: only verifier is stored.
- Regeneration note if existing tokens are invalidated.

## Acceptance criteria

- Verification uses the intended secret component.
- Expiration is enforced.
- Deleted or revoked tokens cannot authenticate.
- Token verifier storage is sized correctly.
- No raw token material is stored after request completion.
- Tests cover positive and negative lifecycle behavior.
- Docs match the new behavior.

## Handoff cautions

- Avoid naming raw secret material `hash`; it caused confusion in the existing implementation.
- Do not use `secrets.token_hex()` output directly as both lookup and verifier.
- Do not expose distinct external errors for expired versus invalid tokens unless the API intentionally wants that; generic `Invalid API token` is safer.
- If using Werkzeug password hashes, use a column that can fit current and future hash formats.
- If adding `revoked_at`, update list endpoint semantics so revoked tokens are either hidden or clearly marked.
