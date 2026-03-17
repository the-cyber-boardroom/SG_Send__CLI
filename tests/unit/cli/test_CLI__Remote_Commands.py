import io
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

from sg_send_cli.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sg_send_cli.cli.CLI__Vault             import CLI__Vault
from sg_send_cli.crypto.Vault__Crypto       import Vault__Crypto
from sg_send_cli.sync.Vault__Sync           import Vault__Sync


VAULT_KEY = 'test-pass:clitest'


class Test_CLI__Remote_Commands:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.api      = Vault__API__In_Memory()
        self.api.setup()
        self.sync     = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli      = CLI__Vault()
        # Wire CLI to the same in-memory API
        self.cli.create_remote = lambda base_url=None, access_token=None: \
            __import__('sg_send_cli.sync.Vault__Remote', fromlist=['Vault__Remote'])\
            .Vault__Remote(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------ #
    #  Setup helpers                                                       #
    # ------------------------------------------------------------------ #

    def _vault_dir(self, name='origin'):
        return os.path.join(self.tmp_dir, name)

    def _push_files(self, files: dict):
        directory = self._vault_dir()
        self.sync.init(directory, vault_key=VAULT_KEY)
        for path, content in files.items():
            full = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as f:
                f.write(content if isinstance(content, bytes) else content.encode())
        self.sync.commit(directory)
        self.sync.push(directory)

    def _push_empty(self):
        directory = self._vault_dir()
        self.sync.init(directory, vault_key=VAULT_KEY)
        self.sync.push(directory)

    # ------------------------------------------------------------------ #
    #  cmd_ls                                                              #
    # ------------------------------------------------------------------ #

    def test_ls_empty_vault(self, capsys):
        self._push_empty()
        args = SimpleNamespace(vault_key=VAULT_KEY, base_url=None, token=None)
        self.cli.cmd_ls(args)
        out = capsys.readouterr().out
        assert 'clitest' in out
        assert '0 files' in out

    def test_ls_with_files(self, capsys):
        self._push_files({'alpha.txt': b'aaa', 'beta.txt': b'bbb'})
        args = SimpleNamespace(vault_key=VAULT_KEY, base_url=None, token=None)
        self.cli.cmd_ls(args)
        out = capsys.readouterr().out
        assert '2 files' in out
        assert 'alpha.txt' in out
        assert 'beta.txt' in out

    def test_ls_shows_sizes(self, capsys):
        self._push_files({'file.txt': b'x' * 512})
        args = SimpleNamespace(vault_key=VAULT_KEY, base_url=None, token=None)
        self.cli.cmd_ls(args)
        out = capsys.readouterr().out
        assert '512' in out or '0.5 KB' in out

    # ------------------------------------------------------------------ #
    #  cmd_cat                                                             #
    # ------------------------------------------------------------------ #

    def test_cat_outputs_to_stdout(self):
        content = b'hello from vault cat'
        self._push_files({'greet.txt': content})
        args = SimpleNamespace(vault_key=VAULT_KEY, file_path='greet.txt',
                               base_url=None, token=None)
        captured = io.BytesIO()
        original_buffer = sys.stdout.buffer
        # Redirect stdout.buffer to our BytesIO via a wrapper object
        class _FakeStdout:
            buffer = captured
            def write(self, data): original_buffer.write(data)
        old_stdout = sys.stdout
        sys.stdout  = _FakeStdout()
        try:
            self.cli.cmd_cat(args)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == content

    def test_cat_missing_file_raises_error(self):
        self._push_empty()
        args = SimpleNamespace(vault_key=VAULT_KEY, file_path='no-such.txt',
                               base_url=None, token=None)
        try:
            self.cli.cmd_cat(args)
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            assert 'no-such.txt' in str(e)

    # ------------------------------------------------------------------ #
    #  cmd_get                                                             #
    # ------------------------------------------------------------------ #

    def test_get_saves_file_locally(self, capsys):
        content  = b'download me'
        self._push_files({'download.txt': content})
        dest = os.path.join(self.tmp_dir, 'local_copy.txt')
        args = SimpleNamespace(vault_key=VAULT_KEY, file_path='download.txt',
                               dest=dest, base_url=None, token=None)
        self.cli.cmd_get(args)
        assert os.path.isfile(dest)
        with open(dest, 'rb') as f:
            assert f.read() == content
        out = capsys.readouterr().out
        assert 'Saved' in out
        assert 'download.txt' in out

    def test_get_default_dest_uses_filename(self, capsys):
        content = b'default dest'
        self._push_files({'myfile.txt': content})
        original_dir = os.getcwd()
        try:
            os.chdir(self.tmp_dir)
            args = SimpleNamespace(vault_key=VAULT_KEY, file_path='myfile.txt',
                                   dest=None, base_url=None, token=None)
            self.cli.cmd_get(args)
            expected = os.path.join(self.tmp_dir, 'myfile.txt')
            assert os.path.isfile(expected)
        finally:
            os.chdir(original_dir)

    # ------------------------------------------------------------------ #
    #  cmd_info                                                            #
    # ------------------------------------------------------------------ #

    def test_info_shows_vault_id(self, capsys):
        self._push_empty()
        args = SimpleNamespace(vault_key=VAULT_KEY, base_url=None, token=None)
        self.cli.cmd_info(args)
        out = capsys.readouterr().out
        assert 'clitest' in out

    def test_info_shows_file_count(self, capsys):
        self._push_files({'a.txt': b'a', 'b.txt': b'b', 'c.txt': b'c'})
        args = SimpleNamespace(vault_key=VAULT_KEY, base_url=None, token=None)
        self.cli.cmd_info(args)
        out = capsys.readouterr().out
        assert '3' in out

    def test_info_shows_total_size(self, capsys):
        self._push_files({'data.bin': b'x' * 1024})
        args = SimpleNamespace(vault_key=VAULT_KEY, base_url=None, token=None)
        self.cli.cmd_info(args)
        out = capsys.readouterr().out
        assert '1.0 KB' in out or '1024' in out

    # ------------------------------------------------------------------ #
    #  format_size helper                                                  #
    # ------------------------------------------------------------------ #

    def test_format_size_bytes(self):
        assert self.cli._format_size(500)      == '500 B'

    def test_format_size_kilobytes(self):
        assert '1.0 KB' in self.cli._format_size(1024)

    def test_format_size_megabytes(self):
        assert 'MB' in self.cli._format_size(2 * 1024 * 1024)

    # ------------------------------------------------------------------ #
    #  CLI parser integration                                              #
    # ------------------------------------------------------------------ #

    def test_parser_registers_ls_command(self):
        from sg_send_cli.cli.CLI__Main import CLI__Main
        main_cli = CLI__Main()
        parser   = main_cli.build_parser()
        args     = parser.parse_args(['ls', 'mypass:myvault'])
        assert args.command   == 'ls'
        assert args.vault_key == 'mypass:myvault'

    def test_parser_registers_cat_command(self):
        from sg_send_cli.cli.CLI__Main import CLI__Main
        main_cli = CLI__Main()
        parser   = main_cli.build_parser()
        args     = parser.parse_args(['cat', 'mypass:myvault', 'path/to/file.txt'])
        assert args.command   == 'cat'
        assert args.vault_key == 'mypass:myvault'
        assert args.file_path == 'path/to/file.txt'

    def test_parser_registers_get_command(self):
        from sg_send_cli.cli.CLI__Main import CLI__Main
        main_cli = CLI__Main()
        parser   = main_cli.build_parser()
        args     = parser.parse_args(['get', 'mypass:myvault', 'file.txt', 'dest.txt'])
        assert args.command   == 'get'
        assert args.vault_key == 'mypass:myvault'
        assert args.file_path == 'file.txt'
        assert args.dest      == 'dest.txt'

    def test_parser_registers_get_command_no_dest(self):
        from sg_send_cli.cli.CLI__Main import CLI__Main
        main_cli = CLI__Main()
        parser   = main_cli.build_parser()
        args     = parser.parse_args(['get', 'mypass:myvault', 'file.txt'])
        assert args.dest is None

    def test_parser_registers_info_command(self):
        from sg_send_cli.cli.CLI__Main import CLI__Main
        main_cli = CLI__Main()
        parser   = main_cli.build_parser()
        args     = parser.parse_args(['info', 'mypass:myvault'])
        assert args.command   == 'info'
        assert args.vault_key == 'mypass:myvault'
