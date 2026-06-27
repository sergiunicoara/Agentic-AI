---
name: supply-chain-integrity
description: Detect dependency vulnerabilities and supply chain risks in agent projects.
triggers: [requirements_txt, pyproject_toml, package_json, lockfile, pip_install]
pillar: 4
---

## What to look for
- Dependencies with known CVEs in requirements.txt or pyproject.toml
- Unpinned dependencies (no version specifier) that could pull malicious updates
- Dependencies not in a lockfile — supply chain drift risk
- Packages with unusual post-install scripts
- Direct imports of packages not declared in requirements

## Evidence required
A finding is ONLY valid if backed by one of:
- A `pip-audit` result showing a CVE with severity and affected version
- A `bandit` hit related to insecure package usage
- A missing lockfile when dependencies are unpinned

No evidence → finding must be dropped by the Adjudicator.

## Remediation patterns
- Pin all dependencies to exact versions in production
- Add pip-audit to CI/CD pipeline as a blocking gate
- Use a lockfile (pip-compile, poetry.lock, uv.lock)
- Review changelogs before upgrading any dependency
- Prefer packages with active security disclosure programs