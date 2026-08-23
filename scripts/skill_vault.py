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
        print(f"  • Active skills:  {self.skills_dir}")
        print(f"  • Archive store:  {self.archive_dir}")

    def get_active_skill_dirs(self):
        """Discover active skill directories."""
        dirs = []
        if self.skills_dir.exists():
            dirs.append(self.skills_dir)

        for sub in [".agents/skills", ".claude/skills"]:
            p = self.base_dir / sub
            if p.exists():
                dirs.append(p)

        plugins_dir = self.base_dir / "plugins"
        if plugins_dir.exists():
            for p in plugins_dir.iterdir():
                if p.is_dir() and (p / "skills").exists():
                    dirs.append(p / "skills")
        return dirs

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

    # --- Actions ---

    def archive(self, name=None, pattern=None, category=None, keep_active=False):
        """Archive active skills with an assigned category."""
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
                shutil.rmtree(dest_dir)
            shutil.copytree(active_path, dest_dir)
            print(f"[Archived] {active_path} -> {dest_dir}")

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
                if force:
                    shutil.rmtree(original_path)
                else:
                    print(f"[Skip] Target exists: {original_path} (use --force to overwrite)")
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

        # Discover all archive directories physically on disk
        disk_skills = self.get_archived_skill_folders()
        for name, data in disk_skills.items():
            if data["has_skill_md"] and name not in manifest_by_folder:
                manifest_by_folder[name] = {
                    "name": name,
                    "category": "General & Utility Skills",
                    "original_path": self.make_portable_path(self.skills_dir / name),
                    "archived_path": self.make_portable_path(data["folder"]),
                }

        # Group by category
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

        # 1. Check Disk Skill Folders
        for name, d in disk_skills.items():
            if not d["has_skill_md"]:
                issues.append(f"[Disk Error] Folder '{name}' in archive is missing SKILL.md")
            elif d["size"] == 0:
                issues.append(f"[Disk Error] SKILL.md in '{name}' is 0 bytes (empty file)")

        # 2. Check Disk vs Manifest
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

        # 3. Check Manifest Path Integrity
        for item in manifest:
            name = item["name"]
            archived_path = self.resolve_portable_path(item.get("archived_path", ""))
            if not archived_path.exists():
                issues.append(f"[Broken Manifest Path] '{name}' archived_path does not exist: {archived_path}")
            elif not (archived_path / "SKILL.md").exists():
                issues.append(f"[Missing SKILL.md] '{name}' archived_path has no SKILL.md: {archived_path}")

            if not item.get("category"):
                warnings.append(f"[Missing Category] '{name}' in manifest has no category assigned")

        # 4. Check Disk vs INDEX.md
        index_names = set(indexed_skills.keys())
        unindexed_disk = disk_names - index_names
        if unindexed_disk:
            for name in sorted(unindexed_disk):
                issues.append(f"[Unindexed on Disk] '{name}' exists on disk but is NOT listed in INDEX.md")

        phantom_index = index_names - disk_names
        if phantom_index:
            for name in sorted(phantom_index):
                issues.append(f"[Phantom Index Entry] '{name}' listed in INDEX.md but does NOT exist on disk")

        # 5. Check INDEX.md vs Manifest
        unindexed_manifest = manifest_names - index_names
        if unindexed_manifest:
            for name in sorted(unindexed_manifest):
                issues.append(f"[Manifest/Index Mismatch] '{name}' is in backup_manifest.json but NOT in INDEX.md")

        # 6. Check INDEX.md Link Validity
        for name, data in indexed_skills.items():
            link_path_str = data.get("link_path")
            if link_path_str:
                if link_path_str.startswith("file:///"):
                    pass
                else:
                    target_file = (self.archive_dir / link_path_str).resolve()
                    if not target_file.exists():
                        issues.append(f"[Broken Index Link] '{name}' link target missing: {target_file}")

        # Summary Metrics
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


def main():
    parser = argparse.ArgumentParser(description="Skill Vault: Universal Agent Skill Lifecycle & Storage Manager")
    parser.add_argument("--base-dir", help="Explicit base directory for skills and archive")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    p_init = subparsers.add_parser("init", help="Bootstrap standard skill directory structure in workspace")

    # Archive
    p_arch = subparsers.add_parser("archive", help="Archive active skills into cold storage")
    p_arch.add_argument("name", nargs="?", help="Specific skill name")
    p_arch.add_argument("--pattern", help="Glob pattern (e.g. 'gcp-*')")
    p_arch.add_argument("--category", help="Category name (e.g. 'Cloud Architecture')")
    p_arch.add_argument("--keep-active", action="store_true", help="Do not delete source folder")

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

    args = parser.parse_args()
    mgr = SkillVault(base_dir=args.base_dir)

    if args.command == "init":
        mgr.init()
    elif args.command == "archive":
        mgr.archive(name=args.name, pattern=args.pattern, category=args.category, keep_active=args.keep_active)
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


if __name__ == "__main__":
    main()
