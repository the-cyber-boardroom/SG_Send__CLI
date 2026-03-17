import base64
import json
import os

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sg_send_cli.api.Vault__API                    import Vault__API
from sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from sg_send_cli.schemas.Schema__Branch_Index      import Schema__Branch_Index
from sg_send_cli.schemas.Schema__Object_Commit     import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree


class Vault__Remote(Type_Safe):
    """Stateless class for reading vault files without cloning.

    All operations go direct to the API — no local .sg_vault directory is
    created or required.  Typical cost per operation:
      list_files / get_info : ~5 API calls  (index list + index + ref + commit + tree)
      read_file             : ~6 API calls  (above + blob)
      read_file_by_id       : ~1 API call   (blob only, if caller already holds vault_key)
    """

    crypto : Vault__Crypto
    api    : Vault__API

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    def list_files(self, vault_key: str) -> dict:
        """List all files in the vault without cloning.

        Returns:
            {files: [{path, size, blob_id}], file_count: int, total_size: int}
        """
        tree, keys = self._fetch_tree(vault_key)
        flat  = self._flatten_tree(keys['vault_id'], tree, keys['read_key_bytes'])
        files = [dict(path    = path,
                      size    = int(e.size) if e.size else 0,
                      blob_id = str(e.blob_id) if e.blob_id else None)
                 for path, e in flat]
        return dict(files      = files,
                    file_count = len(files),
                    total_size = sum(f['size'] for f in files))

    def read_file(self, vault_key: str, file_path: str) -> bytes:
        """Fetch tree, locate file by path, download and decrypt.

        Raises:
            RuntimeError: if file_path is not found in the vault tree.
        """
        tree, keys = self._fetch_tree(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        flat = self._flatten_tree(vault_id, tree, read_key)
        for path, entry in flat:
            if path == file_path:
                blob_id = str(entry.blob_id) if entry.blob_id else None
                if not blob_id:
                    raise RuntimeError(f"File '{file_path}' has no blob_id in vault")
                return self._decrypt_blob(vault_id, blob_id, read_key)

        available = sorted(p for p, _ in flat)
        raise RuntimeError(
            f"File '{file_path}' not found in vault.\n"
            f"Available files: {', '.join(available) if available else '(empty vault)'}")

    def read_file_by_id(self, vault_key: str, file_id: str) -> bytes:
        """Direct download and decrypt by blob file_id.  Fastest path — skips tree fetch."""
        keys = self._resolve_keys(vault_key)
        return self._decrypt_blob(keys['vault_id'], file_id, keys['read_key_bytes'])

    def save_file(self, vault_key: str, file_path: str, dest: str) -> str:
        """Read a file from the vault and write it to a local path.

        Returns:
            Absolute path of the file that was written.
        """
        data     = self.read_file(vault_key, file_path)
        abs_dest = os.path.abspath(dest)
        parent   = os.path.dirname(abs_dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(abs_dest, 'wb') as f:
            f.write(data)
        return abs_dest

    def get_tree(self, vault_key: str) -> Schema__Object_Tree:
        """Return the decrypted current tree object (for callers who want to cache it)."""
        tree, _ = self._fetch_tree(vault_key)
        return tree

    def get_info(self, vault_key: str) -> dict:
        """Return a vault summary without downloading any file blobs.

        Returns:
            {vault_id, file_count, total_size}
        """
        tree, keys = self._fetch_tree(vault_key)
        flat       = self._flatten_tree(keys['vault_id'], tree, keys['read_key_bytes'])
        total_size = sum(int(e.size) if e.size else 0 for _, e in flat)
        return dict(vault_id   = keys['vault_id'],
                    file_count = len(flat),
                    total_size = total_size)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _resolve_keys(self, vault_key: str) -> dict:
        """Derive vault_id, read_key_bytes, write_key from a vault_key string."""
        return self.crypto.derive_keys_from_vault_key(vault_key)

    def _fetch_branch_index(self, vault_id: str, read_key: bytes) -> Schema__Branch_Index:
        """Download and decrypt the branch index for the vault."""
        index_files = self.api.list_files(vault_id, 'bare/indexes/')
        idx_files   = sorted(f for f in index_files if os.path.basename(f).startswith('idx-'))
        if not idx_files:
            raise RuntimeError(f'No branch index found for vault: {vault_id}')
        ciphertext = self.api.read(vault_id, idx_files[0])
        data       = json.loads(self.crypto.decrypt(read_key, ciphertext))
        return Schema__Branch_Index.from_json(data)

    def _fetch_head_commit_id(self, vault_id: str, read_key: bytes, named_branch) -> str:
        """Read and decrypt the HEAD ref for the named branch, returning the commit_id."""
        ref_id    = str(named_branch.head_ref_id)
        ref_data  = self.api.read(vault_id, f'bare/refs/{ref_id}')
        ref_plain = json.loads(self.crypto.decrypt(read_key, ref_data))
        commit_id = ref_plain.get('commit_id')
        if not commit_id:
            raise RuntimeError(f'No commit in HEAD ref for vault: {vault_id}')
        return commit_id

    def _fetch_tree(self, vault_key: str):
        """Core helper: derive keys, walk index→ref→commit→tree, decrypt all fields.

        Returns:
            (Schema__Object_Tree, keys_dict)
        """
        keys     = self._resolve_keys(vault_key)
        vault_id = keys['vault_id']
        read_key = keys['read_key_bytes']

        branch_index = self._fetch_branch_index(vault_id, read_key)
        named_branch = next((b for b in branch_index.branches if str(b.name) == 'current'), None)
        if not named_branch:
            raise RuntimeError(f'Named branch "current" not found in vault: {vault_id}')

        commit_id    = self._fetch_head_commit_id(vault_id, read_key, named_branch)

        commit_data  = self.api.read(vault_id, f'bare/data/{commit_id}')
        commit_plain = json.loads(self.crypto.decrypt(read_key, commit_data))
        commit       = Schema__Object_Commit.from_json(commit_plain)

        tree_id    = str(commit.tree_id)
        tree_data  = self.api.read(vault_id, f'bare/data/{tree_id}')
        tree_plain = json.loads(self.crypto.decrypt(read_key, tree_data))
        tree       = Schema__Object_Tree.from_json(tree_plain)

        for entry in tree.entries:
            self._decrypt_entry_fields(entry, read_key)

        return tree, keys

    def _flatten_tree(self, vault_id: str, tree: Schema__Object_Tree, read_key: bytes, prefix: str = '') -> list:
        """Recursively walk a tree, returning a flat list of (full_path, entry) for all file entries."""
        result = []
        for entry in tree.entries:
            name      = self._entry_path(entry)
            full_path = f'{prefix}/{name}' if prefix else name
            if entry.blob_id:
                result.append((full_path, entry))
            elif entry.tree_id:
                sub_data  = self.api.read(vault_id, f'bare/data/{str(entry.tree_id)}')
                sub_plain = json.loads(self.crypto.decrypt(read_key, sub_data))
                sub_tree  = Schema__Object_Tree.from_json(sub_plain)
                for sub_entry in sub_tree.entries:
                    self._decrypt_entry_fields(sub_entry, read_key)
                result.extend(self._flatten_tree(vault_id, sub_tree, read_key, prefix=full_path))
        return result

    def _decrypt_entry_fields(self, entry, read_key: bytes) -> None:
        """Decrypt encrypted tree entry fields (path, size, content_hash) in-place."""
        if entry.name_enc and not entry.path and not entry.name:
            encrypted  = base64.b64decode(str(entry.name_enc))
            entry.path = self.crypto.decrypt(read_key, encrypted).decode()
        if entry.size_enc:
            encrypted_size = base64.b64decode(str(entry.size_enc))
            entry.size     = int(self.crypto.decrypt(read_key, encrypted_size).decode())
        if entry.content_hash_enc and not entry.content_hash:
            encrypted_hash     = base64.b64decode(str(entry.content_hash_enc))
            entry.content_hash = self.crypto.decrypt(read_key, encrypted_hash).decode()

    def _decrypt_blob(self, vault_id: str, blob_id: str, read_key: bytes) -> bytes:
        """Download and decrypt a single blob by its object ID."""
        ciphertext = self.api.read(vault_id, f'bare/data/{blob_id}')
        return self.crypto.decrypt(read_key, ciphertext)

    def _entry_path(self, entry) -> str:
        """Return the file path string from a tree entry (handles path vs name field)."""
        return str(entry.path) if entry.path else str(entry.name)
