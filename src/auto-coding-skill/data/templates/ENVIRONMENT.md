<!-- auto-coding-skill:managed-environment -->
# Shared Development Environment

This managed document is refreshed by `autocoding init` and `autocoding sync`.
It contains only common endpoints, ports, and credential variable references.
Actual credentials stay in the local, untracked file
`~/.config/auto-coding-skill/credentials.env`.

## Shared services

| Service | URL / host | Port | Credential variables | Notes |
| --- | --- | --- | --- | --- |
| GitLab web | `http://192.168.20.7:8929` | 8929 | `GITLAB_USERNAME`, `GITLAB_PASSWORD` | Source and merge-request UI |
| GitLab SSH | `192.168.20.7` | 2224 | SSH key / agent | Git remote transport |
| Nexus | `http://192.168.20.7:8081` | 8081 | `NEXUS_USERNAME`, `NEXUS_PASSWORD` | Package and image repository |
| Jenkins | `http://192.168.20.7:8080` | 8080 | `JENKINS_USERNAME`, `JENKINS_PASSWORD` | Build and delivery UI |
| Shared backend access | See `docs/PROJECT.md` | project-specific | `BACKEND_USERNAME`, `BACKEND_PASSWORD` | Common credentials; endpoint belongs to the project |

## Local credential source

Create or update `~/.config/auto-coding-skill/credentials.env` locally. It must
never be copied into a repository, chat transcript, build log, or deployment
artifact.

```dotenv
GITLAB_USERNAME=
GITLAB_PASSWORD=
NEXUS_USERNAME=
NEXUS_PASSWORD=
JENKINS_USERNAME=
JENKINS_PASSWORD=
BACKEND_USERNAME=
BACKEND_PASSWORD=
```
