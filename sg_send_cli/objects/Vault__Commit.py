import base64
import json
import time
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto                 import PKI__Crypto
from   sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager         import Vault__Ref_Manager
from   sg_send_cli.schemas.Schema__Object_Commit      import Schema__Object_Commit
from   sg_send_cli.schemas.Schema__Object_Tree        import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry  import Schema__Object_Tree_Entry


class Vault__Commit(Type_Safe):
    crypto       : Vault__Crypto
    pki          : PKI__Crypto
    object_store : Vault__Object_Store
    ref_manager  : Vault__Ref_Manager

    def encrypt_tree_entry_fields(self, entry: Schema__Object_Tree_Entry, key: bytes) -> dict:
        entry_dict = entry.json()
        path_value = str(entry.path) if entry.path else (str(entry.name) if entry.name else '')
        if path_value:
            encrypted = self.crypto.encrypt(key, path_value.encode())
            entry_dict['name_enc'] = base64.b64encode(encrypted).decode()
        size_value = str(int(entry.size))
        encrypted_size = self.crypto.encrypt(key, size_value.encode())
        entry_dict['size_enc'] = base64.b64encode(encrypted_size).decode()
        if entry.content_hash:
            encrypted_hash = self.crypto.encrypt(key, str(entry.content_hash).encode())
            entry_dict['content_hash_enc'] = base64.b64encode(encrypted_hash).decode()
        return entry_dict

    def decrypt_tree_entry_fields(self, entry: Schema__Object_Tree_Entry, key: bytes) -> Schema__Object_Tree_Entry:
        if entry.name_enc and not entry.path and not entry.name:
            encrypted = base64.b64decode(str(entry.name_enc))
            decrypted = self.crypto.decrypt(key, encrypted).decode()
            entry.path = decrypted
        if entry.size_enc:
            encrypted_size = base64.b64decode(str(entry.size_enc))
            entry.size = int(self.crypto.decrypt(key, encrypted_size).decode())
        if entry.content_hash_enc and not entry.content_hash:
            encrypted_hash = base64.b64decode(str(entry.content_hash_enc))
            entry.content_hash = self.crypto.decrypt(key, encrypted_hash).decode()
        return entry

    def create_commit(self, tree: Schema__Object_Tree, read_key: bytes,
                      parent_ids: list = None, message: str = '',
                      branch_id: str = None, signing_key=None,
                      timestamp_ms: int = None) -> str:

        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        tree_dict = tree.json()
        tree_dict['entries'] = [self.encrypt_tree_entry_fields(e, read_key) for e in tree.entries]
        tree_json      = json.dumps(tree_dict).encode()
        encrypted_tree = self.crypto.encrypt(read_key, tree_json)
        tree_id        = self.object_store.store(encrypted_tree)

        parents = []
        if parent_ids:
            parents = [p for p in parent_ids if p]

        commit = Schema__Object_Commit(tree_id      = tree_id,
                                        schema       = 'commit_v1',
                                        timestamp_ms = timestamp_ms,
                                        message      = message,
                                        branch_id    = branch_id or '',
                                        parents      = parents)

        # Set legacy parent field for backward compat
        if parents:
            commit.parent = parents[0]

        commit_data = json.dumps(commit.json()).encode()

        if signing_key:
            sig_raw          = self.pki.sign(signing_key, commit_data)
            sig_b64          = base64.b64encode(sig_raw).decode()
            commit.signature = sig_b64
            commit_data      = json.dumps(commit.json()).encode()

        encrypted_commit = self.crypto.encrypt(read_key, commit_data)
        commit_id        = self.object_store.store(encrypted_commit)
        return commit_id

    def load_commit(self, commit_id: str, read_key: bytes) -> Schema__Object_Commit:
        ciphertext  = self.object_store.load(commit_id)
        commit_data = self.crypto.decrypt(read_key, ciphertext)
        return Schema__Object_Commit.from_json(json.loads(commit_data))

    def load_tree(self, tree_id: str, read_key: bytes) -> Schema__Object_Tree:
        ciphertext = self.object_store.load(tree_id)
        tree_data  = self.crypto.decrypt(read_key, ciphertext)
        tree       = Schema__Object_Tree.from_json(json.loads(tree_data))
        for entry in tree.entries:
            self.decrypt_tree_entry_fields(entry, read_key)
        return tree

    def verify_commit_signature(self, commit: Schema__Object_Commit, public_key) -> bool:
        if not commit.signature:
            return False
        sig_raw = base64.b64decode(str(commit.signature))

        commit_dict = commit.json()
        commit_dict['signature'] = None
        commit_data = json.dumps(commit_dict).encode()

        return self.pki.verify(public_key, sig_raw, commit_data)
