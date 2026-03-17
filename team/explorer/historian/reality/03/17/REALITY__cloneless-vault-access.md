# Reality Document — Cloneless Vault Access

**Date:** 17 March 2026
**Version:** post-session (claude/start-explorer-session-aNXhe)
**Status:** Implemented and tested

---

## What Was Built This Session

### Vault__Remote — Stateless Cloneless Vault Access

**File:** `sg_send_cli/sync/Vault__Remote.py`

Implemented the `Vault__Remote` class — a stateless class that reads vault files
directly from the SG/Send API without creating any local `.sg_vault` directory.

**Public API:**

| Method | Description | API Cost |
|--------|-------------|----------|
| `list_files(vault_key)` | List all files with sizes | ~5 calls |
| `read_file(vault_key, path)` | Download + decrypt one file by path | ~6 calls |
| `read_file_by_id(vault_key, blob_id)` | Download + decrypt by blob ID | ~1 call |
| `save_file(vault_key, path, dest)` | Read + write to local file | ~6 calls |
| `get_tree(vault_key)` | Return decrypted tree object | ~5 calls |
| `get_info(vault_key)` | Return vault summary (id, count, size) | ~5 calls |

**API call chain for list/read:**
1. `list_files(vault_id, 'bare/indexes/')` → find branch index file
2. `read(vault_id, 'bare/indexes/idx-{hex}')` → decrypt → `Schema__Branch_Index`
3. Find named branch "current" → `head_ref_id`
4. `read(vault_id, 'bare/refs/{ref_id}')` → decrypt → commit_id
5. `read(vault_id, 'bare/data/{commit_id}')` → decrypt → `Schema__Object_Commit`
6. `read(vault_id, 'bare/data/{tree_id}')` → decrypt → `Schema__Object_Tree`
7. (for read_file) `read(vault_id, 'bare/data/{blob_id}')` → decrypt → file bytes

**No local state:** All operations are stateless — no `.sg_vault` directory is
created or modified.

### CLI Commands Added

Four new cloneless commands added to `CLI__Vault` + registered in `CLI__Main`:

| Command | Usage | Description |
|---------|-------|-------------|
| `ls` | `sg-send-cli ls <vault_key>` | List files with sizes (no clone) |
| `cat` | `sg-send-cli cat <vault_key> <path>` | Print file to stdout (binary-safe) |
| `get` | `sg-send-cli get <vault_key> <path> [dest]` | Download one file |
| `info` | `sg-send-cli info <vault_key>` | Show vault ID, file count, total size |

### Test Coverage

| Test File | Tests | Focus |
|-----------|-------|-------|
| `tests/unit/sync/test_Vault__Remote.py` | 22 | list_files, read_file, read_file_by_id, save_file, get_tree, get_info, round-trips, no local state |
| `tests/unit/cli/test_CLI__Remote_Commands.py` | 18 | CLI commands, parser registration, format_size helper |

---

## Overall Test Count

**1015 unit tests — all passing** (up from 975 before this session, +40 new tests)

---

## What Still Needs To Be Done

### MEDIUM — Remaining Phase E/F items

1. **Zip backend** (`Vault__Backend__Zip`) — Portable vault export/import as zip
2. **Vault export as zip** — CLI snapshot command
3. **Wire backends into sync workflow** — push/pull using `Vault__Backend` abstraction

### LOW — Polish / deferred

4. **Health check records** (Phase F.5)
5. **Scoped write-only tokens** (Phase F.2) — server-side concern
6. **`Vault__Remote` write support** — `write_file`, `delete_file` (future Phase 4)

---

## Architecture Notes

`Vault__Remote` avoids the heavyweight `Vault__Commit`/`Vault__Object_Store`
objects by reading from the API directly and inlining the `decrypt_tree_entry_fields`
logic as `_decrypt_entry_fields`. This keeps the class stateless and dependency-light.

The cloneless read path is ~6 API calls vs ~N+5 calls for full clone (where N is
the number of files). For a 25-file vault, cloneless access is ~4x faster for
reading a single file.
