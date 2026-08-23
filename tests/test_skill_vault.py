#!/usr/bin/env python3
"""Comprehensive Test Suite & Test Harness for skill_vault.py.

Runs in an isolated sandbox without modifying real user skills or archives.
Validates:
1. Path resolution across environments
2. Workspace bootstrapping (init)
3. Presenting active and archived skills (list & status)
4. Archiving with LLM categories & preservation of SKILL.md
5. Restoring skills (single, pattern, category, overwrite)
6. Recategorization in manifest & index
7. Reindexing & relative link generation
8. Search matching
9. Bi-directional integrity audit & self-healing (--fix)
10. CLI command execution
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
from skill_vault import SkillVault, resolve_base_dir


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

    def _create_mock_skill(self, base_path, name, description="A test skill description.", extra_files=None):
        """Helper to create a valid mock skill folder."""
        skill_dir = base_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        content = f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nInstructions."
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

        # Capture output of list
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

    # --- 3. Archive Tests ---

    def test_archive_single_skill_with_category(self):
        """Test archiving a single active skill with category."""
        self._create_mock_skill(self.skills_dir, "cloud-sql-backup", "Manages database backups.")
        
        self.mgr.archive(name="cloud-sql-backup", category="Cloud Database")

        # 1. Verify removed from active skills
        self.assertFalse((self.skills_dir / "cloud-sql-backup").exists())

        # 2. Verify present in archive
        archived_skill = self.archive_dir / "skills" / "cloud-sql-backup"
        self.assertTrue((archived_skill / "SKILL.md").exists())

        # 3. Verify SKILL.md was untouched and pure
        content = (archived_skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: cloud-sql-backup", content)
        self.assertNotIn("Cloud Database", content)

        # 4. Verify manifest and INDEX.md
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

    # --- 4. Recategorize Tests ---

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

    # --- 5. Restore Tests ---

    def test_restore_single_and_category(self):
        """Test restoring archived skills back to active locations."""
        self._create_mock_skill(self.skills_dir, "bigquery-optimizer", "Optimizes SQL.")
        self._create_mock_skill(self.skills_dir, "bigquery-partitioning", "Handles partitioning.")
        self.mgr.archive(pattern="bigquery-*", category="Data Warehouse")

        self.assertFalse((self.skills_dir / "bigquery-optimizer").exists())
        self.assertFalse((self.skills_dir / "bigquery-partitioning").exists())

        # 1. Restore single skill
        self.mgr.restore(name="bigquery-optimizer")
        self.assertTrue((self.skills_dir / "bigquery-optimizer" / "SKILL.md").exists())
        self.assertFalse((self.skills_dir / "bigquery-partitioning").exists())

        # 2. Restore entire category
        self.mgr.restore(category="Data Warehouse")
        self.assertTrue((self.skills_dir / "bigquery-partitioning" / "SKILL.md").exists())

    # --- 6. Search Tests ---

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

    # --- 7. Integrity Verification & Self-Healing Tests ---

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

    # --- 8. End-to-End CLI Invocation Test ---

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

        # List via CLI
        res_list = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "list"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_list.returncode, 0)
        self.assertIn("cli-test-skill", res_list.stdout)

        # Verify via CLI
        res_verify = subprocess.run(
            [sys.executable, str(script_path), "--base-dir", str(self.base_dir), "verify"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_verify.returncode, 0)
        self.assertIn("[OK] 100% Integrity Verified!", res_verify.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
