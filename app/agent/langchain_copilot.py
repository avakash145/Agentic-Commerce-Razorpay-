import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

load_dotenv()


class LangChainCommerceCopilot:
    """
    LangChain-powered AI Shopping Copilot.
    Handles product comparison, natural language product selection,
    and interactive commerce recommendations using local or hosted LLMs.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY", "ollama")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))

        try:
            self.llm = ChatOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                temperature=0.3,
                timeout=self.timeout,
                max_retries=1,
            )
            self.available = True
        except Exception as exc:
            print(f"[LANGCHAIN COPILOT INIT WARNING] Could not initialize LLM: {exc}")
            self.llm = None
            self.available = False

    def _format_product_brief(self, p: Dict[str, Any], index: int = 1) -> str:
        title = p.get("title", "Product")
        asin = p.get("asin", "N/A")
        brand = p.get("brand", "Unknown")
        price_inr = p.get("price_inr") or (p.get("price") * p.get("fx_rate", 96.3) if p.get("price") else "N/A")
        price_str = f"₹{price_inr:,.2f}" if isinstance(price_inr, (int, float)) else str(price_inr)
        
        specs = p.get("specs") or {}
        ram = specs.get("ram_gb")
        ram_str = f"{ram}GB RAM" if ram else "N/A RAM"
        storage = specs.get("storage_gb")
        storage_str = f"{storage}GB SSD" if storage else "N/A Storage"
        gpu = specs.get("gpu") or "Integrated GPU"
        cpu = specs.get("cpu") or "N/A CPU"
        screen = specs.get("screen_size_inches")
        screen_str = f"{screen}\"" if screen else ""
        stars = p.get("stars", 4.0)
        reviews = p.get("reviews_count", 0)

        return (
            f"Product #{index}: {title}\n"
            f"  - ASIN: {asin} | Brand: {brand}\n"
            f"  - Price: {price_str}\n"
            f"  - Key Specs: {cpu} | {gpu} | {ram_str} | {storage_str} {screen_str}\n"
            f"  - Rating: {stars}★ ({reviews} reviews)\n"
        )

    def compare_products(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare 2 or more products using LangChain and generate an objective,
        structured comparison matrix with a recommendation verdict.
        """
        if not products:
            return {
                "summary": "No products provided for comparison.",
                "analysis_markdown": "Please select at least 2 products to compare.",
                "winner_asin": None,
            }

        if len(products) == 1:
            p = products[0]
            brief = self._format_product_brief(p, 1)
            return {
                "summary": f"Single product overview: {p.get('title')}",
                "analysis_markdown": f"### {p.get('title')}\n\n{brief}\nSelect another product to see a side-by-side comparison.",
                "winner_asin": p.get("asin"),
            }

        # Build product details text
        product_texts = "\n".join(
            self._format_product_brief(p, i + 1) for i, p in enumerate(products)
        )

        system_prompt = (
            "You are an expert AI Shopping and Tech Hardware Advisor for an eCommerce platform. "
            "You provide clear, accurate, and structured comparisons between products to help customers make an informed purchase decision. "
            "Always include:\n"
            "1. **Quick Overview**: A 2-sentence summary comparing their target audiences.\n"
            "2. **Comparison Matrix (Markdown Table)**: Columns for Feature, each Product Name, and Advantage.\n"
            "3. **Key Trade-offs**: Contrast CPU/GPU performance, RAM/Storage, Display, and Value for Money.\n"
            "4. **Verdict / Who Should Buy What**: Clear recommendation on which user persona should choose which product.\n"
            "Keep the tone professional, objective, and easy to read with clean Markdown formatting."
        )

        user_prompt = (
            f"Please compare the following {len(products)} products side by side:\n\n"
            f"{product_texts}\n\n"
            "Deliver an in-depth comparison table, breakdown of differences, and a definitive buying verdict."
        )

        if not self.available or self.llm is None:
            return self._fallback_comparison(products)

        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}"),
            ])
            chain = prompt | self.llm | StrOutputParser()
            analysis = chain.invoke({"input": user_prompt})

            # Determine likely winner (highest rating or first product)
            sorted_by_rating = sorted(products, key=lambda x: x.get("stars", 0) or 0, reverse=True)
            winner_asin = sorted_by_rating[0].get("asin") if sorted_by_rating else products[0].get("asin")

            return {
                "summary": f"Comparison between {len(products)} products",
                "analysis_markdown": analysis,
                "winner_asin": winner_asin,
                "products_compared": [p.get("asin") for p in products],
            }
        except Exception as exc:
            print(f"[LANGCHAIN COPILOT ERROR] compare_products failed: {exc}")
            return self._fallback_comparison(products)

    def compare_followup(
        self,
        query: str,
        products: List[Dict[str, Any]],
        comparison_summary: str = "",
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Handle specific user follow-up questions about an ongoing product comparison.
        """
        if not products:
            return {
                "reply": "No products are currently selected for comparison.",
                "winner_asin": None,
            }

        product_texts = "\n".join(
            self._format_product_brief(p, i + 1) for i, p in enumerate(products)
        )

        system_prompt = (
            "You are an expert AI Shopping Advisor specializing in tech hardware comparisons. "
            "The customer is evaluating specific products side by side and has asked a follow-up question. "
            "Guidelines:\n"
            "- Answer directly and specifically about the products being compared.\n"
            "- Explain trade-offs clearly (e.g. processor speed, GPU capabilities, RAM/multitasking, battery, display, value for money).\n"
            "- Reference exact prices in INR (₹) and key hardware specifications.\n"
            "- If the user asks for a recommendation (e.g. 'which is better for X?'), give a decisive answer with reasons.\n"
            "- Keep your response structured, concise, and easy to read using Markdown bullet points."
        )

        messages = [SystemMessage(content=system_prompt)]

        context_text = f"COMPARED PRODUCTS:\n{product_texts}"
        if comparison_summary:
            context_text += f"\n\nINITIAL COMPARISON OVERVIEW:\n{comparison_summary}"

        messages.append(SystemMessage(content=context_text))

        # Add recent follow-up history
        if history:
            for h in history[-4:]:
                role = h.get("role")
                content = h.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=query))

        if not self.available or self.llm is None:
            return {
                "reply": f"Based on the compared products ({', '.join(p.get('brand', 'Product') for p in products)}), "
                         f"the {products[0].get('title')} offers a strong balance of specifications. "
                         f"Consider your budget and primary workflow (e.g. gaming vs daily productivity) when finalizing.",
                "winner_asin": products[0].get("asin"),
            }

        try:
            response = self.llm.invoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)

            return {
                "reply": reply_text,
                "winner_asin": products[0].get("asin"),
            }
        except Exception as exc:
            print(f"[LANGCHAIN COPILOT ERROR] compare_followup failed: {exc}")
            return {
                "reply": f"Regarding your question '{query}': Between the compared models, "
                         f"{products[0].get('title')} is a top contender. Check the detailed specs table above.",
                "winner_asin": products[0].get("asin"),
            }

    def select_tool(self, message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Classifies incoming user query into one of the specialized commerce tools:
        1. persona_iam_setter: /iam <text> to store/overwrite person's information in account
        2. persona_fetcher: /me information fetcher ('which laptop specs will be better for /me', 'who am i', 'give all info about me')
        3. assistant_identity: 'who are you', 'what are you'
        4. formatted_product_info: specs table, formatted overview, details of a product
        5. specific_product_query: direct technical/feature question (RAM, GPU, battery, upgradeability)
        6. comparison_best_output: side-by-side comparison, trade-offs, and winner recommendation
        7. personal_profile_query: personalized advice ('which is best for me', 'what should I buy', user requirements)
        8. none_query: gibberish, empty, or unintelligible query
        9. off_topic_query: non-commerce / non-shopping query (e.g. C++ Two Sum, math, general programming)
        """
        msg_lower = (message or "").strip().lower()
        if not msg_lower:
            return "none_query"

        # 1. /iam command -> Setting / overwriting person's information
        if msg_lower.startswith("/iam") or " /iam" in msg_lower:
            return "persona_iam_setter"

        # Check if user says `/me ` with descriptive text to set persona (e.g. "/me I am person A and I am...")
        if msg_lower.startswith("/me ") and len(msg_lower.split()) > 3:
            return "persona_iam_setter"

        # 2. Assistant identity questions ("who are you", "what are you", "who r u", "who made you")
        identity_phrases = [
            "who are you", "who r u", "what are you", "who created you",
            "what is your name", "who made you", "what can you do", "introduce yourself"
        ]
        if any(p in msg_lower for p in identity_phrases):
            return "assistant_identity"

        # 3. /me or Information Fetcher ("which laptop specs will be better for /me", "who am i", "give all info about me")
        me_fetch_indicators = [
            "/me", "who am i", "whoami", "about me",
            "information about me", "info about me", "data about me",
            "what do you know about me", "give all the information about me",
            "give all information about me", "give all info about me",
            "show my info", "show my profile", "my account information",
            "my personal information", "my persona", "specs for /me", "laptop for /me"
        ]
        if any(k in msg_lower for k in me_fetch_indicators):
            return "persona_fetcher"

        # 4. Check for off-topic queries (e.g. two sum, cpp, algorithm, general coding)
        off_topic_indicators = [
            "two sum", "twosum", "cpp code", "c++ code", "generate the cpp", "generate cpp",
            "write cpp", "write c++", "python code", "java code", "write a code", "generate code",
            "bubble sort", "binary search", "dijkstra", "dynamic programming", "leetcode",
            "write a poem", "write a story", "capital of", "who is ", "tell me a joke"
        ]
        if any(k in msg_lower for k in off_topic_indicators):
            # Check if they are actually asking for a laptop for that work
            if not any(w in msg_lower for w in ["laptop", "computer", "pc", "buy", "price", "store", "recommend"]):
                return "off_topic_query"

        # 5. Check for unintelligible or keyboard-mashing gibberish
        import re
        if len(msg_lower) <= 2 or re.match(r"^[^a-zA-Z0-9\s]+$", msg_lower):
            return "none_query"
        # Pure consonant mash (e.g. "asdfghjk", "zxcvbnm", "qwrtyp")
        words = msg_lower.split()
        if not any(v in msg_lower for v in "aeiou") and len(msg_lower) > 3:
            return "none_query"
        if any(len(w) >= 5 and not any(v in w for v in "aeiou") for w in words):
            return "none_query"

        # 6. Check for personal profile / recommendation queries
        persona_phrases = [
            "best for me", "which is best for me", "which should be best for me",
            "what is best for me", "what should i buy", "which laptop should i buy",
            "which one should i buy", "recommend for me", "suggest for me",
            "help me choose", "help me pick", "which one is good for me",
            "what do you recommend for me", "for my use", "for myself",
            "i am a student", "i'm a student", "i am a developer", "i'm a developer",
            "i am a programmer", "i'm a programmer", "i am a gamer", "i'm a gamer",
            "my budget is", "budget under", "looking for myself"
        ]
        if any(p in msg_lower for p in persona_phrases):
            return "persona_fetcher"

        # 7. Check for comparison
        compare_phrases = [
            "compare", " vs ", " vs. ", " versus ", "difference between",
            "which is better", "which one is better", "better between",
            "side by side", "best between", "compare these"
        ]
        if any(p in msg_lower for p in compare_phrases):
            return "comparison_best_output"

        # 8. Check for formatted product information
        info_phrases = [
            "tell me about", "specs of", "specifications of", "details of",
            "overview of", "hardware specs", "full specs", "product info",
            "what are the specs", "about this laptop", "about this product"
        ]
        if any(p in msg_lower for p in info_phrases):
            return "formatted_product_info"

        # 9. Check for specific feature/technical query
        specific_phrases = [
            "does it have", "does this have", "how much ram", "is it upgradeable",
            "battery life", "display refresh", "refresh rate", "screen resolution",
            "dedicated gpu", "graphics card", "thunderbolt", "weight", "weight in kg",
            "how heavy", "warranty", "can it run", "is it good for", "does it support"
        ]
        if any(p in msg_lower for p in specific_phrases):
            return "specific_product_query"

        # LLM classification fallback if available
        if self.available and self.llm:
            try:
                classify_prompt = (
                    "Classify this shopping assistant query into EXACTLY ONE category:\n"
                    "- persona_iam_setter (setting user personal info or profile using /iam)\n"
                    "- persona_fetcher (querying user's info, profile, or asking what is best for /me or for me)\n"
                    "- assistant_identity (asking who the assistant is or what it can do)\n"
                    "- formatted_product_info (asking for specs/overview/details of a product)\n"
                    "- specific_product_query (factual question about a spec, feature, or compatibility)\n"
                    "- comparison_best_output (comparing laptops or asking which is best between models)\n"
                    "- off_topic_query (coding algorithms like two sum, code generation, general non-store topics)\n"
                    "- none_query (unintelligible, nonsense, or gibberish)\n\n"
                    f"Query: \"{message}\"\n\n"
                    "Output ONLY the category name:"
                )
                res = self.llm.invoke([SystemMessage(content=classify_prompt)]).content.strip().lower()
                for cat in ["persona_iam_setter", "persona_fetcher", "assistant_identity",
                            "formatted_product_info", "specific_product_query", "comparison_best_output",
                            "off_topic_query", "none_query"]:
                    if cat in res:
                        return cat
            except Exception:
                pass

        return "specific_product_query"

    def chat(
        self,
        message: str,
        catalog_products: Optional[List[Dict[str, Any]]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        selected_asins: Optional[List[str]] = None,
        user_persona: str = "",
        user_id: Optional[int] = None,
        user_commerce_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Conversational assistant using a dedicated Tool Selector to route requests to:
        1. persona_iam_setter (/iam <text> under 100-200 characters, stored in account)
        2. persona_fetcher (/me information fetcher: account info or personalized laptop specs)
        3. assistant_identity (who are you)
        4. formatted_product_info
        5. specific_product_query
        6. comparison_best_output
        7. none_query (unintelligible queries)
        8. off_topic_query (like C++ two sum code)
        """
        if isinstance(catalog_products, dict):
            catalog_products = catalog_products.get("products", [])
        catalog_products = catalog_products or []
        history = history or []

        # 1. SELECT TOOL
        tool_name = self.select_tool(message, history)

        # 2. EXECUTE TOOL HANDLER
        if tool_name == "persona_iam_setter":
            return self._tool_persona_iam_setter(message, user_id, user_commerce_service)
        elif tool_name in ["persona_fetcher", "personal_profile_query"]:
            return self._tool_persona_fetcher(
                message, catalog_products, user_persona, user_id, user_commerce_service, tool_name
            )
        elif tool_name == "assistant_identity":
            return self._tool_assistant_identity()
        elif tool_name == "formatted_product_info":
            return self._tool_formatted_product_info(message, catalog_products)
        elif tool_name == "comparison_best_output":
            return self._tool_comparison_best_output(message, catalog_products, history)
        elif tool_name == "none_query":
            return self._tool_none_query(message, catalog_products)
        elif tool_name == "off_topic_query":
            return self._tool_off_topic_query(message)
        else:
            # specific_product_query
            return self._tool_specific_product_query(message, catalog_products, history)

    # -------------------------------------------------------------
    # SPECIALIZED TOOL HANDLERS
    # -------------------------------------------------------------

    def _tool_formatted_product_info(self, message: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Tool 1: Formatted product information with structured specs table."""
        if not products:
            return {
                "reply": "I couldn't locate specific products matching your request in the catalog. Try searching with a brand or model name.",
                "recommended_products": [],
                "tool_used": "formatted_product_info",
            }

        p = products[0]
        specs = p.get("specs") or {}
        price_inr = p.get("price_inr") or (p.get("price", 0) * 96.3)
        price_str = f"₹{price_inr:,.2f}" if price_inr else "Price N/A"

        reply = (
            f"### 📋 Hardware Specification & Product Overview\n\n"
            f"**{p.get('title')}**\n\n"
            f"| Specification | Hardware Details |\n"
            f"| :--- | :--- |\n"
            f"| **Brand** | {p.get('brand', 'Verified Brand')} |\n"
            f"| **Processor (CPU)** | {specs.get('cpu') or 'High-Performance Multicore CPU'} |\n"
            f"| **Graphics (GPU)** | {specs.get('gpu') or 'Integrated Graphics'} |\n"
            f"| **Memory (RAM)** | {specs.get('ram_gb', 'N/A')} GB DDR |\n"
            f"| **Storage** | {specs.get('storage_gb', 'N/A')} GB High-Speed NVMe SSD |\n"
            f"| **Display** | {specs.get('screen_size_inches', '15.6')}\" FHD Screen |\n"
            f"| **Price** | **{price_str}** *(Eligible for FREE Prime Delivery)* |\n"
            f"| **Rating** | {p.get('stars', 4.5)}★ ({p.get('reviews_count', 12)} customer ratings) |\n\n"
            f"#### 💡 Key Highlights:\n"
            f"- **Performance**: Equipped for smooth multitasking, productivity, and modern applications.\n"
            f"- **Value**: Competitive pricing in INR with verified manufacturer warranty.\n\n"
            f"Click **Buy Now** on the card below to proceed directly to secure checkout!"
        )

        return {
            "reply": reply,
            "recommended_products": products[:3],
            "tool_used": "formatted_product_info",
        }

    def _tool_specific_product_query(
        self, message: str, products: List[Dict[str, Any]], history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Tool 2: Specific technical or factual query about products."""
        if not self.available or not self.llm or not products:
            return self._fallback_chat(message, products)

        context_lines = [self._format_product_brief(p, i + 1) for i, p in enumerate(products[:4])]
        catalog_context = "\n".join(context_lines)

        system_prompt = (
            "You are an expert AI Hardware Engineer and Shopping Assistant.\n"
            "The customer is asking a specific technical or factual question about computers/laptops.\n"
            "Guidelines:\n"
            "- Answer their specific question directly in 2 to 4 sentences.\n"
            "- Cite exact specifications (e.g. RAM, GPU, CPU, battery, display) and prices in INR (₹) from the catalog.\n"
            "- If a feature is supported or upgradeable, state it clearly.\n"
            "- Keep your response concise, professional, and formatted in clean Markdown."
        )

        messages = [
            SystemMessage(content=system_prompt),
            SystemMessage(content=f"STORE CATALOG CONTEXT:\n{catalog_context}"),
            HumanMessage(content=message),
        ]

        try:
            response = self.llm.invoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)
            return {
                "reply": reply_text,
                "recommended_products": products[:3],
                "tool_used": "specific_product_query",
            }
        except Exception as exc:
            print(f"[LANGCHAIN COPILOT ERROR] specific_product_query failed: {exc}")
            return self._fallback_chat(message, products)

    def _tool_comparison_best_output(
        self, message: str, products: List[Dict[str, Any]], history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Tool 3: In-depth side-by-side comparison with trade-offs and best winner."""
        if len(products) < 2:
            return self._tool_formatted_product_info(message, products)

        res = self.compare_products(products[:3])
        return {
            "reply": res.get("analysis_markdown", "Side-by-side comparison generated."),
            "recommended_products": products[:3],
            "tool_used": "comparison_best_output",
            "winner_asin": res.get("winner_asin"),
        }

    def _tool_persona_iam_setter(
        self,
        message: str,
        user_id: Optional[int],
        user_commerce_service: Optional[Any],
    ) -> Dict[str, Any]:
        """
        Tool: Store or overwrite the person's information in account.
        Triggered by: /iam <text> or /me <text>
        """
        raw = message.strip()
        persona_text = ""
        for prefix in ["/iam:", "/iam", "/me:", "/me"]:
            if raw.lower().startswith(prefix):
                persona_text = raw[len(prefix):].strip()
                if persona_text.startswith(":") or persona_text.startswith("-"):
                    persona_text = persona_text[1:].strip()
                break

        if not persona_text and " /iam" in raw.lower():
            idx = raw.lower().find("/iam")
            persona_text = raw[idx + 4:].strip()
            if persona_text.startswith(":") or persona_text.startswith("-"):
                persona_text = persona_text[1:].strip()

        if not persona_text:
            return {
                "reply": (
                    "### ℹ️ How to Use `/iam`\n\n"
                    "Please provide your personal information after `/iam` (under 100–200 characters):\n\n"
                    "**Format:**\n"
                    "`/iam I am person A and I am a college student from XYZ college studying computer science.`\n\n"
                    "👉 Once sent, this information will be stored in your **Person's Information** window "
                    "alongside your account information. You can then ask: *\"Which laptop specs will be better for /me?\"*"
                ),
                "recommended_products": [],
                "tool_used": "persona_iam_setter",
                "persona_saved": False,
            }

        # Overwrite in database via user_commerce_service
        saved_persona = persona_text
        if user_commerce_service and user_id:
            saved_persona = user_commerce_service.update_user_persona(user_id, persona_text)

        reply = (
            "### ✅ Person Information Saved to Account\n\n"
            "Your details have been successfully stored in your **Account Information**:\n\n"
            f"> *\"{saved_persona}\"*\n\n"
            "- **Stored In:** Person's Information Window (alongside Account Details)\n"
            "- **How it works:** Whenever you ask *\"Which laptop specs will be better for /me?\"* or query with `/me`, "
            "I will fetch these details and recommend the optimal laptop hardware for you.\n"
            "- **To Overwrite:** Send `/iam <new text>` anytime, or update it directly in the Account Information window."
        )

        return {
            "reply": reply,
            "recommended_products": [],
            "tool_used": "persona_iam_setter",
            "persona_saved": True,
            "updated_persona": saved_persona,
        }

    def _tool_assistant_identity(self) -> Dict[str, Any]:
        """Tool: Explains who the AI Copilot is and how to use it."""
        reply = (
            "### 🤖 Agentic AI Shopping Copilot\n\n"
            "I am your **AI Shopping Copilot**, powered by LangChain and local Ollama GPU intelligence.\n\n"
            "Here is what I can do for you:\n"
            "- 👤 **Personalized Recommendations (`/me` & `/iam`):**\n"
            "  - Save your profile using: `/iam I am person A and I am a college student from XYZ college...`\n"
            "  - Then ask: *\"Which laptop specs will be better for /me?\"* to get customized hardware advice!\n"
            "- 📋 **Hardware Specs:** Ask for specifications, upgrades, RAM, or battery details on any laptop.\n"
            "- ⚖️ **Side-by-Side Comparison:** Compare 2 or more laptops with detailed trade-off matrices.\n"
            "- 💳 **Amazon Wallet & Rewards:** Track orders, manage wallet credits, and redeem diamonds.\n\n"
            "How can I assist your shopping today?"
        )
        return {
            "reply": reply,
            "recommended_products": [],
            "tool_used": "assistant_identity",
        }

    def _tool_persona_fetcher(
        self,
        message: str,
        products: List[Dict[str, Any]],
        user_persona: str,
        user_id: Optional[int],
        user_commerce_service: Optional[Any],
        tool_name: str = "persona_fetcher",
    ) -> Dict[str, Any]:
        """
        Tool: Information fetcher using /me and account information.
        - If person information is NOT found in account:
            Outputs: "use /iam ---text--- under 100-200 characters" to store details.
        - If person information IS found:
            - If asking about own data ("who am i", "give all information about me you have"):
                Fetches and displays full account & persona information.
            - If asking for laptop specs/recommendations ("which laptop specs will be better for /me"):
                Analyzes their persona and details recommended hardware specs + top catalog matches!
        """
        user_persona = (user_persona or "").strip()

        # Double check DB for latest persona
        if not user_persona and user_commerce_service and user_id:
            user_persona = (user_commerce_service.get_user_persona(user_id) or "").strip()

        # CASE A: PERSON INFORMATION NOT FOUND
        if not user_persona:
            reply = (
                "### ⚠️ No Person Information Found in Account\n\n"
                "I don't have any personal details saved for you yet!\n\n"
                "Please add your details using:\n"
                "👉 `use /iam ---text--- under 100-200 characters`\n\n"
                "**Example:**\n"
                "`/iam I am person A and I am a college student from XYZ college studying computer science.`\n\n"
                "Once you send this, it will be stored in your **Person's Information** window alongside your "
                "account information, and whenever you ask *\"Which laptop specs will be better for /me?\"*, "
                "I will use it to give you the perfect recommendation!"
            )
            return {
                "reply": reply,
                "recommended_products": products[:2] if products else [],
                "tool_used": tool_name,
                "persona_found": False,
            }

        # Fetch user account details from commerce service
        user_data = {}
        if user_commerce_service and user_id:
            user_data = user_commerce_service.get_user_by_id(user_id) or {}

        full_name = user_data.get("full_name") or "Valued Customer"
        email = user_data.get("email") or "account@amazon.com"
        wallet_bal = float(user_data.get("wallet_balance") or 0)
        diamonds = int(user_data.get("diamonds_balance") or 0)
        addr_line = user_data.get("address_line1")
        city = user_data.get("city")
        state = user_data.get("state")
        addr_str = f"{addr_line}, {city}, {state}" if addr_line else "Not set (Click 'Delivery Address' to add)"

        msg_l = message.lower().strip()
        is_info_query = any(k in msg_l for k in [
            "who am i", "whoami", "give all the information", "give all information",
            "give all info", "what do you know about me", "my information", "my info",
            "my details", "show my persona", "my profile", "tell me about me",
            "what is stored", "about me you have"
        ]) or msg_l == "/me"

        # CASE B: USER ASKS TO SEE ALL INFORMATION ABOUT THEMSELVES
        if is_info_query:
            reply = (
                "### 👤 Your Account & Person Information\n\n"
                "Here is all the personal and account information currently stored in your profile:\n\n"
                f"- **👤 Full Name:** {full_name}\n"
                f"- **📧 Email Address:** `{email}`\n"
                f"- **⭐ Membership:** Amazon Prime Member\n"
                f"- **💳 Amazon Wallet Balance:** ₹{wallet_bal:,.2f}\n"
                f"- **💎 Diamond Rewards:** {diamonds} Diamonds\n"
                f"- **📍 Saved Delivery Address:** {addr_str}\n\n"
                "#### 📝 Stored AI Person Profile (`/me`):\n"
                f"> *\"{user_persona}\"*\n\n"
                "---\n"
                "💡 **How to update:**\n"
                "- Send `/iam <new text>` (under 100–200 characters) in this chat to overwrite your persona.\n"
                "- Or open the **Account Information** window to view and edit your profile."
            )
            return {
                "reply": reply,
                "recommended_products": products[:2] if products else [],
                "tool_used": tool_name,
                "persona_found": True,
            }

        # CASE C: USER ASKS FOR HARDWARE SPECS / RECOMMENDATIONS FOR /me
        college_or_student = any(w in user_persona.lower() for w in ["college", "student", "university", "study", "studying"])
        dev_or_coding = any(w in user_persona.lower() for w in ["code", "coding", "developer", "programming", "cs", "computer science", "software"])
        gamer = any(w in user_persona.lower() for w in ["game", "gamer", "gaming", "fps", "aaa"])

        cpu_rec = "Intel Core i5 (12th/13th Gen) or AMD Ryzen 5/7 Hexa-core" if (college_or_student or dev_or_coding) else "Intel Core i7 / AMD Ryzen 7"
        ram_rec = "16GB DDR4/DDR5 (Essential for multitasking, IDEs, browser research, and smooth performance)"
        storage_rec = "512GB to 1TB PCIe NVMe SSD (fast boot times and ample space for projects & course material)"
        display_rec = "14\" to 15.6\" Full HD IPS (Anti-glare, comfortable for long study & coding sessions)"
        gpu_rec = "Dedicated NVIDIA GeForce RTX 3050 / 4050" if gamer else "Integrated Intel Iris Xe / AMD Radeon Graphics (energy-efficient for long battery life)"
        battery_rec = "6 to 8+ Hours Battery Life (lightweight design under 1.8 kg for carrying around campus/office)"

        reply = (
            f"### 🎯 Recommended Laptop Specifications for `/me`\n\n"
            f"Fetched from your saved account profile:\n"
            f"> *\"{user_persona}\"*\n\n"
            f"Based on your profile, here are the optimal laptop specifications tailored for your workload:\n\n"
            f"| Component | Recommended Specification | Why it's best for you |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **Processor (CPU)** | **{cpu_rec}** | Fast multicore performance for smooth multitasking, compiling code, and coursework. |\n"
            f"| **Memory (RAM)** | **{ram_rec}** | Ensures zero lag with multiple tabs, IDEs (VS Code/Android Studio), and productivity apps. |\n"
            f"| **Storage** | **{storage_rec}** | Ultra-responsive application loading with room for projects, videos, and datasets. |\n"
            f"| **Graphics (GPU)** | **{gpu_rec}** | Perfect balance between graphical workload capability and battery efficiency. |\n"
            f"| **Display & Portability**| **{display_rec}** | Crisp visuals with low blue light, easy to carry in a college backpack ({battery_rec}). |\n\n"
            f"#### 🛍️ Top Handpicked Laptops Matching Your Profile:\n"
            f"Here are the top matches currently available in our catalog. Click **Buy Now** to proceed to checkout!"
        )

        return {
            "reply": reply,
            "recommended_products": products[:3],
            "tool_used": tool_name,
            "persona_found": True,
        }

    def _tool_none_query(self, message: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Tool 5: Handles unintelligible / nonsense queries."""
        reply = (
            "I didn't quite catch that! As your **Agentic Shopping Copilot**, I am here to help you discover, compare, and choose laptops and computers.\n\n"
            "Here are a few things you can ask me:\n"
            "- 🔍 **Filter by Budget**: *\"Show me laptops under ₹50,000\"*\n"
            "- ⚡ **Filter by Specs**: *\"I need a gaming laptop with RTX 4060 and 16GB RAM\"*\n"
            "- ⚖️ **Compare Products**: *\"Compare HP 14 with Lenovo ThinkPad\"*\n"
            "- 🎯 **Personalized Fit**: *\"Which laptop is best for me?\"*"
        )
        return {
            "reply": reply,
            "recommended_products": products[:2],
            "tool_used": "none_query",
        }

    def _tool_off_topic_query(self, message: str) -> Dict[str, Any]:
        """Tool 6: Handles off-topic queries (e.g. C++ Two Sum) with friendly agentic note."""
        cpp_fallback = (
            "Here is the optimal C++ solution for the **Two Sum** problem using an unordered hash map ($O(n)$ time complexity):\n\n"
            "```cpp\n"
            "#include <vector>\n"
            "#include <unordered_map>\n\n"
            "class Solution {\n"
            "public:\n"
            "    std::vector<int> twoSum(std::vector<int>& nums, int target) {\n"
            "        std::unordered_map<int, int> numMap; // value -> index\n"
            "        \n"
            "        for (int i = 0; i < nums.size(); ++i) {\n"
            "            int complement = target - nums[i];\n"
            "            if (numMap.find(complement) != numMap.end()) {\n"
            "                return {numMap[complement], i};\n"
            "            }\n"
            "            numMap[nums[i]] = i;\n"
            "        }\n"
            "        return {}; // No pair found\n"
            "    }\n"
            "};\n"
            "```\n\n"
            "**Complexity Analysis:**\n"
            "- **Time Complexity**: $\\mathcal{O}(n)$ — Single pass through the array with $\\mathcal{O}(1)$ average hash table lookups.\n"
            "- **Space Complexity**: $\\mathcal{O}(n)$ — Extra memory for the hash map.\n\n"
            "---\n"
            "💡 **Shopping Copilot Note:**\n"
            "*If you write and compile C++ code or work on software development, I can recommend high-performance developer laptops equipped with fast multicore CPUs (Intel Core i7 / AMD Ryzen 7) and 16GB+ RAM to speed up your builds and IDEs! Let me know if you would like developer laptop recommendations.*"
        )

        if not self.available or not self.llm:
            return {
                "reply": cpp_fallback,
                "recommended_products": [],
                "tool_used": "off_topic_query",
            }

        try:
            system_prompt = (
                "You are an intelligent assistant. The user asked a non-shopping or general programming query.\n"
                "1. Answer their query accurately, helpfully, and concisely (e.g., if they asked for C++ code for two sum, provide clean, optimal C++ code with explanation).\n"
                "2. At the end, add a divider `---` followed by a polite note:\n"
                "'💡 **Shopping Copilot Note:** If you are running coding, algorithms, or software development workloads, I can help you find high-performance developer laptops with multicore CPUs and 16GB+ RAM to compile and run your code lightning fast! Let me know if you would like recommendations.'"
            )
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=message),
            ])
            reply_text = response.content if hasattr(response, "content") else str(response)

            return {
                "reply": reply_text,
                "recommended_products": [],
                "tool_used": "off_topic_query",
            }
        except Exception:
            return {
                "reply": cpp_fallback,
                "recommended_products": [],
                "tool_used": "off_topic_query",
            }

    def _extract_user_preferences(self, message: str) -> Optional[str]:
        """Extract user requirements from their message to store in user persona."""
        msg_l = message.lower()
        triggers = [
            "i am a ", "i'm a ", "my budget is", "budget under", "budget of",
            "need it for", "need a laptop for", "use it for", "looking for a laptop for",
            "want to buy for", "prefer ", "studying", "programming", "coding", "gaming"
        ]
        if any(t in msg_l for t in triggers):
            cleaned = message.strip()
            if len(cleaned) > 8:
                return cleaned
        return None

    def _fallback_comparison(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Deterministic fallback comparison when LLM is unavailable."""
        rows = []
        rows.append("| Feature | " + " | ".join(f"{p.get('brand', 'Product')} ({p.get('asin')})" for p in products) + " |")
        rows.append("| --- | " + " | ".join("---" for _ in products) + " |")

        # Price
        prices = []
        for p in products:
            price_inr = p.get("price_inr") or (p.get("price", 0) * 96.3)
            prices.append(f"₹{price_inr:,.2f}" if price_inr else "N/A")
        rows.append("| **Price** | " + " | ".join(prices) + " |")

        # RAM
        rams = [f"{p.get('specs', {}).get('ram_gb', 'N/A')} GB" for p in products]
        rows.append("| **RAM** | " + " | ".join(rams) + " |")

        # Storage
        storages = [f"{p.get('specs', {}).get('storage_gb', 'N/A')} GB" for p in products]
        rows.append("| **Storage** | " + " | ".join(storages) + " |")

        # GPU
        gpus = [str(p.get("specs", {}).get("gpu") or "Integrated") for p in products]
        rows.append("| **GPU** | " + " | ".join(gpus) + " |")

        # CPU
        cpus = [str(p.get("specs", {}).get("cpu") or "Standard Processor") for p in products]
        rows.append("| **CPU** | " + " | ".join(cpus) + " |")

        # Rating
        ratings = [f"{p.get('stars', 'N/A')}★ ({p.get('reviews_count', 0)} reviews)" for p in products]
        rows.append("| **Customer Rating** | " + " | ".join(ratings) + " |")

        table_md = "\n".join(rows)

        analysis = (
            f"### Side-by-Side Product Comparison\n\n"
            f"{table_md}\n\n"
            f"#### Recommendation:\n"
            f"- **Top Value**: [{products[0].get('title', 'Option 1')}](/checkout?asin={products[0].get('asin')})\n"
            f"- Review the specifications above to match your specific performance and budget requirements."
        )

        return {
            "summary": f"Comparison between {len(products)} products",
            "analysis_markdown": analysis,
            "winner_asin": products[0].get("asin") if products else None,
            "products_compared": [p.get("asin") for p in products],
        }

    def _fallback_chat(self, message: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Deterministic fallback chat when LLM is unavailable."""
        if products:
            top = products[0]
            price = top.get("price_inr") or (top.get("price", 0) * 96.3)
            reply = (
                f"I found {len(products)} products matching your query. "
                f"A great choice is **{top.get('title')}** at ₹{price:,.2f} "
                f"({top.get('stars', 4.5)}★ with {top.get('reviews_count', 0)} reviews). "
                f"You can add it to compare or click Buy Now to proceed directly to checkout."
            )
        else:
            reply = (
                "I am here to help you discover, compare, and select the best products. "
                "Try searching for specific requirements like 'RTX gaming laptop under ₹1.5L' "
                "or select products from the store to compare them side by side."
            )

        return {
            "reply": reply,
            "recommended_products": products[:4],
        }
