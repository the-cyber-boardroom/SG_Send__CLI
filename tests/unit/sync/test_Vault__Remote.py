import os
import shutil
import tempfile

from sg_send_cli.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sg_send_cli.crypto.Vault__Crypto       import Vault__Crypto
from sg_send_cli.sync.Vault__Remote         import Vault__Remote
from sg_send_cli.sync.Vault__Sync           import Vault__Sync


VAULT_KEY = 'test-passphrase:testvlt'


class Test_Vault__Remote:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.remote  = Vault__Remote(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _vault_dir(self, name='origin'):
        return os.path.join(self.tmp_dir, name)

    def _init_push_empty(self):
        """Create and push an empty vault."""
        directory = self._vault_dir()
        self.sync.init(directory, vault_key=VAULT_KEY)
        self.sync.push(directory)
        return directory

    def _init_push_with_files(self, files: dict):
        """Create, populate, commit, and push a vault.

        files: {relative_path: bytes_content}
        """
        directory = self._vault_dir()
        self.sync.init(directory, vault_key=VAULT_KEY)
        for path, content in files.items():
            full = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as f:
                f.write(content)
        self.sync.commit(directory, message='add files')
        self.sync.push(directory)
        return directory

    # ------------------------------------------------------------------ #
    #  list_files                                                          #
    # ------------------------------------------------------------------ #

    def test_list_files__empty_vault(self):
        self._init_push_empty()
        result = self.remote.list_files(VAULT_KEY)
        assert result['files']      == []
        assert result['file_count'] == 0
        assert result['total_size'] == 0

    def test_list_files__with_single_file(self):
        self._init_push_with_files({'hello.txt': b'hello world'})
        result = self.remote.list_files(VAULT_KEY)
        assert result['file_count'] == 1
        paths = [f['path'] for f in result['files']]
        assert 'hello.txt' in paths

    def test_list_files__returns_correct_sizes(self):
        content = b'x' * 100
        self._init_push_with_files({'data.bin': content})
        result = self.remote.list_files(VAULT_KEY)
        assert result['file_count'] == 1
        assert result['total_size'] == 100
        assert result['files'][0]['size'] == 100

    def test_list_files__multiple_files(self):
        self._init_push_with_files({
            'a.txt': b'file a',
            'b.txt': b'file b',
            'sub/c.txt': b'file c',
        })
        result = self.remote.list_files(VAULT_KEY)
        assert result['file_count'] == 3
        paths = {f['path'] for f in result['files']}
        assert 'a.txt' in paths
        assert 'b.txt' in paths
        assert 'sub/c.txt' in paths

    def test_list_files__blob_ids_present(self):
        self._init_push_with_files({'file.txt': b'content'})
        result = self.remote.list_files(VAULT_KEY)
        for f in result['files']:
            assert f['blob_id'] is not None
            assert len(f['blob_id']) > 0

    # ------------------------------------------------------------------ #
    #  read_file                                                           #
    # ------------------------------------------------------------------ #

    def test_read_file__existing_file(self):
        content = b'hello from remote'
        self._init_push_with_files({'msg.txt': content})
        result = self.remote.read_file(VAULT_KEY, 'msg.txt')
        assert result == content

    def test_read_file__binary_content(self):
        content = bytes(range(256))
        self._init_push_with_files({'blob.bin': content})
        result = self.remote.read_file(VAULT_KEY, 'blob.bin')
        assert result == content

    def test_read_file__nested_path(self):
        content = b'nested file content'
        self._init_push_with_files({'dir/sub/deep.txt': content})
        result = self.remote.read_file(VAULT_KEY, 'dir/sub/deep.txt')
        assert result == content

    def test_read_file__missing_file_raises_error(self):
        self._init_push_with_files({'exists.txt': b'here'})
        try:
            self.remote.read_file(VAULT_KEY, 'missing.txt')
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            assert 'missing.txt' in str(e)
            assert 'not found' in str(e).lower()

    def test_read_file__missing_file_lists_available(self):
        self._init_push_with_files({'alpha.txt': b'a', 'beta.txt': b'b'})
        try:
            self.remote.read_file(VAULT_KEY, 'gamma.txt')
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            msg = str(e)
            assert 'alpha.txt' in msg or 'beta.txt' in msg

    def test_read_file__empty_vault_raises_error(self):
        self._init_push_empty()
        try:
            self.remote.read_file(VAULT_KEY, 'any.txt')
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            assert 'empty vault' in str(e).lower() or 'not found' in str(e).lower()

    # ------------------------------------------------------------------ #
    #  read_file_by_id                                                     #
    # ------------------------------------------------------------------ #

    def test_read_file_by_id__direct_download(self):
        content = b'direct access content'
        self._init_push_with_files({'direct.txt': content})
        listing = self.remote.list_files(VAULT_KEY)
        blob_id = listing['files'][0]['blob_id']
        result  = self.remote.read_file_by_id(VAULT_KEY, blob_id)
        assert result == content

    # ------------------------------------------------------------------ #
    #  save_file                                                           #
    # ------------------------------------------------------------------ #

    def test_save_file__writes_to_disk(self):
        content  = b'save me to disk'
        self._init_push_with_files({'saveme.txt': content})
        dest_path = os.path.join(self.tmp_dir, 'output.txt')
        returned  = self.remote.save_file(VAULT_KEY, 'saveme.txt', dest_path)
        assert returned == dest_path
        with open(dest_path, 'rb') as f:
            assert f.read() == content

    def test_save_file__creates_parent_dirs(self):
        content   = b'deep save'
        self._init_push_with_files({'src.txt': content})
        dest_path = os.path.join(self.tmp_dir, 'new', 'nested', 'out.txt')
        self.remote.save_file(VAULT_KEY, 'src.txt', dest_path)
        assert os.path.isfile(dest_path)
        with open(dest_path, 'rb') as f:
            assert f.read() == content

    def test_save_file__returns_absolute_path(self):
        self._init_push_with_files({'f.txt': b'data'})
        dest  = os.path.join(self.tmp_dir, 'out.txt')
        result = self.remote.save_file(VAULT_KEY, 'f.txt', dest)
        assert os.path.isabs(result)

    # ------------------------------------------------------------------ #
    #  get_tree                                                            #
    # ------------------------------------------------------------------ #

    def test_get_tree__returns_tree_object(self):
        from sg_send_cli.schemas.Schema__Object_Tree import Schema__Object_Tree
        self._init_push_with_files({'t.txt': b'tree test'})
        tree = self.remote.get_tree(VAULT_KEY)
        assert isinstance(tree, Schema__Object_Tree)
        assert len(tree.entries) == 1

    def test_get_tree__empty_vault(self):
        self._init_push_empty()
        tree = self.remote.get_tree(VAULT_KEY)
        assert tree.entries == []

    # ------------------------------------------------------------------ #
    #  get_info                                                            #
    # ------------------------------------------------------------------ #

    def test_get_info__returns_vault_metadata(self):
        self._init_push_with_files({
            'a.txt': b'aaa',
            'b.txt': b'bbbbbb',
        })
        info = self.remote.get_info(VAULT_KEY)
        assert info['vault_id']   == 'testvlt'
        assert info['file_count'] == 2
        assert info['total_size'] == 9   # 3 + 6

    def test_get_info__empty_vault(self):
        self._init_push_empty()
        info = self.remote.get_info(VAULT_KEY)
        assert info['vault_id']   == 'testvlt'
        assert info['file_count'] == 0
        assert info['total_size'] == 0

    # ------------------------------------------------------------------ #
    #  Round-trip: push then remote-read                                  #
    # ------------------------------------------------------------------ #

    def test_roundtrip__push_then_read_file(self):
        content = b'round-trip content'
        self._init_push_with_files({'roundtrip.txt': content})
        assert self.remote.read_file(VAULT_KEY, 'roundtrip.txt') == content

    def test_roundtrip__push_then_list_and_read(self):
        files = {'one.txt': b'one', 'two.txt': b'two', 'three.txt': b'three'}
        self._init_push_with_files(files)
        listing = self.remote.list_files(VAULT_KEY)
        assert listing['file_count'] == 3
        for entry in listing['files']:
            data = self.remote.read_file_by_id(VAULT_KEY, entry['blob_id'])
            assert data == files[entry['path']]

    # ------------------------------------------------------------------ #
    #  No local state created                                              #
    # ------------------------------------------------------------------ #

    def test_no_local_state_created(self):
        """Remote operations must not create any .sg_vault directory."""
        self._init_push_with_files({'check.txt': b'checking'})
        before = set(os.listdir(self.tmp_dir))
        self.remote.list_files(VAULT_KEY)
        self.remote.read_file(VAULT_KEY, 'check.txt')
        self.remote.get_info(VAULT_KEY)
        after = set(os.listdir(self.tmp_dir))
        new_entries = after - before
        for entry in new_entries:
            assert '.sg_vault' not in entry, f'Unexpected local state created: {entry}'
