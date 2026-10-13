#!/usr/bin/env python3
"""Comprehensive Test Suite & Test Harness for skill_vault.py.

Runs in an isolated sandbox without modifying real user skills or archives.
Validates:
1. Path resolution across environments
2. Workspace bootstrapping (init)
3. Presenting active and archived skills (list & status)
4. Workspace detection & automated optimization (optimize)
5. Archiving with LLM categories & preservation of SKILL.md
6. Restoring skills (single, pattern, category, overwrite)
7. Recategorization in manifest & index
8. Reindexing & relative link generation
9. Search matching
10. Bi-directional integrity audit & self-healing (--fix)
11. CLI command execution
"""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# Import SkillVault from the parent scripts directory
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from skill_vault import SkillVault, resolve_base_dir, parse_version_tuple, compare_skill_recency


class TestSkillVault(unittest.TestCase):
    def setUp(self):
        """Create an isolated sandbox for testing."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.test_dir.name).resolve()

        # Create standard layout
        self.skills_dir = self.base_dir / "skills"
        self.archive_dir = self.base_dir / "skill_archive"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Initialize manager targeting the sandbox base_dir
        self.mgr = SkillVault(base_dir=str(self.base_dir))

    def tearDown(self):
        """Clean up the sandbox."""
        self.test_dir.cleanup()

    def _create_mock_skill(self, base_path, name, description="A test skill description.", version=None, extra_files=None):
        """Helper to create a valid mock skill folder."""
        skill_dir = base_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        ver_header = f"version: {version}\n" if version else ""
        content = f"---\nname: {name}\n{ver_header}description: {description}\n---\n\n# {name}\n\nInstructions."
        skill_md.write_text(content, encoding="utf-8")

        if extra_files:
            for rel_file, file_content in extra_files.items():
                target_file = skill_dir / rel_file
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(file_content, encoding="utf-8")
        return skill_dir

    # --- 1. Base Directory Resolution Tests ---

    def test_base_dir_resolution(self):
        """Test base directory resolution via CLI argument, env var, and default."""
        # 1. Explicit CLI argument
        resolved = resolve_base_dir(cli_base=str(self.base_dir))
        self.assertEqual(resolved, self.base_dir)

        # 2. Environment variable
        os.environ["SKILL_VAULT_BASE"] = str(self.base_dir)
        try:
            resolved_env = resolve_base_dir()
            self.assertEqual(resolved_env, self.base_dir)
        finally:
            del os.environ["SKILL_VAULT_BASE"]

    def test_init_command(self):
        """Test initializing a fresh workspace."""
        empty_sandbox = tempfile.TemporaryDirectory()
        try:
            vault = SkillVault(base_dir=empty_sandbox.name)
            vault.init()
            self.assertTrue((Path(empty_sandbox.name) / "skills").exists())
            self.assertTrue((Path(empty_sandbox.name) / "skill_archive" / "backup_manifest.json").exists())
            self.assertTrue((Path(empty_sandbox.name) / "skill_archive" / "INDEX.md").exists())
        finally:
            empty_sandbox.cleanup()

    # --- 2. List & Status Presentation Tests ---

    def test_list_and_status_skills(self):
        """Test listing active and archived skills and status summary."""
        self._create_mock_skill(self.skills_dir, "active-skill-1", "Active skill description.")
        self._create_mock_skill(self.skills_dir, "archived-skill-1", "Archived skill description.")
        self.mgr.archive(name="archived-skill-1", category="Analytics")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.mgr.list_skills(show_active=True, show_archived=True)
            output = sys.stdout.getvalue()
            self.assertIn("L1 ACTIVE SKILLS", output)
            self.assertIn("active-skill-1", output)
            self.assertIn("L2 ARCHIVED SKILLS", output)
            self.assertIn("archived-skill-1", output)
            self.assertIn("[Analytics]", output)
        finally:
            sys.stdout = old_stdout

    # --- 3. Workspace Detection & Auto-Optimization Tests ---

    def test_detect_workspace_categories(self):
        """Test scanning files to fingerprint workspace stack."""
        ws = tempfile.TemporaryDirectory()
        try:
            ws_path = Path(ws.name)
            (ws_path / "dbt_project.yml").write_text("name: my_dbt_project", encoding="utf-8")
            (ws_path / "models").mkdir(parents=True, exist_ok=True)
            (ws_path / "models" / "query.sql").write_text("SELECT 1;", encoding="utf-8")

            detected = self.mgr.detect_workspace_categories(ws_path)
            self.assertIn("BigQuery & Data Warehouse", detected)
        finally:
            ws.cleanup()

    def test_optimize_minimization(self):
        """Test auto-minimization keeping core + matched skills, archiving unrelated skills."""
        # 1. Setup Active Skills
        self._create_mock_skill(self.skills_dir, "skill-vault", "Vault Core.")
        self._create_mock_skill(self.skills_dir, "accidental-data-loss-prevention", "Safety Core.")
        self._create_mock_skill(self.skills_dir, "unrelated-bio-skill", "Bio skill in active memory.")
        self._create_mock_skill(self.skills_dir, "bigquery-helper", "BigQuery tool in active memory.")

        # 2. Setup Archive Vault
        manifest = [
            {
                "name": "unrelated-bio-skill",
                "category": "Science & Biomedicine",
                "original_path": "skills/unrelated-bio-skill",
                "archived_path": "skill_archive/skills/unrelated-bio-skill",
            },
            {
                "name": "bigquery-helper",
                "category": "BigQuery & Data Warehouse",
                "original_path": "skills/bigquery-helper",
                "archived_path": "skill_archive/skills/bigquery-helper",
            },
            {
                "name": "vaulted-sql-tool",
                "category": "BigQuery & Data Warehouse",
                "original_path": "skills/vaulted-sql-tool",
                "archived_path": "skill_archive/skills/vaulted-sql-tool",
            },
        ]
        self.mgr.save_manifest(manifest)
        # Create vaulted skill folder
        self._create_mock_skill(self.archive_dir / "skills", "vaulted-sql-tool", "Vaulted SQL tool.")

        # 3. Create a SQL workspace
        ws = tempfile.TemporaryDirectory()
        try:
            ws_path = Path(ws.name)
            (ws_path / "query.sql").write_text("SELECT * FROM table;", encoding="utf-8")

            # Run optimize
            self.mgr.optimize(workspace_path=ws_path)

            # Core skills must remain active
            self.assertTrue((self.skills_dir / "skill-vault").exists())
            self.assertTrue((self.skills_dir / "accidental-data-loss-prevention").exists())

            # Matched BigQuery skills must be active
            self.assertTrue((self.skills_dir / "bigquery-helper").exists())
            self.assertTrue((self.skills_dir / "vaulted-sql-tool").exists())

            # Unrelated bio skill must be evicted to cold storage
            self.assertFalse((self.skills_dir / "unrelated-bio-skill").exists())
            self.assertTrue((self.archive_dir / "skills" / "unrelated-bio-skill").exists())
        finally:
            ws.cleanup()

    # --- 4. Archive Tests ---

    def test_archive_single_skill_with_category(self):
        """Test archiving a single active skill with category."""
        self._create_mock_skill(self.skills_dir, "cloud-sql-backup", "Manages database backups.")
        
        self.mgr.archive(name="cloud-sql-backup", category="Cloud Database")

        self.assertFalse((self.skills_dir / "cloud-sql-backup").exists())

        archived_skill = self.archive_dir / "skills" / "cloud-sql-backup"
        self.assertTrue((archived_skill / "SKILL.md").exists())

        content = (archived_skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: cloud-sql-backup", content)
        self.assertNotIn("Cloud Database", content)

        manifest = self.mgr.load_manifest()
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["name"], "cloud-sql-backup")
        self.assertEqual(manifest[0]["category"], "Cloud Database")

        index_content = self.mgr.index_file.read_text(encoding="utf-8")
        self.assertIn("## Cloud Database (1 skills)", index_content)
        self.assertIn("### `cloud-sql-backup`", index_content)

    def test_archive_pattern_and_keep_active(self):
        """Test archiving multiple skills with pattern matching and --keep-active."""
        self._create_mock_skill(self.skills_dir, "gcp-spanner", "Spanner tools.")
        self._create_mock_skill(self.skills_dir, "gcp-pubsub", "PubSub tools.")
        self._create_mock_skill(self.skills_dir, "aws-s3", "S3 tools.")

        self.mgr.archive(pattern="gcp-*", category="Google Cloud", keep_active=True)

        self.assertTrue((self.skills_dir / "gcp-spanner").exists())
        self.assertTrue((self.skills_dir / "gcp-pubsub").exists())
        self.assertTrue((self.archive_dir / "skills" / "gcp-spanner").exists())
        self.assertTrue((self.archive_dir / "skills" / "gcp-pubsub").exists())
        self.assertFalse((self.archive_dir / "skills" / "aws-s3").exists())

    # --- 5. Recategorize Tests ---

    def test_recategorize_skill(self):
        """Test updating a category without touching SKILL.md."""
        self._create_mock_skill(self.skills_dir, "data-cleaner", "Cleans raw datasets.")
        self.mgr.archive(name="data-cleaner", category="Initial Category")

        self.mgr.recategorize(name="data-cleaner", new_category="Data Engineering")

        manifest = self.mgr.load_manifest()
        self.assertEqual(manifest[0]["category"], "Data Engineering")

        index_content = self.mgr.index_file.read_text(encoding="utf-8")
        self.assertIn("## Data Engineering (1 skills)", index_content)
        self.assertNotIn("Initial Category", index_content)

    # --- 6. Restore Tests ---

    def test_restore_single_and_category(self):
        """Test restoring archived skills back to active locations."""
        self._create_mock_skill(self.skills_dir, "bigquery-optimizer", "Optimizes SQL.")
        self._create_mock_skill(self.skills_dir, "bigquery-partitioning", "Handles partitioning.")
        self.mgr.archive(pattern="bigquery-*", category="Data Warehouse")

        self.assertFalse((self.skills_dir / "bigquery-optimizer").exists())
        self.assertFalse((self.skills_dir / "bigquery-partitioning").exists())

        self.mgr.restore(name="bigquery-optimizer")
        self.assertTrue((self.skills_dir / "bigquery-optimizer" / "SKILL.md").exists())
        self.assertFalse((self.skills_dir / "bigquery-partitioning").exists())

        self.mgr.restore(category="Data Warehouse")
        self.assertTrue((self.skills_dir / "bigquery-partitioning" / "SKILL.md").exists())

    # --- 7. Search Tests ---

    def test_search_skills(self):
        """Test keyword searching in names, descriptions, and categories."""
        self._create_mock_skill(self.skills_dir, "alphafold-protein", "Analyzes 3D protein structures.")
        self.mgr.archive(name="alphafold-protein", category="Biomedical")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.mgr.search("protein")
            output = sys.stdout.getvalue()
            self.assertIn("alphafold-protein", output)
            self.assertIn("Biomedical", output)
        finally:
            sys.stdout = old_stdout

    # --- 8. Integrity Verification & Self-Healing Tests ---

    def test_integrity_audit_clean(self):
        """Test verify returns 0 when archive is in 100% sync."""
        self._create_mock_skill(self.skills_dir, "skill-a", "Skill A description.")
        self.mgr.archive(name="skill-a", category="Category A")

        ret = self.mgr.verify(fix=False)
        self.assertEqual(ret, 0)

    def test_integrity_audit_detection_and_self_healing(self):
        """Test verify detects discrepancies and --fix heals them."""
        self._create_mock_skill(self.skills_dir, "skill-valid", "Valid skill.")
        self.mgr.archive(name="skill-valid", category="Category Valid")

        manifest = self.mgr.load_manifest()
        manifest.append({
            "name": "phantom-skill",
            "category": "Ghost",
            "original_path": "skills/phantom-skill",
            "archived_path": "skill_archive/skills/phantom-skill"
        })
        self.mgr.save_manifest(manifest)

        unindexed = self.archive_dir / "skills" / "unindexed-skill"
        unindexed.mkdir(parents=True, exist_ok=True)
        (unindexed / "SKILL.md").write_text("---\nname: unindexed-skill\ndescription: Unindexed.\n---\n", encoding="utf-8")

        ret_fail = self.mgr.verify(fix=False)
        self.assertEqual(ret_fail, 1)

        ret_fix = self.mgr.verify(fix=True)
        self.assertEqual(ret_fix, 0)

        ret_clean = self.mgr.verify(fix=False)
        self.assertEqual(ret_clean, 0)

        final_manifest = self.mgr.load_manifest()
        names = [m["name"] for m in final_manifest]
        self.assertNotIn("phantom-skill", names)
        self.assertIn("unindexed-skill", names)
        self.assertIn("skill-valid", names)

    # --- 9. End-to-End CLI Invocation Test ---

    def test_cli_execution(self):
        """Test running skill_vault.py directly via subprocess CLI."""
        script_path = SCRIPT_DIR / "skill_vault.py"
        
        self._create_mock_skill(self.skills_dir, "cli-test-skill", "CLI test description.")

        # Archive via CLI
        res = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "archive", "cli-test-skill", "--category", "CLI Tests"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("[Archived]", res.stdout)

        # Optimize via CLI
        res_opt = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "optimize", "--dry-run"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_opt.returncode, 0)
        self.assertIn("SKILL VAULT AUTO-OPTIMIZATION", res_opt.stdout)

        # Verify via CLI
        res_verify = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "verify"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_verify.returncode, 0)
        self.assertIn("[OK] 100% Integrity Verified!", res_verify.stdout)

    # --- 10. Recency & Version Prioritization Tests ---

    def test_parse_version_tuple(self):
        """Test parsing diverse version formats into comparable tuples."""
        self.assertEqual(parse_version_tuple("v1"), (1,))
        self.assertEqual(parse_version_tuple("v20"), (20,))
        self.assertEqual(parse_version_tuple("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version_tuple("v0.9.1"), (0, 9, 1))
        self.assertIsNone(parse_version_tuple(""))
        self.assertIsNone(parse_version_tuple(None))
        self.assertIsNone(parse_version_tuple("unversioned"))

    def test_compare_skill_recency_version_and_mtime(self):
        """Test compare_skill_recency with semantic version and mtime fallback."""
        skill_a = self._create_mock_skill(self.skills_dir, "skill-a", version="v2")
        skill_b = self._create_mock_skill(self.archive_dir / "skills", "skill-b", version="v1")
        self.assertEqual(compare_skill_recency(skill_a, skill_b), 1)
        self.assertEqual(compare_skill_recency(skill_b, skill_a), -1)

        # Equal versions compare identical
        skill_c = self._create_mock_skill(self.skills_dir, "skill-c", version="v1")
        self.assertEqual(compare_skill_recency(skill_b, skill_c), 0)

    def test_archive_prioritizes_newer_version(self):
        """Test archiving overwrites older archive if active is newer, but preserves newer archive if active is older."""
        # 1. Active is newer (v2) than Archive (v1) -> Archive must be upgraded to v2
        self._create_mock_skill(self.skills_dir, "evolving-skill", version="v2")
        self._create_mock_skill(self.archive_dir / "skills", "evolving-skill", version="v1")
        manifest = [{
            "name": "evolving-skill",
            "category": "Testing",
            "original_path": "skills/evolving-skill",
            "archived_path": "skill_archive/skills/evolving-skill",
        }]
        self.mgr.save_manifest(manifest)

        self.mgr.archive(name="evolving-skill")
        archived_md = (self.archive_dir / "skills" / "evolving-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v2", archived_md)

        # 2. Active is older (v1) than Archive (v2) -> Archive must be preserved at v2, not overwritten
        self._create_mock_skill(self.skills_dir, "evolving-skill", version="v1")
        self.mgr.archive(name="evolving-skill")
        archived_md_after = (self.archive_dir / "skills" / "evolving-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v2", archived_md_after)

    def test_restore_prioritizes_newer_version(self):
        """Test restore updates active skill if archive is newer, but skips if active is already newer."""
        # 1. Archive is newer (v2) than Active (v1) -> Active must be updated to v2
        self._create_mock_skill(self.skills_dir, "restorable-skill", version="v1")
        self._create_mock_skill(self.archive_dir / "skills", "restorable-skill", version="v2")
        manifest = [{
            "name": "restorable-skill",
            "category": "Testing",
            "original_path": "skills/restorable-skill",
            "archived_path": "skill_archive/skills/restorable-skill",
        }]
        self.mgr.save_manifest(manifest)

        self.mgr.restore(name="restorable-skill")
        active_md = (self.skills_dir / "restorable-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v2", active_md)

        # 2. Active is newer (v3) than Archive (v2) -> Active must remain at v3
        (self.skills_dir / "restorable-skill" / "SKILL.md").write_text("---\nname: restorable-skill\nversion: v3\ndescription: Test.\n---\n", encoding="utf-8")
        self.mgr.restore(name="restorable-skill")
        active_md_preserved = (self.skills_dir / "restorable-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v3", active_md_preserved)

    def test_force_overwrites_regardless_of_recency(self):
        """Test --force flag forces overwrite even when target is newer."""
        self._create_mock_skill(self.skills_dir, "forced-skill", version="v1")
        self._create_mock_skill(self.archive_dir / "skills", "forced-skill", version="v2")
        manifest = [{
            "name": "forced-skill",
            "category": "Testing",
            "original_path": "skills/forced-skill",
            "archived_path": "skill_archive/skills/forced-skill",
        }]
        self.mgr.save_manifest(manifest)

        # Forcing archive of older v1 over newer v2
        self.mgr.archive(name="forced-skill", force=True)
        archived_md = (self.archive_dir / "skills" / "forced-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: v1", archived_md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
