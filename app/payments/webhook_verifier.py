import os
import hmac
import hashlib

from dotenv import load_dotenv


load_dotenv()


class WebhookVerifier:

    def __init__(self):

        self.secret = os.getenv(
            "RAZORPAY_WEBHOOK_SECRET"
        )

        if not self.secret:

            raise RuntimeError(
                "RAZORPAY_WEBHOOK_SECRET is missing"
            )

    def verify(
        self,
        payload: bytes,
        signature: str
    ) -> bool:

        expected_signature = hmac.new(
            self.secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(
            expected_signature,
            signature
        )