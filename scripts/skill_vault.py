#!/usr/bin/env python3
"""Skill Vault: Universal Skill Archive, Lifecycle Manager & Router.

Works across Google Antigravity, Claude Code, Cursor, CI/CD, and standalone repositories.
Resolves paths relatively without hardcoded user directories. Categories are stored
strictly in backup_manifest.json and INDEX.md, keeping SKILL.md files pure and untouched.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

# Default Core Foundation Skills that are protected from auto-archiving
DEFAULT_CORE_SKILLS = {
    "skill-vault",
    "accidental-data-loss-prevention",
    "managing-python-dependencies",
    "find-skills",
    "skill-repair",
}

# Workspace fingerprint signatures mapping to skill categories
WORKSPACE_FINGERPRINTS = {
    "BigQuery & Data Warehouse": [
        "dbt_project.yml",
        "dataform.json",
        "bigquery.json",
        "*.sql",
    ],
    "GCP & Data Engineering": [
        "dags",
        "airflow.cfg",
        "cloudbuild.yaml",
        "cloudbuild.json",
        "*.tf",
        "Dockerfile",
    ],
    "AlloyDB": [
        "alembic.ini",
        "alloydb.json",
    ],
    "Cloud SQL": [
        "cloudsql.json",
    ],
    "Science & Biomedicine": [
        "*.pdb",
        "*.fasta",
        "*.fa",
        "*.cif",
        "*.vcf",
        "*.bam",
    ],
    "Gemini API & AI Agents": [
        "agent.py",
        "evals.py",
        "gemini.json",
    ],
    "Android Development": [
        "build.gradle",
        "build.gradle.kts",
        "AndroidManifest.xml",
    ],
}


def parse_version_tuple(ver_str):
    """Parse version string into a comparable numeric tuple, e.g. 'v20' -> (20,), '1.1.5' -> (1, 1, 5)."""
    if not ver_str:
        return None
    cleaned = str(ver_str).strip().strip("'\"").lstrip("vV")
    nums = re.findall(r"\d+", cleaned)
    if nums:
        return tuple(int(n) for n in nums)
    return None


def get_skill_metadata(skill_dir):
    """Extract parsed version and latest modification timestamp for a skill directory."""
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"

    ver_tuple = None
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8", errors="ignore")
            fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                v_match = re.search(r"version:\s*([^\n]+)", fm_match.group(1), re.IGNORECASE)
                if v_match:
                    ver_tuple = parse_version_tuple(v_match.group(1))
        except Exception:
            pass

    latest_mtime = 0.0
    try:
        files = [f for f in skill_dir.rglob("*") if f.is_file()]
        if files:
            latest_mtime = max(f.stat().st_mtime for f in files)
        elif skill_dir.exists():
            latest_mtime = skill_dir.stat().st_mtime
    except Exception:
        pass

    return ver_tuple, latest_mtime


def compare_skill_recency(dir_a, dir_b):
    """Compare two skill directories to determine which is newer.

    Returns:
       1 if dir_a is newer than dir_b
      -1 if dir_b is newer than dir_a
       0 if they are equivalent in version and recency
    """
    ver_a, mtime_a = get_skill_metadata(dir_a)
    ver_b, mtime_b = get_skill_metadata(dir_b)

    # 1. Compare semantic/numeric versions if both exist and differ
    if ver_a is not None and ver_b is not None and ver_a != ver_b:
        return 1 if ver_a > ver_b else -1

    # 2. Compare file modification timestamps (allowing a 1-second margin for filesystem granularity)
    if abs(mtime_a - mtime_b) > 1.0:
        return 1 if mtime_a > mtime_b else -1

    return 0


def resolve_base_dir(cli_base=None):
    """Dynamically resolve the base directory for skills and archives."""
    if cli_base:
        p = Path(cli_base).resolve()
        if p.exists():
            return p

    env_base = os.environ.get("SKILL_VAULT_BASE") or os.environ.get("SKILL_BASE_DIR") or os.environ.get("AGENTS_HOME")
    if env_base:
        p = Path(env_base).resolve()
        if p.exists():
            return p

    # Check ancestors of the script location
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if parent.name != "skill_archive" and (
            (parent / "skill_archive").exists() or (parent / "skills").exists()
        ):
            return parent

    cwd = Path.cwd().resolve()
    for candidate in [
        cwd,
        cwd / ".agents",
        cwd / ".claude",
        Path.home() / ".gemini" / "config",
        Path.home() / ".agents",
        Path.home() / ".claude",
    ]:
        if candidate.exists() and (
            (candidate / "skills").exists() or (candidate / "skill_archive").exists()
        ):
            return candidate

    return cwd


class SkillVault:
    def __init__(self, base_dir=None):
        self.base_dir = resolve_base_dir(base_dir)
        self.archive_dir = self.base_dir / "skill_archive"
        self.manifest_file = self.archive_dir / "backup_manifest.json"
        self.index_file = self.archive_dir / "INDEX.md"
        self.skills_dir = self.base_dir / "skills"

    def init(self):
        """Bootstrap standard directory structure for a new workspace or repository."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        (self.archive_dir / "skills").mkdir(parents=True, exist_ok=True)
        if not self.manifest_file.exists():
            self.save_manifest([])
        if not self.index_file.exists():
            self.index_file.write_text("# Skill Archive Index\n\nTotal Archived Skills: 0\n", encoding="utf-8")
        print(f"[Initialized] Skill Vault initialized at: {self.base_dir}")
        print(f"  * Active skills:  {self.skills_dir}")
        print(f"  * Archive store:  {self.archive_dir}")

    def get_active_skill_dirs(self):
        """Discover active skill directories."""
        dirs = []
        if self.skills_dir.exists():
            dirs.append(self.skills_dir)

        for sub in [".agents/skills", ".claude/skills"]:
            p = self.base_dir / sub
            if p.exists() and p not in dirs:
                dirs.append(p)

        # Also search active working directory and its skill locations if distinct from base_dir
        cwd = Path.cwd().resolve()
        if cwd != self.base_dir:
            for sub in ["skills", ".agents/skills", ".claude/skills"]:
                p = cwd / sub
                if p.exists() and p not in dirs:
                    dirs.append(p)

        # If base_dir is nested inside a skills folder (e.g. skills/skill-vault)
        if self.base_dir.parent.name == "skills" and self.base_dir.parent.exists():
            if self.base_dir.parent not in dirs:
                dirs.append(self.base_dir.parent)
            parent_plugins = self.base_dir.parent.parent / "plugins"
            if parent_plugins.exists():
                for p in parent_plugins.iterdir():
                    if p.is_dir() and (p / "skills").exists() and (p / "skills") not in dirs:
                        dirs.append(p / "skills")

        plugins_dir = self.base_dir / "plugins"
        if plugins_dir.exists():
            for p in plugins_dir.iterdir():
                if p.is_dir() and (p / "skills").exists() and (p / "skills") not in dirs:
                    dirs.append(p / "skills")
        return dirs

    def parse_skill_name(self, skill_md_path):
        """Extract name from SKILL.md frontmatter."""
        skill_md_path = Path(skill_md_path)
        if not skill_md_path.exists():
            return None
        try:
            content = skill_md_path.read_text(encoding="utf-8", errors="ignore")
            fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                n_match = re.search(r"^name:\s*([^\n]+)", fm_match.group(1), re.MULTILINE)
                if n_match:
                    return n_match.group(1).strip().strip("'\"")
        except Exception:
            pass
        return None

    def get_active_skills(self):
        """Discover all currently active skills on disk across standard and plugin layouts."""
        active = {}
        for search_dir in self.get_active_skill_dirs():
            if not search_dir.exists():
                continue

            # Case 1: search_dir contains subdirectories with SKILL.md (e.g. skills/<name>/SKILL.md)
            for folder in search_dir.iterdir():
                if folder.is_dir() and (folder / "SKILL.md").exists():
                    skill_name = self.parse_skill_name(folder / "SKILL.md") or folder.name
                    desc = self.parse_skill_description(folder / "SKILL.md")
                    active[skill_name] = {
                        "name": skill_name,
                        "path": str(folder),
                        "relative_path": self.make_portable_path(folder),
                        "description": desc,
                        "single_skill_dir": False,
                    }

            # Case 2: search_dir itself has SKILL.md directly (e.g. plugins/<plugin>/skills/SKILL.md)
            if (search_dir / "SKILL.md").exists():
                skill_name = self.parse_skill_name(search_dir / "SKILL.md") or search_dir.parent.name
                desc = self.parse_skill_description(search_dir / "SKILL.md")
                active[skill_name] = {
                    "name": skill_name,
                    "path": str(search_dir),
                    "relative_path": self.make_portable_path(search_dir),
                    "description": desc,
                    "single_skill_dir": True,
                }
        return active

    def get_archived_skill_folders(self):
        """Discover all skill folders physically present in the archive directory."""
        archive_subdirs = [self.archive_dir / "skills"]
        if self.archive_dir.exists():
            for p in self.archive_dir.iterdir():
                if p.is_dir() and p.name.startswith("plugins_") and p.name.endswith("_skills"):
                    archive_subdirs.append(p)

        folders = {}
        for base in archive_subdirs:
            if base.exists():
                for folder in base.iterdir():
                    if folder.is_dir():
                        skill_md = folder / "SKILL.md"
                        folders[folder.name] = {
                            "name": folder.name,
                            "folder": folder,
                            "skill_md": skill_md,
                            "has_skill_md": skill_md.exists(),
                            "size": skill_md.stat().st_size if skill_md.exists() else 0,
                        }
        return folders

    def load_manifest(self):
        """Load backup_manifest.json."""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Warning] Failed to parse {self.manifest_file}: {e}")
        return []

    def save_manifest(self, manifest):
        """Save manifest sorted by category and name."""
        manifest.sort(key=lambda x: (x.get("category", "").lower(), x.get("name", "").lower()))
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def parse_skill_description(self, skill_md_path):
        """Extract description from SKILL.md without modifying it."""
        skill_md_path = Path(skill_md_path)
        if not skill_md_path.exists():
            return "No description available."

        with open(skill_md_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            desc_match = re.search(
                r"^description:\s*(?:>[-+]?|\|[-+]?)?\s*\n?(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
                fm_text,
                re.DOTALL | re.MULTILINE,
            )
            if desc_match:
                raw_desc = desc_match.group(1).strip()
                return " ".join(line.strip() for line in raw_desc.splitlines() if line.strip())
            simple_desc = re.search(r"^description:\s*([^\n]+)", fm_text, re.MULTILINE)
            if simple_desc:
                return simple_desc.group(1).strip().strip("'\"")
        return "No description available."

    def find_active_skill(self, skill_name):
        """Find active skill across discovered search paths."""
        for search_dir in self.get_active_skill_dirs():
            target = search_dir / skill_name
            if target.exists() and (target / "SKILL.md").exists():
                return target
        return None

    def make_portable_path(self, abs_path):
        """Convert path to relative from base_dir if possible."""
        try:
            return str(Path(abs_path).resolve().relative_to(self.base_dir))
        except ValueError:
            return str(abs_path)

    def resolve_portable_path(self, path_str):
        """Resolve a stored relative path back to an absolute Path."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return (self.base_dir / p).resolve()

    def parse_index_file(self):
        """Parse INDEX.md and return extracted skills with categories and link targets."""
        if not self.index_file.exists():
            return {}

        with open(self.index_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        indexed_skills = {}
        current_category = "General & Utility Skills"

        for line in content.splitlines():
            cat_match = re.match(r"^##\s+(.*?)\s+\(\d+\s+skills?\)", line)
            if cat_match:
                current_category = cat_match.group(1).strip()
                continue

            skill_match = re.match(r"^###\s+`([^`]+)`", line)
            if skill_match:
                skill_name = skill_match.group(1).strip()
                indexed_skills[skill_name] = {
                    "name": skill_name,
                    "category": current_category,
                    "link_path": None,
                }
                continue

            link_match = re.search(r"\- \*\*Archived Path\*\*:\s+\[`SKILL\.md`\]\((.*?)\)", line)
            if link_match and indexed_skills:
                last_skill = list(indexed_skills.keys())[-1]
                if indexed_skills[last_skill]["link_path"] is None:
                    indexed_skills[last_skill]["link_path"] = link_match.group(1).strip()

        return indexed_skills

    # --- Workspace & Optimization Engine ---

    def detect_workspace_categories(self, workspace_path=None):
        """Inspect workspace files and return matched skill categories."""
        target_ws = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        matched = {}

        for category, patterns in WORKSPACE_FINGERPRINTS.items():
            for pat in patterns:
                if "*" in pat:
                    matches = list(target_ws.glob(pat)) + list(target_ws.glob(f"**/{pat}"))[:5]
                    if matches:
                        matched.setdefault(category, []).append(pat)
                        break
                else:
                    if (target_ws / pat).exists() or list(target_ws.glob(f"**/{pat}"))[:1]:
                        matched.setdefault(category, []).append(pat)
                        break

        return matched

    def optimize(self, workspace_path=None, protected_skills=None, dry_run=False, force=False):
        """Automatically minimize active skills to essential Core + workspace-relevant skills.
        
        Archives unneeded active skills into cold storage and mounts matching domain skills,
        prioritizing newer versions when versions overlap.
        """
        target_ws = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        core_set = set(DEFAULT_CORE_SKILLS)
        if protected_skills:
            core_set.update(protected_skills)

        print("==================================================")
        print("          SKILL VAULT AUTO-OPTIMIZATION")
        print(f"  Target Workspace: {target_ws}")
        print("==================================================\n")

        # 1. Detect workspace domain
        detected_categories = self.detect_workspace_categories(target_ws)
        if detected_categories:
            print("Detected Tech Stack & Fingerprints:")
            for cat, sigs in detected_categories.items():
                print(f"  * {cat} (matched: {', '.join(sigs)})")
        else:
            print("Detected Tech Stack: Generic / Multi-purpose (Only Core Foundation Skills required)")
        print("")

        # 2. Inspect active skills vs vault
        active_map = self.get_active_skills()
        manifest = self.load_manifest()
        manifest_by_name = {m["name"]: m for m in manifest}

        to_archive = []
        to_keep = []

        for name, data in active_map.items():
            if name in core_set:
                to_keep.append((name, "Core Foundation Skill"))
            else:
                skill_cat = manifest_by_name.get(name, {}).get("category", "General & Utility Skills")
                if skill_cat in detected_categories:
                    to_keep.append((name, f"Matched Stack ({skill_cat})"))
                else:
                    to_archive.append((name, skill_cat))

        # Check if any kept active skill has a newer version in the archive
        to_upgrade = []
        for name, reason in to_keep:
            if name in manifest_by_name:
                item = manifest_by_name[name]
                archived_path = self.resolve_portable_path(item.get("archived_path", ""))
                active_path = self.find_active_skill(name)
                if archived_path.exists() and active_path and active_path.exists():
                    if compare_skill_recency(archived_path, active_path) > 0:
                        to_upgrade.append((name, reason))

        # 3. Determine skills in vault that should be mounted
        to_mount = []
        for cat in detected_categories.keys():
            for item in manifest:
                if item.get("category") == cat and item["name"] not in active_map:
                    to_mount.append((item["name"], cat))

        # Output Plan
        print(f"Active Skills Action Plan:")
        print(f"  * Retained in Context ({len(to_keep)} skills):")
        for name, reason in to_keep:
            print(f"    [KEEP] {name} - {reason}")

        if to_upgrade:
            print(f"\n  * Upgrading Active Skills with Newer Vault Versions ({len(to_upgrade)} skills):")
            for name, reason in to_upgrade:
                print(f"    [UPGRADE] {name} (Newer version found in Vault)")

        if to_archive:
            print(f"\n  * Evicting to Cold Storage Archive ({len(to_archive)} skills):")
            for name, cat in to_archive:
                print(f"    [ARCHIVE] {name} ({cat})")
        else:
            print("\n  * Evictions: None needed (Context is already minimal).")

        if to_mount:
            print(f"\n  * Mounting from Vault ({len(to_mount)} skills):")
            for name, cat in to_mount:
                print(f"    [MOUNT] {name} ({cat})")

        if dry_run:
            print("\n[Dry Run] Optimization preview complete. No files were moved.")
            return

        # Execute Upgrades
        if to_upgrade:
            print("\nExecuting Auto-Upgrades from Newer Vault Copies...")
            for name, _ in to_upgrade:
                self.restore(name=name, force=True)

        # Execute Evictions (Archive)
        if to_archive:
            print("\nExecuting Auto-Archival...")
            for name, cat in to_archive:
                self.archive(name=name, category=cat, keep_active=False, force=force)

        # Execute Mounts (Restore)
        if to_mount:
            print("\nExecuting Auto-Mounts...")
            for name, cat in to_mount:
                self.restore(name=name, force=force)

        print("\n[OK] Optimization complete! Active context surface is at absolute minimum.")

    # --- Sync & Ingestion Engine ---

    def infer_category(self, skill_name, skill_desc=""):
        """Infer an appropriate category for a new skill based on name and description keywords."""
        text = f"{skill_name} {skill_desc}".lower()
        if any(k in text for k in ["gemini", "adk", "live api", "llm agent", "vertex ai"]):
            return "Gemini API & AI Agents"
        if any(k in text for k in ["android", "gradle", "apk", "adb"]):
            return "Android Development"
        if any(k in text for k in ["bigquery", "dbt", "dataform", "data warehouse", "lakehouse"]):
            return "BigQuery & Data Warehouse"
        if any(k in text for k in ["alloydb", "omni"]):
            return "AlloyDB"
        if any(k in text for k in ["cloud sql", "postgres", "mysql"]):
            return "Cloud SQL"
        if any(k in text for k in ["protein", "alphafold", "pdb", "dna", "rna", "chembl", "bioinformatics", "variant", "genome", "pymol"]):
            return "Science & Biomedicine"
        if any(k in text for k in ["gcp", "airflow", "composer", "spanner", "dataflow", "dataproc", "pubsub", "cloud storage"]):
            return "GCP & Data Engineering"
        return "General & Utility Skills"

    def sync(self, dry_run=False, keep_active=False, force=False, protect_skills=None):
        """Automatically scan plugins and active directories for new or updated skills,
        ingest them into the vault, preserve Core Foundation Skills, and prune non-core active skills."""
        print("==================================================")
        print("           SKILL VAULT AUTO-SYNC & INGEST")
        print(f"  Base Directory: {self.base_dir}")
        print(f"  Vault Store:    {self.archive_dir}")
        print("==================================================\n")

        core_set = set(DEFAULT_CORE_SKILLS)
        if protect_skills:
            core_set.update(protect_skills)

        active_skills = self.get_active_skills()
        manifest = self.load_manifest()
        manifest_map = {m["name"]: m for m in manifest}

        to_ingest_new = []
        to_ingest_update = []
        to_prune = []
        in_sync = []
        retained_core = []

        for name, data in sorted(active_skills.items()):
            active_path = Path(data["path"])
            is_core = name in core_set

            if name in manifest_map:
                item = manifest_map[name]
                archived_path = self.resolve_portable_path(item.get("archived_path", ""))
                if not archived_path.exists():
                    archived_path = self.archive_dir / "skills" / name

                recency = compare_skill_recency(active_path, archived_path)
                if recency > 0 or force:
                    to_ingest_update.append((name, data, item.get("category") or self.infer_category(name, data["description"])))
                else:
                    in_sync.append(name)
            else:
                assigned_cat = self.infer_category(name, data["description"])
                to_ingest_new.append((name, data, assigned_cat))

            if is_core:
                retained_core.append(name)
            elif not keep_active:
                to_prune.append((name, data))

        print("Scan Results:")
        print(f"  * New skills to ingest into vault:     {len(to_ingest_new)}")
        for name, _, cat in to_ingest_new:
            print(f"    [NEW] {name} -> Category: {cat}")

        print(f"  * Updated skills to refresh in vault:  {len(to_ingest_update)}")
        for name, _, cat in to_ingest_update:
            print(f"    [UPDATE] {name} (Newer active version detected)")

        print(f"  * In-sync skills in vault:             {len(in_sync)}")
        print(f"  * Retained Core Foundation Skills:     {len(retained_core)} ({', '.join(sorted(retained_core))})")
        print(f"  * Non-core active skills to prune:     {len(to_prune)}")
        for name, _ in to_prune:
            print(f"    [PRUNE] {name} (Will be removed from active context to prevent context bloat)")
        print("")

        if dry_run:
            print("[Dry Run] Preview complete. No files were modified.")
            return 0

        total_ingested = 0
        items_to_write = to_ingest_new + to_ingest_update
        for name, data, cat in items_to_write:
            active_path = Path(data["path"])
            if name in manifest_map and manifest_map[name].get("archived_path"):
                dest = self.resolve_portable_path(manifest_map[name]["archived_path"])
            else:
                dest = self.archive_dir / "skills" / name

            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)

            shutil.copytree(active_path, dest)
            print(f"[Vaulted] {name} -> {dest}")

            manifest_map[name] = {
                "name": name,
                "category": cat,
                "original_path": data["relative_path"],
                "archived_path": self.make_portable_path(dest),
            }
            total_ingested += 1

        for name, data in to_prune:
            active_path = Path(data["path"])
            if data.get("single_skill_dir"):
                for sub in active_path.iterdir():
                    if sub.is_dir():
                        shutil.rmtree(sub)
                    else:
                        sub.unlink()
                print(f"[Pruned] Emptied single-skill directory: {active_path}")
            else:
                if active_path.exists():
                    shutil.rmtree(active_path)
                    print(f"[Pruned] Removed active folder: {active_path}")

        if total_ingested > 0 or to_prune:
            self.save_manifest(list(manifest_map.values()))
            self.reindex()
            self.verify()

        print(f"\n[OK] Sync complete: {total_ingested} skill(s) vaulted/refreshed, {len(to_prune)} active skill(s) pruned.")
        print(f"Active context memory is clean with {len(retained_core)} Core Foundation Skill(s).\n")
        return 0

    # --- Actions ---

    def list_skills(self, show_active=True, show_archived=True, category_filter=None, as_json=False, summary_only=False):
        """Present active and archived skills in structured, human-readable or JSON formats."""
        active_map = self.get_active_skills() if show_active else {}
        manifest = self.load_manifest() if show_archived else []

        if category_filter and show_archived:
            manifest = [m for m in manifest if m.get("category", "").lower() == category_filter.lower()]

        archived_by_cat = {}
        for item in manifest:
            cat = item.get("category", "General & Utility Skills")
            archived_path = self.resolve_portable_path(item["archived_path"])
            skill_md = archived_path / "SKILL.md"
            desc = self.parse_skill_description(skill_md)
            archived_by_cat.setdefault(cat, []).append({
                "name": item["name"],
                "path": str(archived_path),
                "relative_path": item["archived_path"],
                "description": desc,
            })

        if as_json:
            result = {}
            if show_active:
                result["active"] = list(active_map.values())
            if show_archived:
                result["archived"] = archived_by_cat
                result["archived_total"] = len(manifest)
            print(json.dumps(result, indent=2))
            return

        print("==================================================")
        print("                 SKILL VAULT OVERVIEW")
        print(f"  Base Directory: {self.base_dir}")
        print("==================================================\n")

        total_active = len(active_map)
        total_archived = len(manifest)
        total_categories = len(archived_by_cat)

        print("Storage Tier Summary:")
        if show_active:
            print(f"  * L1 Active Context Memory:  {total_active} skill(s)")
        if show_archived:
            print(f"  * L2 Cold Storage Archive:   {total_archived} skill(s) across {total_categories} categories")
        print("")

        if summary_only:
            if show_archived and archived_by_cat:
                print("Archived Categories Breakdown:")
                for cat, skills in sorted(archived_by_cat.items()):
                    print(f"  - {cat}: {len(skills)} skill(s)")
                print("")
            return

        if show_active:
            print("--------------------------------------------------")
            print(f"  [L1 ACTIVE SKILLS] ({total_active} in context)")
            print("--------------------------------------------------")
            if not active_map:
                print("  (No active skills found. Use 'restore' to mount skills from archive.)\n")
            else:
                for name, data in sorted(active_map.items()):
                    desc = data["description"]
                    desc_snippet = desc[:110] + "..." if len(desc) > 110 else desc
                    print(f"  * {name}")
                    print(f"    Desc: {desc_snippet}")
                    print(f"    Path: {data['relative_path']}")
                print("")

        if show_archived:
            print("--------------------------------------------------")
            print(f"  [L2 ARCHIVED SKILLS] ({total_archived} in vault)")
            print("--------------------------------------------------")
            if not archived_by_cat:
                print("  (No archived skills found.)\n")
            else:
                for cat, skills in sorted(archived_by_cat.items()):
                    print(f"\n  [{cat}] ({len(skills)} skills):")
                    for s in sorted(skills, key=lambda x: x["name"].lower()):
                        desc = s["description"]
                        desc_snippet = desc[:110] + "..." if len(desc) > 110 else desc
                        print(f"    * {s['name']}: {desc_snippet}")
                print("")

    def archive(self, name=None, pattern=None, category=None, keep_active=False, force=False):
        """Archive active skills with an assigned category, prioritizing newer versions."""
        manifest = self.load_manifest()
        manifest_map = {item["name"]: item for item in manifest}

        skills_to_archive = []
        if name:
            skills_to_archive.append(name)
        elif pattern:
            regex = re.compile(pattern.replace("*", ".*"))
            for s_dir in self.get_active_skill_dirs():
                for item in s_dir.iterdir():
                    if item.is_dir() and regex.match(item.name):
                        skills_to_archive.append(item.name)

        if not skills_to_archive:
            print("No matching active skills found to archive.")
            return

        category_name = category.strip() if category else None

        for skill_name in sorted(set(skills_to_archive)):
            active_path = self.find_active_skill(skill_name)
            if not active_path:
                print(f"[Skip] Active skill '{skill_name}' not found.")
                continue

            dest_dir = self.archive_dir / "skills" / skill_name
            dest_dir.parent.mkdir(parents=True, exist_ok=True)

            if dest_dir.exists():
                recency = compare_skill_recency(active_path, dest_dir)
                if recency < 0 and not force:
                    print(f"[Skip] L2 archive '{skill_name}' is newer than active L1 version. Preserving newer archive (use --force to overwrite).")
                    if not keep_active:
                        shutil.rmtree(active_path)
                        print(f"[Cleaned] Removed older active directory: {active_path}")
                    continue
                elif recency > 0:
                    print(f"[Archived] Overwriting older L2 archive with newer active L1 version: {active_path} -> {dest_dir}")
                    shutil.rmtree(dest_dir)
                else:
                    shutil.rmtree(dest_dir)
                    print(f"[Archived] {active_path} -> {dest_dir}")
            else:
                print(f"[Archived] {active_path} -> {dest_dir}")

            shutil.copytree(active_path, dest_dir)

            existing_cat = manifest_map.get(skill_name, {}).get("category")
            assigned_cat = category_name or existing_cat or "General & Utility Skills"

            manifest_map[skill_name] = {
                "name": skill_name,
                "category": assigned_cat,
                "original_path": self.make_portable_path(active_path),
                "archived_path": self.make_portable_path(dest_dir),
            }

            if not keep_active:
                shutil.rmtree(active_path)
                print(f"[Cleaned] Removed active directory: {active_path}")

        self.save_manifest(list(manifest_map.values()))
        self.reindex()
        print("Archiving complete.")

    def recategorize(self, name, new_category):
        """Update category for an archived skill."""
        manifest = self.load_manifest()
        manifest_map = {item["name"]: item for item in manifest}

        if name not in manifest_map:
            print(f"[Error] Skill '{name}' not found in manifest.")
            return

        old_cat = manifest_map[name].get("category", "Uncategorized")
        manifest_map[name]["category"] = new_category.strip()
        self.save_manifest(list(manifest_map.values()))
        self.reindex()
        print(f"[Recategorized] '{name}': '{old_cat}' -> '{new_category.strip()}'")

    def restore(self, name=None, pattern=None, category=None, restore_all=False, force=False):
        """Restore archived skills back to active locations."""
        manifest = self.load_manifest()
        if not manifest:
            print("Manifest is empty. Nothing to restore.")
            return

        targets = []
        if restore_all:
            targets = manifest
        elif name:
            targets = [m for m in manifest if m["name"] == name]
        elif pattern:
            regex = re.compile(pattern.replace("*", ".*"))
            targets = [m for m in manifest if regex.match(m["name"])]
        elif category:
            targets = [m for m in manifest if m.get("category", "").lower() == category.lower()]

        if not targets:
            print("No matching skills found to restore.")
            return

        for item in targets:
            archived_path = self.resolve_portable_path(item["archived_path"])
            original_path = self.resolve_portable_path(item["original_path"])

            if not archived_path.exists():
                print(f"[Error] Missing archive source: {archived_path}")
                continue

            original_path.parent.mkdir(parents=True, exist_ok=True)
            if original_path.exists():
                recency = compare_skill_recency(archived_path, original_path)
                if recency > 0 or force:
                    shutil.rmtree(original_path)
                    shutil.copytree(archived_path, original_path)
                    print(f"[Restored] Updated L1 with newer L2 version: {item['name']} -> {original_path}")
                    continue
                else:
                    print(f"[Skip] Target L1 skill '{item['name']}' is already newer than or equal to L2 archive (use --force to overwrite)")
                    continue

            shutil.copytree(archived_path, original_path)
            print(f"[Restored] {item['name']} -> {original_path}")

        print("Restoration complete.")

    def reindex(self):
        """Rebuild INDEX.md grouped by manifest categories with portable relative links."""
        manifest = self.load_manifest()
        manifest_by_folder = {}

        for item in manifest:
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            if archived_path.exists() and (archived_path / "SKILL.md").exists():
                folder_name = archived_path.name
                if folder_name not in manifest_by_folder or item.get("name") == folder_name:
                    manifest_by_folder[folder_name] = {
                        "name": folder_name,
                        "category": item.get("category") or "General & Utility Skills",
                        "original_path": item.get("original_path", self.make_portable_path(self.skills_dir / folder_name)),
                        "archived_path": self.make_portable_path(archived_path),
                    }

        disk_skills = self.get_archived_skill_folders()
        for name, data in disk_skills.items():
            if data["has_skill_md"] and name not in manifest_by_folder:
                manifest_by_folder[name] = {
                    "name": name,
                    "category": "General & Utility Skills",
                    "original_path": self.make_portable_path(self.skills_dir / name),
                    "archived_path": self.make_portable_path(data["folder"]),
                }

        categories = {}
        for name, item in manifest_by_folder.items():
            cat = item.get("category") or "General & Utility Skills"
            categories.setdefault(cat, []).append(item)

        total_count = len(manifest_by_folder)
        lines = ["# Skill Archive Index", "", f"Total Archived Skills: {total_count}", ""]

        for cat in sorted(categories.keys()):
            skills_in_cat = sorted(categories[cat], key=lambda x: x["name"].lower())
            lines.append(f"## {cat} ({len(skills_in_cat)} skills)")
            lines.append("")
            for s in skills_in_cat:
                skill_name = s["name"]
                archived_path = self.resolve_portable_path(s["archived_path"])
                skill_md = archived_path / "SKILL.md"
                desc = self.parse_skill_description(skill_md)

                lines.append(f"### `{skill_name}`")
                lines.append(f"- **Description**: {desc}")

                try:
                    rel_link = skill_md.relative_to(self.archive_dir).as_posix()
                    lines.append(f"- **Archived Path**: [`SKILL.md`]({rel_link})")
                except ValueError:
                    file_uri = skill_md.resolve().as_uri().replace("file:////", "file:///")
                    lines.append(f"- **Archived Path**: [`SKILL.md`]({file_uri})")
                lines.append("")

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")

        self.save_manifest(list(manifest_by_folder.values()))
        print(f"[Reindexed] {total_count} skills across {len(categories)} categories (Base: {self.base_dir}).")

    def verify(self, fix=False):
        """Perform a comprehensive bi-directional integrity check across Disk, Manifest, and INDEX.md."""
        print("==================================================")
        print("       SKILL VAULT INTEGRITY AUDIT")
        print(f"  Base Directory: {self.base_dir}")
        print(f"  Archive Store:  {self.archive_dir}")
        print("==================================================\n")

        disk_skills = self.get_archived_skill_folders()
        manifest = self.load_manifest()
        manifest_map = {m["name"]: m for m in manifest}
        indexed_skills = self.parse_index_file()

        issues = []
        warnings = []

        for name, d in disk_skills.items():
            if not d["has_skill_md"]:
                issues.append(f"[Disk Error] Folder '{name}' in archive is missing SKILL.md")
            elif d["size"] == 0:
                issues.append(f"[Disk Error] SKILL.md in '{name}' is 0 bytes (empty file)")

        disk_names = set(disk_skills.keys())
        manifest_names = set(manifest_map.keys())

        unmanifested_disk = disk_names - manifest_names
        if unmanifested_disk:
            for name in sorted(unmanifested_disk):
                issues.append(f"[Uncataloged on Disk] '{name}' exists in archive folder but NOT in backup_manifest.json")

        phantom_manifest = manifest_names - disk_names
        if phantom_manifest:
            for name in sorted(phantom_manifest):
                issues.append(f"[Phantom Manifest Entry] '{name}' listed in backup_manifest.json but NOT found on disk")

        for item in manifest:
            name = item["name"]
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            if not archived_path.exists():
                issues.append(f"[Broken Manifest Path] '{name}' archived_path does not exist: {archived_path}")
            elif not (archived_path / "SKILL.md").exists():
                issues.append(f"[Missing SKILL.md] '{name}' archived_path has no SKILL.md: {archived_path}")

            if not item.get("category"):
                warnings.append(f"[Missing Category] '{name}' in manifest has no category assigned")

        index_names = set(indexed_skills.keys())
        unindexed_disk = disk_names - index_names
        if unindexed_disk:
            for name in sorted(unindexed_disk):
                issues.append(f"[Unindexed on Disk] '{name}' exists on disk but is NOT listed in INDEX.md")

        phantom_index = index_names - disk_names
        if phantom_index:
            for name in sorted(phantom_index):
                issues.append(f"[Phantom Index Entry] '{name}' listed in INDEX.md but does NOT exist on disk")

        unindexed_manifest = manifest_names - index_names
        if unindexed_manifest:
            for name in sorted(unindexed_manifest):
                issues.append(f"[Manifest/Index Mismatch] '{name}' is in backup_manifest.json but NOT in INDEX.md")

        for name, data in indexed_skills.items():
            link_path_str = data.get("link_path")
            if link_path_str:
                if link_path_str.startswith("file:///"):
                    pass
                else:
                    target_file = (self.archive_dir / link_path_str).resolve()
                    if not target_file.exists():
                        issues.append(f"[Broken Index Link] '{name}' link target missing: {target_file}")

        print("Component Counts:")
        print(f"  * Physical Folders on Disk:        {len(disk_skills)}")
        print(f"  * Entries in backup_manifest.json: {len(manifest)}")
        print(f"  * Entries in INDEX.md:             {len(indexed_skills)}\n")

        if not issues and not warnings:
            print("[OK] 100% Integrity Verified! Disk, manifest, and index are in perfect sync.\n")
            return 0

        if warnings:
            print(f"Warnings ({len(warnings)}):")
            for w in warnings:
                print(f"  [!] {w}")
            print("")

        if issues:
            print(f"Discrepancies / Errors ({len(issues)}):")
            for iss in issues:
                print(f"  [X] {iss}")
            print("")

            if fix:
                print("[Self-Healing] Applying automatic repairs (--fix enabled)...")
                self.reindex()
                print("[Self-Healing] Reindexed and resynchronized successfully.\n")
                return 0
            else:
                print("Tip: Run with '--fix' (e.g. 'python skill_vault.py verify --fix') to automatically repair discrepancies.\n")
                return 1

        return 0

    def search(self, query):
        """Search archived skills."""
        q = query.lower()
        manifest = self.load_manifest()
        results = []

        for item in manifest:
            name = item["name"]
            cat = item.get("category", "General & Utility Skills")
            archived_path = self.resolve_portable_path(item["archived_path"])
            skill_md = archived_path / "SKILL.md"
            desc = self.parse_skill_description(skill_md)

            if q in name.lower() or q in desc.lower() or q in cat.lower():
                results.append((name, cat, desc, str(archived_path)))

        if not results:
            print(f"No archived skills matched '{query}'.")
            return

        print(f"Found {len(results)} matching skill(s):\n")
        for name, cat, desc, path_str in results:
            print(f"* {name} [{cat}]")
            desc_snippet = desc[:130] + "..." if len(desc) > 130 else desc
            print(f"  Description: {desc_snippet}")
            print(f"  Path: {path_str}\n")

    # --- Project Import Engine ---

    def resolve_vault_archive_dir(self, vault_arg=None):
        """Resolve the source vault archive directory."""
        if vault_arg:
            p = Path(vault_arg).resolve()
            if (p / "skill_archive").exists():
                return p / "skill_archive"
            return p

        env_vault = os.environ.get("SKILL_VAULT_DIR") or os.environ.get("SKILL_VAULT_ARCHIVE")
        if env_vault:
            p = Path(env_vault).resolve()
            if (p / "skill_archive").exists():
                return p / "skill_archive"
            return p

        env_base = os.environ.get("SKILL_VAULT_BASE") or os.environ.get("SKILL_BASE_DIR")
        if env_base:
            p = Path(env_base).resolve() / "skill_archive"
            if p.exists():
                return p

        # Check self.archive_dir
        if self.archive_dir.exists() and (
            (self.archive_dir / "skills").exists()
            or (self.archive_dir / "backup_manifest.json").exists()
        ):
            return self.archive_dir

        # Check standard global locations
        candidates = [
            Path.home() / ".gemini" / "config" / "skills" / "skill-vault" / "skill_archive",
            Path.home() / ".gemini" / "config" / "skills" / ".skill_archive",
            Path.home() / ".gemini" / "config" / "skill_archive",
            Path.home() / ".agents" / "skill_archive",
            Path.home() / ".claude" / "skill_archive",
        ]
        for cand in candidates:
            if cand.exists() and (
                (cand / "skills").exists() or (cand / "backup_manifest.json").exists()
            ):
                return cand

        return self.archive_dir

    def resolve_dest_dir(self, dest_arg=None):
        """Resolve target destination directory for imported skills."""
        if dest_arg:
            p = Path(dest_arg).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p

        cwd = Path.cwd().resolve()
        if (cwd / ".agents" / "skills").exists():
            return cwd / ".agents" / "skills"
        if (cwd / "skills").exists():
            return cwd / "skills"
        if (cwd / ".claude" / "skills").exists():
            return cwd / ".claude" / "skills"
        if (cwd / ".agents").exists():
            p = cwd / ".agents" / "skills"
            p.mkdir(parents=True, exist_ok=True)
            return p

        p = cwd / "skills"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def find_vault_skill(self, skill_name, vault_archive_dir, manifest_map=None):
        """Find the physical skill directory in a vault archive store."""
        vault_archive_dir = Path(vault_archive_dir).resolve()
        vault_base = (
            vault_archive_dir.parent
            if vault_archive_dir.name == "skill_archive"
            else vault_archive_dir
        )

        # 1. Check via manifest if provided
        if manifest_map and skill_name in manifest_map:
            item = manifest_map[skill_name]
            rel_archived = item.get("archived_path")
            if rel_archived:
                p1 = (vault_base / rel_archived).resolve()
                if p1.exists() and (p1 / "SKILL.md").exists():
                    return p1
                p2 = (vault_archive_dir / rel_archived).resolve()
                if p2.exists() and (p2 / "SKILL.md").exists():
                    return p2
                p3 = Path(rel_archived)
                if p3.is_absolute() and p3.exists() and (p3 / "SKILL.md").exists():
                    return p3

        # 2. Check vault_archive_dir / "skills" / skill_name
        p_std = vault_archive_dir / "skills" / skill_name
        if p_std.exists() and (p_std / "SKILL.md").exists():
            return p_std

        # 3. Check vault_archive_dir / skill_name
        p_direct = vault_archive_dir / skill_name
        if p_direct.exists() and (p_direct / "SKILL.md").exists():
            return p_direct

        # 4. Check nested plugins_*_skills subdirectories
        if vault_archive_dir.exists():
            for child in vault_archive_dir.iterdir():
                if child.is_dir():
                    candidate = child / skill_name
                    if candidate.exists() and (candidate / "SKILL.md").exists():
                        return candidate

        return None

    def import_skills(
        self,
        name=None,
        pattern=None,
        category=None,
        import_all=False,
        dest_dir=None,
        vault_dir=None,
        force=False,
        dry_run=False,
    ):
        """Import skills from a vault (global archive or specified) into a project destination."""
        vault_archive_dir = self.resolve_vault_archive_dir(vault_dir)
        dest_path = self.resolve_dest_dir(dest_dir)

        if not vault_archive_dir.exists():
            print(f"[Error] Vault archive directory does not exist: {vault_archive_dir}")
            return 1

        # Load vault manifest if present
        manifest_file = vault_archive_dir / "backup_manifest.json"
        vault_manifest = []
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    vault_manifest = json.load(f)
            except Exception as e:
                print(f"[Warning] Could not parse vault manifest at {manifest_file}: {e}")

        manifest_map = {item["name"]: item for item in vault_manifest if "name" in item}

        targets = []
        if import_all:
            if manifest_map:
                targets = sorted(manifest_map.keys())
            else:
                skills_base = vault_archive_dir / "skills"
                if skills_base.exists():
                    targets = sorted([d.name for d in skills_base.iterdir() if d.is_dir() and (d / "SKILL.md").exists()])
        elif category:
            cat_lower = category.strip().lower()
            if manifest_map:
                targets = sorted([n for n, item in manifest_map.items() if item.get("category", "").lower() == cat_lower])
            if not targets:
                print(f"[Warning] No skills found matching category '{category}' in vault manifest.")
        elif pattern:
            regex = re.compile(pattern.replace("*", ".*"))
            if manifest_map:
                targets = sorted([n for n in manifest_map.keys() if regex.match(n)])
            else:
                skills_base = vault_archive_dir / "skills"
                if skills_base.exists():
                    targets = sorted([d.name for d in skills_base.iterdir() if d.is_dir() and regex.match(d.name)])
        elif name:
            targets = [name.strip()]
        else:
            print("Please specify a skill name, --category, --pattern, or --all to import.")
            return 1

        if not targets:
            print("No matching skills found in vault to import.")
            return 1

        imported_count = 0
        skipped_count = 0
        error_count = 0

        print("==================================================")
        print("            SKILL VAULT PROJECT IMPORT")
        print(f"  Source Vault: {vault_archive_dir}")
        print(f"  Target Dest:  {dest_path}")
        print("==================================================\n")

        for skill_name in targets:
            source_skill_dir = self.find_vault_skill(skill_name, vault_archive_dir, manifest_map)
            if not source_skill_dir:
                print(f"[Error] Skill '{skill_name}' not found in vault ({vault_archive_dir})")
                error_count += 1
                continue

            target_skill_dir = dest_path / skill_name

            if target_skill_dir.exists():
                recency = compare_skill_recency(source_skill_dir, target_skill_dir)
                if recency <= 0 and not force:
                    print(f"[Skip] Project skill '{skill_name}' is already newer than or equal to vault version (use --force to overwrite)")
                    skipped_count += 1
                    continue
                else:
                    if dry_run:
                        print(f"[Dry Run] Would update project skill with newer vault version: {skill_name} -> {target_skill_dir}")
                    else:
                        shutil.rmtree(target_skill_dir)
                        shutil.copytree(source_skill_dir, target_skill_dir)
                        print(f"[Imported] Updated project skill with newer vault version: {skill_name} -> {target_skill_dir}")
                    imported_count += 1
            else:
                if dry_run:
                    print(f"[Dry Run] Would import: {skill_name} -> {target_skill_dir}")
                else:
                    shutil.copytree(source_skill_dir, target_skill_dir)
                    print(f"[Imported] {skill_name} -> {target_skill_dir}")
                imported_count += 1

        print(f"\n[OK] Import completed: {imported_count} imported, {skipped_count} skipped, {error_count} errors.")
        return 0 if error_count == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Skill Vault: Universal Agent Skill Lifecycle & Storage Manager")
    parser.add_argument("--base-dir", help="Explicit base directory for skills and archive")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    p_init = subparsers.add_parser("init", help="Bootstrap standard skill directory structure in workspace")

    # Optimize / Auto-Tune
    p_opt = subparsers.add_parser("optimize", help="Auto-minimize active skills to essential Core + workspace stack")
    p_opt.add_argument("--workspace", help="Path to workspace directory to inspect")
    p_opt.add_argument("--protect", nargs="*", help="Additional skill names to protect from auto-archiving")
    p_opt.add_argument("--dry-run", action="store_true", help="Preview optimization changes without moving files")
    p_opt.add_argument("--force", action="store_true", help="Force overwrite during optimization regardless of recency")

    # List / Overview
    p_list = subparsers.add_parser("list", help="Present active and archived skills")
    p_list.add_argument("-a", "--active", action="store_true", help="List only active skills (L1 Context)")
    p_list.add_argument("-c", "--archived", action="store_true", help="List only archived skills (L2 Vault)")
    p_list.add_argument("--category", help="Filter by category")
    p_list.add_argument("--summary", action="store_true", help="Show compact category summary")
    p_list.add_argument("--json", action="store_true", help="Output in structured JSON format")

    # Status (alias for list --summary)
    p_stat = subparsers.add_parser("status", help="Show summary of active and archived skills")
    p_stat.add_argument("--json", action="store_true", help="Output in structured JSON format")

    # Archive
    p_arch = subparsers.add_parser("archive", help="Archive active skills into cold storage")
    p_arch.add_argument("name", nargs="?", help="Specific skill name")
    p_arch.add_argument("--pattern", help="Glob pattern (e.g. 'gcp-*')")
    p_arch.add_argument("--category", help="Category name (e.g. 'Cloud Architecture')")
    p_arch.add_argument("--keep-active", action="store_true", help="Do not delete source folder")
    p_arch.add_argument("--force", action="store_true", help="Force overwrite in archive regardless of recency")

    # Recategorize
    p_rec = subparsers.add_parser("recategorize", help="Recategorize an archived skill in metadata")
    p_rec.add_argument("name", help="Skill name")
    p_rec.add_argument("category", help="New category name")

    # Restore
    p_rest = subparsers.add_parser("restore", help="Restore archived skills back to active availability")
    p_rest.add_argument("name", nargs="?", help="Specific skill name")
    p_rest.add_argument("--all", action="store_true", help="Restore all archived skills")
    p_rest.add_argument("--pattern", help="Glob pattern to restore")
    p_rest.add_argument("--category", help="Category name to restore")
    p_rest.add_argument("--force", action="store_true", help="Overwrite existing active directory")

    # Reindex
    p_idx = subparsers.add_parser("reindex", help="Rebuild INDEX.md and sync manifest")

    # Verify / Integrity Check
    p_ver = subparsers.add_parser("verify", help="Verify archive integrity across disk, manifest, and index")
    p_ver.add_argument("--fix", action="store_true", help="Automatically repair any detected discrepancies")

    # Search
    p_srch = subparsers.add_parser("search", help="Search archived skills by keyword, intent, or domain")
    p_srch.add_argument("query", help="Keyword to search for")

    # Sync
    p_sync = subparsers.add_parser("sync", help="Scan plugins and active skills, ingest new/updated skills, and prune non-core skills")
    p_sync.add_argument("--dry-run", action="store_true", help="Preview sync operations without moving or deleting files")
    p_sync.add_argument("--keep-active", action="store_true", help="Keep all scanned skills active in context instead of pruning")
    p_sync.add_argument("--force", action="store_true", help="Force overwrite in vault even if vault copy is newer")
    p_sync.add_argument("--protect", nargs="*", help="Additional skill names to protect from pruning")

    # Import
    p_imp = subparsers.add_parser("import", help="Import skills from vault into project or target directory")
    p_imp.add_argument("name", nargs="?", help="Specific skill name to import")
    p_imp.add_argument("--pattern", help="Glob pattern of skills to import (e.g. 'gcp-*')")
    p_imp.add_argument("--category", help="Import all skills in a category")
    p_imp.add_argument("--all", action="store_true", help="Import all skills from the vault")
    p_imp.add_argument("--dest", help="Destination directory in project (default: ./skills or ./.agents/skills)")
    p_imp.add_argument("--vault-dir", help="Explicit source vault archive directory")
    p_imp.add_argument("--force", action="store_true", help="Overwrite existing skill in project regardless of recency")
    p_imp.add_argument("--dry-run", action="store_true", help="Preview skills that would be imported without copying")

    args = parser.parse_args()
    mgr = SkillVault(base_dir=args.base_dir)

    if args.command == "init":
        mgr.init()
    elif args.command == "optimize":
        mgr.optimize(workspace_path=args.workspace, protected_skills=args.protect, dry_run=args.dry_run, force=args.force)
    elif args.command == "sync":
        sys.exit(
            mgr.sync(
                dry_run=args.dry_run,
                keep_active=args.keep_active,
                force=args.force,
                protect_skills=args.protect,
            )
        )
    elif args.command == "list":
        show_active = not args.archived or args.active
        show_archived = not args.active or args.archived
        mgr.list_skills(
            show_active=show_active,
            show_archived=show_archived,
            category_filter=args.category,
            as_json=args.json,
            summary_only=args.summary,
        )
    elif args.command == "status":
        mgr.list_skills(
            show_active=True,
            show_archived=True,
            as_json=args.json,
            summary_only=True,
        )
    elif args.command == "archive":
        mgr.archive(name=args.name, pattern=args.pattern, category=args.category, keep_active=args.keep_active, force=args.force)
    elif args.command == "recategorize":
        mgr.recategorize(name=args.name, new_category=args.category)
    elif args.command == "restore":
        mgr.restore(name=args.name, pattern=args.pattern, category=args.category, restore_all=args.all, force=args.force)
    elif args.command == "reindex":
        mgr.reindex()
    elif args.command == "verify":
        sys.exit(mgr.verify(fix=args.fix))
    elif args.command == "search":
        mgr.search(query=args.query)
    elif args.command == "import":
        sys.exit(
            mgr.import_skills(
                name=args.name,
                pattern=args.pattern,
                category=args.category,
                import_all=args.all,
                dest_dir=args.dest,
                vault_dir=args.vault_dir,
                force=args.force,
                dry_run=args.dry_run,
            )
        )


if __name__ == "__main__":
    main()
