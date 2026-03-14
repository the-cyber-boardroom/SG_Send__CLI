import pytest
from sg_send_cli.safe_types.Safe_Str__Batch_Op import Safe_Str__Batch_Op


class Test_Safe_Str__Batch_Op:

    def test_valid_write(self):
        op = Safe_Str__Batch_Op('write')
        assert op == 'write'

    def test_valid_delete(self):
        op = Safe_Str__Batch_Op('delete')
        assert op == 'delete'

    def test_valid_write_if_match(self):
        op = Safe_Str__Batch_Op('write-if-match')
        assert op == 'write-if-match'

    def test_empty_allowed(self):
        op = Safe_Str__Batch_Op('')
        assert op == ''

    def test_uppercase_converted_to_lower(self):
        op = Safe_Str__Batch_Op('WRITE')
        assert op == 'write'

    def test_invalid_op_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Batch_Op('read')

    def test_partial_match_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Batch_Op('write-extra')

    def test_type_preserved(self):
        op = Safe_Str__Batch_Op('write')
        assert type(op).__name__ == 'Safe_Str__Batch_Op'
