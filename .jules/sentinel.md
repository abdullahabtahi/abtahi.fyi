## 2025-03-08 - [Missing Authentication on Admin Endpoints]
**Vulnerability:** The admin endpoints in `app/routers/admin.py` (`/capture`, `/api/poll-feeds`, `/api/consolidate`) lacked proper authentication checks. They either had no dependencies at all or relied on a weak, custom `verify_csrf` function that only verified cookie-header parity, without actually validating user identity.
**Learning:** In a fast API app, relying on a custom CSRF check instead of the standard `require_identity` dependency can result in completely unauthenticated access to administrative actions. The `verify_csrf` did not check if the user was logged in.
**Prevention:** Always reuse standard security dependencies (like `require_identity` and `require_csrf`) across all sensitive routes. Avoid custom security check implementations on a per-router basis unless absolutely necessary and thoroughly reviewed.

## 2025-03-08 - [SSRF Bypass via 0.0.0.0 and Missing IPv6 Checks]
**Vulnerability:** The SSRF guardrail `validate_outbound_url` relied on basic string matching on resolved IPs (e.g., `ip.startswith("127.")`). It failed to block `0.0.0.0`, which Linux often routes to localhost. Additionally, an unused and syntactically broken version of this function existed in `app/ingest/poller.py`.
**Learning:** Using simple string operations on resolved IPs allows multiple bypass vectors, including octal representation and unspecified IPs like `0.0.0.0`. Dead security code can create a false sense of security.
**Prevention:** Always use a robust networking library like `ipaddress` to parse and check IP classes (`is_loopback`, `is_private`, `is_link_local`, `is_unspecified`) instead of manual string matching. Remove dead security code.
