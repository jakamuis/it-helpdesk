# AIJaka local development

This checkout was restored from `/home/codex/IT-Helpdesk.bundle`, containing
`feature/layanan-ti-cloud` at `1fbc40d3a8d556aaa2184d6db8125dc76014b172`.
The working branch is `agent/local-dev-setup`; this is not a checkout of main.
`offline-bundle` preserves the bundle source. `origin` fetches the verified public
GitHub repository over HTTPS and uses `github-aijaka` SSH for explicitly authorized
pushes. No fetch has established an `origin/main` ref yet.

Read `.agents/AGENTS.md` before project work: asset data comes only from the
Datasheet; Zabbix tickets must remain limited to High/Disaster with deduplication.
No production connection, synchronization, ticket generation, or deployment is
part of local setup. Even dry-run synchronization may read live services.

## Isolated Python environments

Use one `.venv` per component; do not combine requirements. The pinned versions
conflict across components. The root CLI and WhatsApp component have Python 3.9
venvs prepared. wa-glpi dependencies are installed and verified; root CLI dependencies remain pending.

Runtime parity from the checked-in Dockerfiles:

| Component | Interpreter | Requirements |
| --- | --- | --- |
| Root synchronization CLI | Python 3.9 available; README requires 3.8+ | requirements.txt |
| wa-glpi | Python 3.9 | wa-glpi/requirements-dev.txt |
| ai-triage | Python 3.11 | ai-triage/requirements-dev.txt |
| asset-sync | Python 3.12 | asset-sync/requirements-dev.txt |

Python 3.11/3.12 are absent. Install parallel interpreters only through an approved
administrator action; never replace system Python. wa-glpi is usable with the installed Python 3.9.25, requests==2.32.4 and pytest==7.4.2. Root CLI installation still returns no candidates from the configured package source. No pins or package-index settings were changed.

Check without installing:

```bash
~/scripts/helpdesk-local-setup check wa-glpi
```

After interpreters and package access are available, review requirements and run:

```bash
~/scripts/helpdesk-local-setup install
```

The helper does not start applications, create credentials, push, deploy, or use
Docker. Check mode verifies both runtime/dev requirements and version constraints, plus `pip check`. Omit the component argument to check all components.
venvs are ignored by Git. Do not copy production `.env`, credentials, spreadsheets,
SQLite databases, or session data into this checkout.

## Verified wa-glpi unit tests

Run component tests separately after reviewing their fixtures. Do not run broad
repository-wide discovery: legacy `asset-sync/scripts/test_*.py` files can contact
external systems. Only use the component's `tests/` directory.

```bash
cd ~/projects/IT-Helpdesk/wa-glpi
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q tests
```

This command passed 48 tests (0 failed) in 0.56s; the repeatable helper `~/scripts/helpdesk-wa-test` also passed all 48 in 1.05s. `pip check` passed. For ai-triage and asset-sync, first obtain their missing runtimes/dependencies and review fixtures, then run their tests separately. Those suites have not been verified here. Avoid running `main.py`, `wa-glpi/app.py`, or sync/import scripts.
No application environment with live endpoints or tokens was created.

Docker and runtime integration remain on the separately confirmed development
server. Its host/user/path and trusted host key are not yet supplied. tmux 3.2a
is installed, but the current agent session cannot open tmux sockets, so SSH
logout/reconnect persistence is not verified.
