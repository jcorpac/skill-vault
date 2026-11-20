#!/usr/bin/env python3
"""Skill Vault Read-Only MCP Stdio Server.

Provides three read-only fallback tools (`search_skills`, `list_skills`, `load_skill`) over
JSON-RPC 2.0 (supporting both newline-delimited JSON and Content-Length framing) so coding
agents can discover and inspect cold-storage skills mid-turn without shell approvals or L1 mutations.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import skill_router  # noqa: E402

SERVER_NAME = "skill-vault"
SERVER_VERSION = "2.0.0"
MAX_READ_BYTES = 102400  # 100 KB safety cap per tool call

TOOLS_SPEC = [
    {
        "name": "search_skills",
        "description": (
            "Search vaulted cold-storage skills by keyword, intent, or category. "
            "Pass an empty query to list categories and counts, or use list_skills to list all skill names in one call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords or task intent (or empty string to list categories).",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category name filter.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 8, max 25).",
                    "default": 8,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset into sorted results (default 0).",
                    "default": 0,
                },
            },
            "required": ["query"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "list_skills",
        "description": (
            "List all vaulted cold-storage skill names grouped by category in a single compact call "
            "(no 25-item limit). Optionally filter by category or include short 1-line descriptions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category name filter (case-insensitive).",
                },
                "include_descriptions": {
                    "type": "boolean",
                    "description": (
                        "Include truncated 1-line descriptions per skill "
                        "(default false for compact names-only output)."
                    ),
                    "default": False,
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load the full SKILL.md instructions for a vaulted skill, or read a specific "
            "companion file (e.g. 'references/guide.md') inside that skill's directory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact skill name from search_skills or pointer context.",
                },
                "file": {
                    "type": "string",
                    "description": "Optional relative path to a companion file inside the skill folder.",
                },
            },
            "required": ["name"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]


def _debug(msg):
    if os.environ.get("SKILL_VAULT_MCP_DEBUG") == "1":
        sys.stderr.write(f"[skill-vault-mcp] {msg}\n")
        sys.stderr.flush()


def _resolve_base_and_archive(cli_base=None):
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

    vault_link = SCRIPT_DIR.parent / "vault_link.json"
    if vault_link.exists():
        try:
            link_data = json.loads(vault_link.read_text(encoding="utf-8"))
            if isinstance(link_data, dict) and link_data.get("baseDir"):
                candidates.append(Path(link_data["baseDir"]).resolve())
        except Exception:
            pass

    for parent in Path(__file__).resolve().parents:
        if parent.name != "skill_archive" and (parent / "skill_archive").exists():
            candidates.append(parent)

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

    for cand in candidates:
        if cand.exists():
            return cand, cand / "skill_archive"

    fallback = home / ".gemini" / "config"
    return fallback, fallback / "skill_archive"


_INDEX_CACHE = {}


def _file_sig(path):
    try:
        st = Path(path).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def clear_index_cache():
    """Clear the in-memory search index cache."""
    _INDEX_CACHE.clear()


def _load_index(base_dir, archive_dir):
    archive_path = Path(archive_dir).resolve()
    cache_key = str(archive_path)
    if not archive_path.exists():
        _INDEX_CACHE.pop(cache_key, None)
        return {"doc_count": 0, "skills": [], "df": {}, "avg_len": {}}

    index_sig = _file_sig(archive_path / "search_index.json")
    manifest_sig = _file_sig(archive_path / "backup_manifest.json")
    cached = _INDEX_CACHE.get(cache_key)
    if cached is not None and cached[0] == index_sig and cached[1] == manifest_sig:
        return cached[2]

    data = skill_router.load_or_build_index(archive_dir=archive_path, base_dir=base_dir)
    new_index_sig = _file_sig(archive_path / "search_index.json")
    new_manifest_sig = _file_sig(archive_path / "backup_manifest.json")
    _INDEX_CACHE[cache_key] = (new_index_sig, new_manifest_sig, data)
    return data


def _tool_result(text, is_error=False):
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _short_desc(text, max_len=160):
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3].rstrip() + "..."


def _handle_list_skills(args, base_dir, archive_dir):
    category = args.get("category")
    if category is not None:
        category = str(category).strip() or None

    raw_inc = args.get("include_descriptions", False)
    if isinstance(raw_inc, bool):
        include_descriptions = raw_inc
    elif isinstance(raw_inc, str):
        include_descriptions = raw_inc.strip().lower() in ("true", "1", "yes")
    else:
        include_descriptions = bool(raw_inc)

    index_data = _load_index(base_dir, archive_dir)
    skills = index_data.get("skills", [])

    grouped = {}
    for entry in skills:
        cat = entry.get("category") or "General & Utility Skills"
        grouped.setdefault(cat, []).append(entry)

    all_categories = sorted(grouped.keys(), key=str.lower)

    if category:
        cat_lower = category.lower()
        filtered_items = [
            (cat, items) for cat, items in grouped.items() if cat.lower() == cat_lower
        ]
    else:
        filtered_items = list(grouped.items())

    filtered_items.sort(key=lambda kv: (-len(kv[1]), kv[0].lower()))

    cat_blocks = []
    total_matching = 0
    for cat, items in filtered_items:
        sorted_entries = sorted(items, key=lambda s: s.get("name", "").lower())
        total_matching += len(sorted_entries)
        if include_descriptions:
            skill_list = [
                {
                    "name": s["name"],
                    "description": _short_desc(s.get("description", "")),
                }
                for s in sorted_entries
            ]
        else:
            skill_list = [s["name"] for s in sorted_entries]
        cat_blocks.append({
            "category": cat,
            "count": len(sorted_entries),
            "skills": skill_list,
        })

    payload = {
        "total_skills": total_matching,
        "category_count": len(cat_blocks),
        "categories": cat_blocks,
    }
    if category and total_matching == 0:
        payload["available_categories"] = all_categories

    return _tool_result(json.dumps(payload, indent=2, ensure_ascii=False))


def _handle_search_skills(args, base_dir, archive_dir):
    query = str(args.get("query") or "")
    category = args.get("category")
    if category is not None:
        category = str(category).strip() or None
    try:
        limit = int(args.get("limit", 8))
    except (TypeError, ValueError):
        limit = 8
    limit = max(1, min(limit, 25))
    try:
        offset = max(0, int(args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    index_data = _load_index(base_dir, archive_dir)
    skills = index_data.get("skills", [])

    if not query.strip() and not category:
        cats = {}
        for s in skills:
            c = s.get("category", "General & Utility Skills")
            cats[c] = cats.get(c, 0) + 1
        summary = {
            "total_skills": len(skills),
            "categories": [
                {"category": k, "count": v}
                for k, v in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0].lower()))
            ],
        }
        return _tool_result(json.dumps(summary, indent=2, ensure_ascii=False))

    all_matches = skill_router.search_index(
        index_data=index_data,
        query=query,
        category=category,
        limit=None,
    )

    # Substring fallback for partial fragments (e.g., "proto") if BM25 returned nothing
    if not all_matches and query.strip():
        q_lower = query.strip().lower()
        word_pat = re.compile(rf"(?<![a-z0-9]){re.escape(q_lower)}(?![a-z0-9])")
        fallback = []
        for entry in skills:
            entry_cat = entry.get("category", "General & Utility Skills")
            if category and entry_cat.lower() != category.lower():
                continue
            name_l = entry.get("name", "").lower()
            aliases_l = [a.lower() for a in entry.get("aliases", [entry.get("name", "")])]
            desc_l = entry.get("description", "").lower()
            cat_l = entry_cat.lower()

            if q_lower == name_l or q_lower in aliases_l:
                score = 10.0
            elif q_lower in name_l or any(q_lower in a for a in aliases_l):
                score = 5.0
            elif word_pat.search(desc_l):
                score = 2.0
            elif q_lower in desc_l or q_lower in cat_l:
                score = 1.0
            else:
                continue

            fallback.append({
                "name": entry["name"],
                "category": entry_cat,
                "score": score,
                "description": entry.get("description", ""),
                "companion_files": entry.get("companion_files", []),
            })
        fallback.sort(key=lambda m: (-m["score"], m["name"].lower()))
        all_matches = fallback

    total_matches = len(all_matches)
    matches = all_matches[offset : offset + limit]

    payload = {
        "query": query,
        "total_matches": total_matches,
        "offset": offset,
        "count": len(matches),
        "results": [
            {
                "name": m["name"],
                "category": m["category"],
                "score": m["score"],
                "description": m["description"],
                "companion_files": m.get("companion_files", []),
            }
            for m in matches
        ],
    }
    return _tool_result(json.dumps(payload, indent=2, ensure_ascii=False))


def _find_skill_entry(index_data, skill_name):
    target_canon = skill_router.canonicalize_skill_name(skill_name)
    raw_lower = str(skill_name or "").strip().lower()
    for entry in index_data.get("skills", []):
        if entry.get("name", "").lower() == raw_lower:
            return entry
        if entry.get("canonical_key") == target_canon:
            return entry
        for alias in entry.get("aliases", []):
            if alias.lower() == raw_lower:
                return entry
    return None


def _handle_load_skill(args, base_dir, archive_dir):
    skill_name = str(args.get("name") or "").strip()
    if not skill_name:
        return _tool_result("Error: 'name' parameter is required.", is_error=True)

    rel_file = args.get("file")
    if rel_file is not None:
        rel_file = str(rel_file).strip() or None

    index_data = _load_index(base_dir, archive_dir)
    entry = _find_skill_entry(index_data, skill_name)
    if not entry:
        return _tool_result(
            f"Skill '{skill_name}' was not found in the Skill Vault archive. "
            "Call search_skills to discover exact skill names.",
            is_error=True,
        )

    skill_dir = None
    if entry.get("resolved_path") and Path(entry["resolved_path"]).exists():
        skill_dir = Path(entry["resolved_path"]).resolve()
    elif entry.get("archived_path"):
        cand = skill_router._resolve_archived_skill_dir(base_dir, archive_dir, entry["archived_path"])
        if cand.exists():
            skill_dir = cand.resolve()

    if not skill_dir or not skill_dir.exists():
        return _tool_result(
            f"Error: Archived directory for skill '{skill_name}' does not exist on disk.",
            is_error=True,
        )

    if rel_file:
        # Strict path traversal check: target must reside inside skill_dir
        try:
            req_path = Path(rel_file)
            if req_path.is_absolute():
                return _tool_result(
                    "Error: Absolute paths are not allowed; provide a relative path inside the skill directory.",
                    is_error=True,
                )
            target = (skill_dir / req_path).resolve()
            if skill_dir not in target.parents:
                return _tool_result(
                    "Error: Path traversal denied; companion file must reside inside the skill directory.",
                    is_error=True,
                )
        except Exception as exc:
            return _tool_result(f"Error resolving path: {exc}", is_error=True)

        if not target.exists() or not target.is_file():
            return _tool_result(
                f"Error: Companion file '{rel_file}' not found inside '{entry['name']}'.",
                is_error=True,
            )

        raw = target.read_bytes()
        truncated = len(raw) > MAX_READ_BYTES
        text = raw[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        if truncated:
            text += f"\n\n[... truncated at {MAX_READ_BYTES} bytes ...]"
        header = f"# {entry['name']} :: {rel_file}\n\n"
        return _tool_result(header + text)

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return _tool_result(
            f"Error: SKILL.md missing for skill '{entry['name']}'.",
            is_error=True,
        )

    raw = skill_md.read_bytes()
    truncated = len(raw) > MAX_READ_BYTES
    content = raw[:MAX_READ_BYTES].decode("utf-8", errors="replace")
    if truncated:
        content += f"\n\n[... truncated at {MAX_READ_BYTES} bytes ...]"

    companions = entry.get("companion_files", [])
    comp_line = ", ".join(companions) if companions else "(none)"
    header = (
        f"Skill: {entry['name']}\n"
        f"Category: {entry.get('category', 'General & Utility Skills')}\n"
        f"Directory: {skill_dir}\n"
        f"Companion Files: {comp_line}\n"
        f"---\n"
    )
    return _tool_result(header + content)


def _read_rpc_message(stdin_buf):
    """Read one JSON-RPC message supporting both newline-delimited JSON and Content-Length framing."""
    while True:
        line = stdin_buf.readline()
        if not line:
            return None, None
        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()
        if lower.startswith(b"content-length:"):
            try:
                content_length = int(stripped.split(b":", 1)[1].strip())
            except ValueError:
                return None, "content_length"
            # Consume remaining headers up to blank line
            while True:
                hdr = stdin_buf.readline()
                if not hdr or hdr.strip() == b"":
                    break
            body = stdin_buf.read(content_length)
            if not body:
                return None, "content_length"
            return json.loads(body.decode("utf-8", errors="replace")), "content_length"

        return json.loads(stripped.decode("utf-8", errors="replace")), "newline"


def _write_rpc_message(stdout_buf, payload, framing):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "content_length":
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        stdout_buf.write(header + body)
    else:
        stdout_buf.write(body + b"\n")
    stdout_buf.flush()


def _dispatch_request(msg, base_dir, archive_dir):
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    # Notifications have no id (or id is None) and expect no response
    if msg_id is None:
        return None

    if method == "initialize":
        proto_ver = params.get("protocolVersion") or "2024-11-05"
        result = {
            "protocolVersion": proto_ver,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS_SPEC}}

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        if tool_name == "search_skills":
            res = _handle_search_skills(args, base_dir, archive_dir)
        elif tool_name == "list_skills":
            res = _handle_list_skills(args, base_dir, archive_dir)
        elif tool_name == "load_skill":
            res = _handle_load_skill(args, base_dir, archive_dir)
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": res}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    parser = argparse.ArgumentParser(description="Skill Vault Read-Only MCP Stdio Server")
    parser.add_argument("--base-dir", help="Explicit Skill Vault base directory")
    args, _ = parser.parse_known_args()

    base_dir, archive_dir = _resolve_base_and_archive(args.base_dir)
    _debug(f"Started MCP server with base_dir={base_dir}, archive_dir={archive_dir}")

    stdin_buf = sys.stdin.buffer
    stdout_buf = sys.stdout.buffer
    detected_framing = "newline"

    while True:
        try:
            msg, framing = _read_rpc_message(stdin_buf)
        except Exception as exc:
            _debug(f"Parse error: {exc}")
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            _write_rpc_message(stdout_buf, err_resp, detected_framing)
            continue

        if msg is None:
            break
        if framing:
            detected_framing = framing

        try:
            resp = _dispatch_request(msg, base_dir, archive_dir)
        except Exception as exc:
            _debug(f"Internal error: {exc}")
            msg_id = msg.get("id") if isinstance(msg, dict) else None
            if msg_id is None:
                continue
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            }

        if resp is not None:
            _write_rpc_message(stdout_buf, resp, detected_framing)


if __name__ == "__main__":
    main()
