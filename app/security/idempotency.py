class IdempotencyStore:

    def __init__(self):
        self._keys = {}

    def exists(self, key: str) -> bool:
        return key in self._keys

    def save(self, key: str, result):
        self._keys[key] = result

    def get(self, key: str):
        return self._keys.get(key)