import json

from app.security.mandate import PaymentMandate
from app.security.keys import KeyManager


class MandateSigner:

    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    def _canonicalize(self,mandate: PaymentMandate) -> bytes:
        data = mandate.model_dump(mode="json")
        canonical = json.dumps(data,sort_keys=True,separators=(",", ":"))
        return canonical.encode("utf-8")

    def sign(self,mandate: PaymentMandate) -> bytes:
        data = self._canonicalize(mandate)
        return self.key_manager.sign(data)

    def verify(self,mandate: PaymentMandate,signature: bytes) -> bool:
        data = self._canonicalize(mandate)
        return self.key_manager.verify(signature,data)