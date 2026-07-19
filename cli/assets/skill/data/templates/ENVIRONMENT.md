<!-- auto-coding-skill:managed-environment -->
# Shared Development Environment

This managed document is refreshed by `autocoding init` and `autocoding sync`.
It contains only common endpoints, ports, and credential lookup guidance.

## Shared services

| Service | URL / host | Port | Credential lookup | Notes |
| --- | --- | --- | --- | --- |
| GitLab web | `http://192.168.20.7:8929` | 8929 | Local shared credential source | Source and merge-request UI |
| GitLab SSH | `192.168.20.7` | 2224 | SSH key / agent | Git remote transport |
| Nexus | `http://192.168.20.7:8081` | 8081 | Local shared credential source | Package and image repository |
| Jenkins | `http://192.168.20.7:8080` | 8080 | Local shared credential source | Build and delivery UI |
| Shared backend access | See `docs/PROJECT.md` | project-specific | Local project credential source | Endpoint belongs to the project |

## Credential lookup

Actual usernames and passwords are project-specific information. Read them from
the credential records in `docs/PROJECT.md`; this managed environment document
intentionally contains no blank or project-specific credential fields.
