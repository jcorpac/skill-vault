# Skill Vault 🛡️

[![CI Test Suite](https://github.com/jcorpac/skill-vault/actions/workflows/test.yml/badge.svg)](https://github.com/jcorpac/skill-vault/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/@jcorpac/skill-vault.svg)](https://www.npmjs.com/package/@jcorpac/skill-vault)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-Standard-green.svg)](SKILL.md)

> **Universal Agent Skill Router, Lifecycle Manager & Tiered Storage Engine for AI Coding Agents.**
> Works across **Google Antigravity, Claude Code, Cursor, Windsurf, OpenCode, and CI/CD**.

---

## ⚡ The Problem: Context Bloat & Skill Bleed

As teams collect specialized skills (database admin, cloud deployment, bioinformatics, testing workflows), loading 50–100+ skills into active AI prompts causes:
1. **Context Window Saturation**: Thousands of prompt tokens consumed before the conversation even starts.
2. **Skill Bleed**: AI models get confused by conflicting tool instructions from unrelated frameworks.
3. **Broken Manifests & Orphan Folders**: Manual directory changes leave dangling references.

## 💡 The Solution: Tiered Skill Memory

**Skill Vault** implements a **two-tier memory model**:
- **L1 Active Memory (`skills/`)**: Lightweight general-purpose skills actively loaded in context.
- **L2 Cold Storage (`skill_archive/`)**: Deep domain skills indexed in metadata, searchable in milliseconds, and dynamically mounted or restored on demand.

```
┌─────────────────────────────────────────────────────────────┐
│                       AI CODING AGENT                       │
│    (Google Antigravity / Claude Code / Cursor / Windsurf)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
    [L1 Active Context Memory]     [L2 Cold Storage Archive]
       ./.agents/skills/              ./skill_archive/skills/
     - general-git-workflow         - alloydb-omni-cluster
     - managing-python-deps         - gcp-composer-troubleshoot
                                    - alphafold-protein-analysis
               │                               ▲
               │  npx @jcorpac/skill-vault     │
               │  archive                      │
               ├──────────────────────────────►│
               │  npx @jcorpac/skill-vault     │
               │  restore                      │
               │◄──────────────────────────────┤
```

---

## 🚀 Quickstart

### Option 1: Run via `npx` (Zero Installation)
```bash
# Initialize a repository for skill storage
npx @jcorpac/skill-vault init

# Search indexed skills
npx @jcorpac/skill-vault search "database"

# Verify archive integrity
npx @jcorpac/skill-vault verify --fix
```

### Option 2: Install as an Agent Skill
Install directly into Claude Code, Antigravity, or Cursor:
```bash
npx skills add jcorpac/skill-vault
```

### Option 3: Use with Python CLI (Pure Standard Library)
```bash
python scripts/skill_vault.py verify
```

---

## 🛠️ CLI Command Reference

| Command | Description |
| :--- | :--- |
| `skill-vault init` | Bootstrap standard skill and archive folders in workspace. |
| `skill-vault list` | Present all active skills (L1) and archived skills (L2). |
| `skill-vault status` | Fast summary of skill counts and category breakdown. |
| `skill-vault list --active` | List only active skills currently loaded in context memory. |
| `skill-vault list --archived` | List only cold-storage skills grouped by category. |
| `skill-vault archive <name> --category "<Cat>"` | Move active skill to archive with category metadata. |
| `skill-vault archive --pattern "gcp-*"` | Archive multiple matching skills via glob pattern. |
| `skill-vault recategorize <name> "<New Cat>"` | Reorganize skill category without modifying `SKILL.md`. |
| `skill-vault restore <name>` | Restore an archived skill back to active availability. |
| `skill-vault restore --category "<Cat>"` | Restore all skills in a specific category. |
| `skill-vault search "<query>"` | Search skills across names, descriptions, and categories. |
| `skill-vault reindex` | Regenerate `INDEX.md` and sync `backup_manifest.json`. |
| `skill-vault verify` | Audit bi-directional consistency across disk, manifest, and index. |
| `skill-vault verify --fix` | Audit and automatically self-heal all detected discrepancies. |

---

## 🎯 Key Design Principles

1. **`SKILL.md` Purity**: `SKILL.md` files are immutable instructions. Categories and routing metadata are stored strictly in `backup_manifest.json` and rendered in `INDEX.md`.
2. **Environment Agnostic**: Dynamically resolves workspace roots via CLI flags (`--base-dir`), environment variables (`$SKILL_VAULT_BASE`), script parents, or working directories.
3. **Zero Runtime Dependencies**: The core engine requires only Python 3 standard library (`os`, `sys`, `json`, `re`, `shutil`, `hashlib`, `argparse`, `pathlib`).
4. **Self-Healing Integrity**: Detects orphaned folders, phantom manifest entries, broken markdown links, and duplicate aliases.

---

## 🧪 Running the Test Suite

Skill Vault includes a comprehensive, sandboxed test harness:

```bash
# Run unit tests
python -m unittest discover -s tests -v

# Or via npm
npm test
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
