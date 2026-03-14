from sg_send_cli.api.Vault__API import Vault__API


class Vault__API__In_Memory(Vault__API):
    """In-memory API stub for testing. Stores writes in a dict instead of hitting a server."""

    def setup(self):
        self._store       = {}
        self._write_count = 0
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        self._store[f'{vault_id}/{file_id}'] = payload
        self._write_count += 1
        return {'status': 'ok'}

    def read(self, vault_id: str, file_id: str) -> bytes:
        key = f'{vault_id}/{file_id}'
        if key not in self._store:
            raise RuntimeError(f'Not found: {key}')
        return self._store[key]

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        key = f'{vault_id}/{file_id}'
        self._store.pop(key, None)
        return {'status': 'ok'}
