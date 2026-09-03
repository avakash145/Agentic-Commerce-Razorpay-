from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization


class KeyManager:
    def __init__(self):
        self.private_key = Ed25519PrivateKey.generate()
        self._public_key = self.private_key.public_key()

    def sign(self, data: bytes) -> bytes:
        return self.private_key.sign(data)

    def verify(self,signature:bytes,data:bytes) -> bool:
        try:
            self._public_key.verify(signature, data)
            return True
        except Exception:
            return False
