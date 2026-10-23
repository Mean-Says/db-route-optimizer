# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | yes (once tagged) |
| main    | best-effort |

## Reporting a vulnerability

Please open a **private** security advisory on GitHub, or email the maintainer listed in the
repository profile. Do not open a public issue for credential leaks or RCE-class bugs.

## Safe usage

- Point `DATABASE_URL` at a **local copy** or demo database for `dbro-explain --analyze` and
  `--suggest-index --verify`.
- Non-local hosts default to plan-only (`--plain`); ANALYZE on non-SELECT is refused.
- Passwords in URLs are redacted in tool output; still avoid pasting live credentials into logs.
- Never run this tool's write/DDL paths against production.
