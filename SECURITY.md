# Security Policy

## Reporting

Do not file sensitive disclosures in public issues.

Report security issues privately to the repository owner or maintainer instead
of publishing exploit details in a public issue or pull request.

## Scope

This repository must not become a place to store live secrets, credentials,
tokens, private keys, personal data, or other private environment details.

- Treat `CHATHISTORY.md` as local-only operational memory and do not publish it.
- Do not commit machine-specific absolute filesystem paths, hostnames, internal
  endpoint addresses, or local-only config files unless the exact value is
  strictly required and already safe to disclose.
- Treat tracked example files, fixtures, screenshots, copied logs, and issue or
  pull-request snippets as public documentation. Use synthetic placeholders and
  redacted examples instead of real usernames, hostnames, account identifiers,
  secrets, or private operational data.

## Repo-Specific Boundaries

- This library does not handle credentials directly — credential management
  should use `auto-pass` or equivalent.
- Browser automation runs are local-only; no remote services are exposed.
- Chrome for Testing downloads use Google's public CDN only.
- Debug snapshots (HTML, screenshots) may capture sensitive page content —
  ensure snapshot directories are excluded from version control and public
  sharing.
