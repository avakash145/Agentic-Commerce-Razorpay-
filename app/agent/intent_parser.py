import os
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from app.agent.intent import CommerceIntent

load_dotenv()


class IntentParser:

    def __init__(self):

        api_key = os.getenv("OLLAMA_API_KEY")

        # The hosted model is an enhancement, not a reason for the
        # shopping experience to be unavailable.  A conservative local
        # parser below keeps demos and health checks usable without it.
        self.structured_llm = None

        if not api_key:
            return

        model = os.getenv(
            "OLLAMA_MODEL",
            "nemotron-3-ultra"
        )

        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
            timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "15")),
            max_retries=1,
            api_key=api_key,
            base_url=("https://ollama.com/v1"))

        self.structured_llm = (self.llm.with_structured_output(CommerceIntent))

    @staticmethod
    def _amount(match: re.Match) -> float:
        value = float(match.group(1).replace(",", ""))
        unit = (match.group(2) or "").lower()

        if unit in {"lakh", "lac"}:
            value *= 100000
        elif unit in {"k", "thousand"}:
            value *= 1000

        return value

    def _fallback_parse(self, user_query: str) -> CommerceIntent:
        """Extract only explicit, high-confidence constraints locally."""

        query = " ".join(user_query.split())
        lower = query.lower()
        amount = r"(?:₹|rs\.?|inr\s*)?([\d][\d,]*(?:\.\d+)?)\s*(lakh|lac|k|thousand)?"

        max_match = re.search(
            rf"(?:under|below|less than|up to|upto|within|budget\s+(?:of|is))\s*{amount}",
            lower,
        )
        min_match = re.search(
            rf"(?:above|over|more than|starting at)\s*{amount}",
            lower,
        )

        def first_group(match, index=1):
            if not match:
                return None
            return match.group(index) or match.group(index + 1)

        ram_match = re.search(
            r"(?:(\d+)\s*gb\s*(?:of\s*)?(?:ram|memory)|(?:ram|memory)\s*(?:of\s*)?(\d+)\s*gb)",
            lower,
        )
        storage_match = re.search(
            r"(?:(\d+)\s*gb\s*(?:of\s*)?(?:storage|ssd)|(?:storage|ssd)\s*(?:of\s*)?(\d+)\s*gb)",
            lower,
        )
        rating_match = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?star", lower)

        category = None
        for candidate in (
            "laptop", "notebook", "phone", "smartphone", "tablet",
            "headphone", "earbuds", "monitor", "camera", "keyboard",
            "mouse", "desktop", "computer", "webcam", "printer",
            "router", "ssd", "storage",
        ):
            if candidate in lower:
                category = candidate
                break

        gpu = None
        # Prefer a concrete model when the request says "GPU RTX 3050";
        # matching the generic word GPU first loses the useful model.
        gpu_match = re.search(
            r"\b((?:rtx|gtx)(?:\s*\d{3,4})?)\b",
            lower,
        )
        if not gpu_match:
            gpu_match = re.search(
                r"\b(dedicated\s+gpu|gpu)\b",
                lower,
            )
        if gpu_match:
            gpu = gpu_match.group(1)

        cpu = None
        cpu_match = re.search(r"\b((?:intel\s+)?(?:core\s+i[3579]|ultra\s*[3579])|ryzen\s*[3579])\b", lower)
        if cpu_match:
            cpu = cpu_match.group(1)

        semantic_terms = []
        for term in (
            "ai", "gaming", "business", "student", "developer",
            "portable", "professional", "wireless", "noise cancelling",
        ):
            if term in lower:
                semantic_terms.append(term)

        search_parts = []
        if category:
            search_parts.append(category)
        search_parts.extend(semantic_terms)
        if gpu:
            search_parts.append(gpu)
        if cpu:
            search_parts.append(cpu)

        return CommerceIntent(
            search_query=" ".join(dict.fromkeys(search_parts)) or query,
            category=category,
            search_terms=semantic_terms,
            max_price_inr=self._amount(max_match) if max_match else None,
            min_price_inr=self._amount(min_match) if min_match else None,
            min_ram_gb=int(first_group(ram_match)) if ram_match else None,
            min_storage_gb=int(first_group(storage_match)) if storage_match else None,
            gpu=gpu,
            cpu=cpu,
            min_rating=float(rating_match.group(1)) if rating_match else None,
            stock_required=True,
        )

    # PARSE

    def parse(
        self,
        user_query: str
    ) -> CommerceIntent:

        system_prompt = """
You are the structured intent parser
for a secure agentic commerce system.

Convert the user's shopping request into
the CommerceIntent schema.

IMPORTANT:

You ONLY interpret the request.

You NEVER:

- purchase products
- authorize payments
- create payment mandates
- call Razorpay
- choose a payment method
- invent product information
- decide whether a product is eligible

Extract ONLY information present in
the user's request.

RULES:

1. category:
   Extract the product category.

2. search_terms:
   Extract important semantic terms.

3. max_price_inr:
   Extract the maximum budget.

4. min_price_inr:
   Extract minimum price if explicitly stated.

5. Convert monetary amounts to INR.

6. min_ram_gb:
   Extract minimum RAM.

7. min_storage_gb:
   Extract minimum storage.

8. gpu:
   Extract GPU requirements.

9. cpu:
   Extract CPU requirements.

10. min_rating:
    Extract minimum rating.

11. stock_required:
    If the user explicitly requires
    availability, set true.

12. Never invent constraints.

13. If something is not specified,
    return null.

14. search_query should contain the
    semantic product query.

Example:

User:
"Find me an AI laptop under ₹80000"

Return conceptually:

category = "laptop"

search_query = "AI laptop"

search_terms = ["AI"]

max_price_inr = 80000

Everything else = null
"""

        messages = [

            (
                "system",
                system_prompt
            ),

            (
                "human",
                user_query
            )
        ]

        if self.structured_llm is None:
            return self._fallback_parse(user_query)

        try:
            intent = self.structured_llm.invoke(messages)
        except Exception as exc:
            print(f"[INTENT FALLBACK] {exc}")
            return self._fallback_parse(user_query)

        # SAFETY / NORMALIZATION

        if not intent.search_query:

            parts = []

            if intent.category:

                parts.append(
                    intent.category
                )

            parts.extend(
                intent.search_terms
            )

            intent.search_query = " ".join(
                dict.fromkeys(parts)
            )

        # Keep explicit RTX/GTX model numbers from being weakened to the
        # generic "gpu" value by a hosted parser response.
        local_intent = self._fallback_parse(user_query)
        if local_intent.gpu and re.search(
            r"\b(?:rtx|gtx)\b",
            local_intent.gpu,
            re.IGNORECASE,
        ):
            intent.gpu = local_intent.gpu
            if local_intent.gpu.lower() not in intent.search_query.lower():
                intent.search_query = (
                    f"{intent.search_query} {local_intent.gpu}"
                ).strip()

        return intent
