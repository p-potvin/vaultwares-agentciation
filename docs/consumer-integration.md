# Consumer Integration Guide

This repository (`vaultwares-agentciation`) is the canonical source of truth for reusable agents, skills, and cross-project agent/IDE guidance.

## Add As a Submodule

Preferred submodule path (hyphenated):

```bash
git submodule add https://github.com/p-potvin/vaultwares-agentciation vaultwares-agentciation
git submodule update --init
```

## Sync Agent/IDE Instruction Surfaces

Some tools require repo-local wrapper files such as:

- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `.cursor/rules/vault-designer.mdc`
- `.windsurfrules`

These files should contain a managed block copied from the canonical source.

To check for drift:

```bash
python vaultwares-agentciation/tools/sync_agentciation_rules.py --agentciation-root vaultwares-agentciation --check
```

To apply updates:

```bash
python vaultwares-agentciation/tools/sync_agentciation_rules.py --agentciation-root vaultwares-agentciation --write
```

## Sync `.github/agents` Snapshots (Optional)

If a repo uses `.github/agents` as a skills snapshot, keep it generated from the canonical mirror:

```bash
python vaultwares-agentciation/tools/sync_agentciation_rules.py --agentciation-root vaultwares-agentciation --write --sync-github-agents-snapshot
```

Canonical mirrors live under:

- `skills/mirrors/<repo-name>/.github/agents`

