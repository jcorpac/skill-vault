#!/usr/bin/env python3
"""Skill Vault Background Hook Runner (Antigravity, Claude Code, Gemini CLI).

Executes silently at SessionStart and PreInvocation / UserPromptSubmit / BeforeAgent
to maintain the L2 archive index and inject relevant skills just-in-time with zero
user approvals. Strictly fails safe (always exits 0 with valid JSON on stdout).
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import skill_router  # noqa: E402


def _configure_stdio():
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _resolve_base_and_archive(cli_base=None, workspace_paths=None):
    """Resolve Skill Vault base_dir and archive_dir without heavy imports."""
    if cli_base:
        p = Path(cli_base).resolve()
        return p, p / "skill_archive"

    for env_key in ("SKILL_VAULT_BASE", "SKILL_BASE_DIR", "AGENTS_HOME"):
        val = os.environ.get(env_key)
        if val:
            p = Path(val).resolve()
            return p, p / "skill_archive"

    candidates = []

    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        candidates.append(Path(plugin_data).resolve())

    # Installed plugin link file written by `skill-vault setup`
    vault_link = SCRIPT_DIR.parent / "vault_link.json"
    if vault_link.exists():
        try:
            link_data = json.loads(vault_link.read_text(encoding="utf-8"))
            if isinstance(link_data, dict) and link_data.get("baseDir"):
                candidates.append(Path(link_data["baseDir"]).resolve())
        except Exception:
            pass

    # Check script ancestors (e.g. ~/.gemini/config/plugins/skill-vault/scripts/hook_runner.py -> ~/.gemini/config)
    for parent in Path(__file__).resolve().parents:
        if parent.name != "skill_archive" and (parent / "skill_archive").exists():
            candidates.append(parent)

    # Check workspace roots for workspace-scoped archives
    for ws in workspace_paths or []:
        if not ws:
            continue
        wsp = Path(ws).resolve()
        for sub in (wsp / ".agents", wsp, wsp / ".claude", wsp / ".gemini", wsp / ".cursor"):
            if (sub / "skill_archive").exists():
                candidates.append(sub)

    home = Path.home()
    candidates.extend([
        home / ".gemini" / "config",
        home / ".gemini" / "config" / "skills" / "skill-vault",
        home / ".agents",
        home / ".claude",
        home / ".gemini",
        home / ".cursor",
    ])

    for cand in candidates:
        arch = cand / "skill_archive"
        if arch.exists() and (
            (arch / "backup_manifest.json").exists()
            or (arch / "search_index.json").exists()
            or (arch / "skills").exists()
        ):
            return cand, arch

    # Fallback to first valid candidate or ~/.gemini/config
    for cand in candidates:
        if cand.exists():
            return cand, cand / "skill_archive"

    fallback = home / ".gemini" / "config"
    return fallback, fallback / "skill_archive"


def _load_routing_config(archive_dir):
    """Read routing settings from vault_config.json merged with defaults."""
    cfg = dict(skill_router.DEFAULT_ROUTING_CONFIG)
    cfg_file = Path(archive_dir) / "vault_config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("routing"), dict):
                cfg.update(data["routing"])
        except Exception:
            pass
    return cfg


def _detect_harness(requested_harness, payload, cli_event):
    if requested_harness and requested_harness != "auto":
        return requested_harness

    antigravity_events = {
        "SessionStart", "PreInvocation", "PostInvocation",
        "PreToolUse", "PostToolUse", "Stop",
    }
    if payload.get("hookEventName") in antigravity_events:
        return "antigravity"
    if any(k in payload for k in ("lastUserInput", "conversationId", "workspacePaths", "invocationNum")):
        return "antigravity"
    if cli_event == "PreInvocation":
        return "antigravity"

    hook_evt = payload.get("hook_event_name") or cli_event or ""
    if hook_evt == "BeforeAgent":
        return "gemini-cli"
    if hook_evt == "UserPromptSubmit" or ("session_id" in payload and "prompt" in payload):
        return "claude"

    return "antigravity"


def _detect_event(cli_event, payload):
    if cli_event:
        return cli_event
    return payload.get("hookEventName") or payload.get("hook_event_name") or "PreInvocation"


def _fast_active_skill_names(base_dir, workspace_paths=None):
    """Quickly collect active L1 skill folder names without reading SKILL.md files."""
    names = set()
    roots = [Path(base_dir)]
    for ws in workspace_paths or []:
        if ws:
            wsp = Path(ws).resolve()
            if wsp not in roots:
                roots.append(wsp)

    for root in roots:
        for sub in ("skills", ".agents/skills", ".claude/skills"):
            sdir = root / sub
            if sdir.exists() and sdir.is_dir():
                try:
                    for item in sdir.iterdir():
                        if item.is_dir() and (item / "SKILL.md").exists():
                            names.add(item.name)
                except OSError:
                    pass
        plugins_dir = root / "plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            try:
                for plug in plugins_dir.iterdir():
                    pskills = plug / "skills"
                    if pskills.exists() and pskills.is_dir():
                        for item in pskills.iterdir():
                            if item.is_dir() and (item / "SKILL.md").exists():
                                names.add(item.name)
            except OSError:
                pass
    return names


def _collect_skill_dirs_snapshot(mgr):
    """Build lightweight mtime snapshot across active and plugin skill directories."""
    snapshot = {}
    hook_protected = set()
    if hasattr(mgr, "get_hook_protected_skills"):
        try:
            hook_protected = mgr.get_hook_protected_skills()
        except Exception:
            hook_protected = set()

    for sdir in mgr.get_active_skill_dirs():
        sdir_path = Path(sdir)
        if not sdir_path.exists():
            continue
        try:
            if (sdir_path / "SKILL.md").exists():
                snapshot[str(sdir_path / "SKILL.md")] = round((sdir_path / "SKILL.md").stat().st_mtime, 2)
            for item in sdir_path.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    if item.name == "skill-vault" or item.name in hook_protected:
                        continue
                    snapshot[str(item)] = round((item / "SKILL.md").stat().st_mtime, 2)
        except OSError:
            pass
    return snapshot


def _handle_session_start(base_dir, archive_dir, payload, routing_cfg):
    """Run silent background index check, optional plugin sync, and workspace cache warmup."""
    if not routing_cfg.get("enabled", True):
        return {}

    workspace_paths = payload.get("workspacePaths") or ([payload["cwd"]] if payload.get("cwd") else [])

    # Prune old conversation state files
    if archive_dir.exists():
        skill_router.prune_old_states(archive_dir, max_age_days=7)

    # Import SkillVault only inside SessionStart for sync + workspace fingerprinting
    from skill_vault import SkillVault  # noqa: E402

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        mgr = SkillVault(base_dir=str(base_dir))
        auto_sync = bool(routing_cfg.get("auto_sync_on_session_start", True))
        auto_prune = bool(routing_cfg.get("auto_prune_on_session_start", True))

        if auto_sync and archive_dir.exists():
            state_dir = archive_dir / ".state"
            state_dir.mkdir(parents=True, exist_ok=True)
            stamp_file = state_dir / "sync_stamp.json"

            current_snap = _collect_skill_dirs_snapshot(mgr)
            prev_snap = None
            if stamp_file.exists():
                try:
                    prev_snap = json.loads(stamp_file.read_text(encoding="utf-8"))
                except Exception:
                    prev_snap = None

            if current_snap != prev_snap:
                mgr.sync(keep_active=not auto_prune)
                post_snap = _collect_skill_dirs_snapshot(mgr)
                skill_router._atomic_write_json(stamp_file, post_snap)

        # Ensure search_index.json exists & is up-to-date
        if archive_dir.exists():
            skill_router.load_or_build_index(
                archive_dir=archive_dir,
                base_dir=mgr.base_dir,
                resolve_path_fn=mgr.resolve_portable_path,
            )

        # Warm workspace fingerprint cache
        if workspace_paths and archive_dir.exists():
            ws_cats = set()
            for wsp in workspace_paths:
                if wsp and Path(wsp).exists():
                    ws_cats.update(mgr.detect_workspace_categories(wsp).keys())
            skill_router.cache_workspace_categories(archive_dir, workspace_paths, sorted(ws_cats))

    return {}


def _handle_prompt_hook(base_dir, archive_dir, payload, harness, event_name, routing_cfg, start_time):
    """Route user prompt against L2 index and emit harness-native injection JSON."""
    if not routing_cfg.get("enabled", True):
        return {}

    if not archive_dir.exists():
        return {}

    prompt = payload.get("lastUserInput") or payload.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt.strip():
        return {}

    conversation_id = payload.get("conversationId") or payload.get("session_id") or "default"
    workspace_paths = payload.get("workspacePaths") or ([payload["cwd"]] if payload.get("cwd") else [])
    invocation_num = payload.get("invocationNum")
    initial_num_steps = payload.get("initialNumSteps")

    conv_state = skill_router.ConversationState(archive_dir, conversation_id)
    input_hash = hashlib.sha256(prompt.strip().encode("utf-8", errors="ignore")).hexdigest()[:16]

    if conv_state.should_short_circuit(input_hash, invocation_num=invocation_num, initial_num_steps=initial_num_steps):
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        skill_router.log_routing_event(
            archive_dir,
            {
                "ts": round(time.time(), 3),
                "event": event_name,
                "harness": harness,
                "latency_ms": latency_ms,
                "matched_inline": [],
                "matched_pointers": [],
                "estimated_tokens": 0,
                "short_circuited": True,
            },
        )
        return {}

    # Fast zero-token early exit before loading search_index.json or workspace cache
    if not skill_router.tokenize(prompt, include_stems=False):
        conv_state.record_turn(
            input_hash=input_hash,
            initial_num_steps=initial_num_steps,
            inline_keys=[],
            pointer_keys=[],
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        skill_router.log_routing_event(
            archive_dir,
            {
                "ts": round(time.time(), 3),
                "event": event_name,
                "harness": harness,
                "latency_ms": latency_ms,
                "matched_inline": [],
                "matched_pointers": [],
                "estimated_tokens": 0,
                "short_circuited": False,
            },
        )
        return {}

    # Load pre-built search index (fast path <5ms)
    index_data = skill_router.load_or_build_index(archive_dir=archive_dir, base_dir=base_dir)
    if not index_data.get("skills"):
        return {}

    # Cached workspace stack categories (compute once if cache miss)
    ws_cats = skill_router.get_cached_workspace_categories(archive_dir, workspace_paths)
    if ws_cats is None and workspace_paths:
        ws_cats_set = set()
        try:
            from skill_vault import SkillVault  # noqa: E402

            sink = io.StringIO()
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                mgr = SkillVault(base_dir=str(base_dir))
                for wsp in workspace_paths:
                    if wsp and Path(wsp).exists():
                        ws_cats_set.update(mgr.detect_workspace_categories(wsp).keys())
            ws_cats = sorted(ws_cats_set)
            skill_router.cache_workspace_categories(archive_dir, workspace_paths, ws_cats)
        except Exception:
            ws_cats = []

    active_names = _fast_active_skill_names(base_dir, workspace_paths)
    exclude_names = active_names | conv_state.get_excluded_skills()

    result = skill_router.route_prompt(
        index_data=index_data,
        prompt=prompt,
        archive_dir=archive_dir,
        base_dir=base_dir,
        workspace_categories=ws_cats,
        exclude_names=exclude_names,
        routing_config=routing_cfg,
    )

    inline_keys = [item["canonical_key"] for item in result["inline"]]
    pointer_keys = [item["canonical_key"] for item in result["pointers"]]
    conv_state.record_turn(
        input_hash=input_hash,
        initial_num_steps=initial_num_steps,
        inline_keys=inline_keys,
        pointer_keys=pointer_keys,
    )

    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    skill_router.log_routing_event(
        archive_dir,
        {
            "ts": round(time.time(), 3),
            "event": event_name,
            "harness": harness,
            "latency_ms": latency_ms,
            "matched_inline": [i["name"] for i in result["inline"]],
            "matched_pointers": [p["name"] for p in result["pointers"]],
            "estimated_tokens": result["estimated_tokens"],
            "short_circuited": False,
        },
    )

    injection_text = result.get("injection_text", "")
    if not injection_text:
        return {}

    if harness == "antigravity":
        metadata = {}
        if routing_cfg.get("show_ui_notice") and result.get("ui_notice"):
            metadata["user_markdown"] = result["ui_notice"]
        return {
            "injectSteps": [
                {
                    "systemMessage": {
                        "systemMessage": injection_text,
                        "metadata": metadata,
                    }
                }
            ]
        }

    hook_evt = "BeforeAgent" if harness == "gemini-cli" else "UserPromptSubmit"
    return {
        "hookSpecificOutput": {
            "hookEventName": hook_evt,
            "additionalContext": injection_text,
        }
    }


def _record_hook_error(archive_dir, err):
    try:
        if archive_dir and Path(archive_dir).exists():
            state_dir = Path(archive_dir) / ".state"
            state_dir.mkdir(parents=True, exist_ok=True)
            log_path = state_dir / "hook_errors.log"
            with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {type(err).__name__}: {err}\n")
    except Exception:
        pass


def main():
    _configure_stdio()
    start_time = time.perf_counter()

    parser = argparse.ArgumentParser(description="Skill Vault Lifecycle Hook Runner")
    parser.add_argument("--event", help="Hook event name override")
    parser.add_argument(
        "--harness",
        choices=["auto", "antigravity", "claude", "gemini-cli"],
        default="auto",
        help="Target agent harness format",
    )
    parser.add_argument("--base-dir", help="Explicit Skill Vault base directory")
    args, _ = parser.parse_known_args()

    archive_dir = None
    try:
        raw_stdin = ""
        if sys.stdin is not None:
            raw_stdin = sys.stdin.read()
        payload = json.loads(raw_stdin) if raw_stdin and raw_stdin.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        ws_paths = payload.get("workspacePaths") or ([payload["cwd"]] if payload.get("cwd") else [])
        base_dir, archive_dir = _resolve_base_and_archive(args.base_dir, workspace_paths=ws_paths)
        routing_cfg = _load_routing_config(archive_dir)

        event_name = _detect_event(args.event, payload)
        harness = _detect_harness(args.harness, payload, event_name)

        if event_name == "SessionStart":
            out = _handle_session_start(base_dir, archive_dir, payload, routing_cfg)
        elif event_name in ("PreInvocation", "UserPromptSubmit", "BeforeAgent"):
            out = _handle_prompt_hook(
                base_dir=base_dir,
                archive_dir=archive_dir,
                payload=payload,
                harness=harness,
                event_name=event_name,
                routing_cfg=routing_cfg,
                start_time=start_time,
            )
        else:
            out = {}

        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception as exc:
        _record_hook_error(archive_dir, exc)
        sys.stdout.write("{}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
