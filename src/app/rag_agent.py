import logging
import json
import re

try:
    import google.generativeai as genai
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False

from src.config import GEMINI_API_KEY, GOLD_DIR
from src.utils.db_manager import DatabaseManager
from src.utils.drug_dictionary import DrugDictionary

logger = logging.getLogger(__name__)

# --- CALLABLE TOOLS FOR GEMINI FUNCTION CALLING ---

def get_drug_signals(drug_name: str) -> str:
    """
    Retrieves statistically significant adverse event safety signals for a specific drug.
    
    Args:
        drug_name: The brand name or generic name of the drug (e.g. 'Humira' or 'adalimumab').
        
    Returns:
        A JSON string containing active safety signals (with cases, PRR, ROR, Chi-Square values).
    """
    # Load dynamic drug list to bypass Python module caching
    from src.config import DATA_DIR, TARGET_DRUGS, CONTROL_DRUGS
    all_tracked_drugs = TARGET_DRUGS + CONTROL_DRUGS
    active_drugs_path = DATA_DIR / "active_drugs.json"
    if active_drugs_path.exists():
        try:
            with open(active_drugs_path, "r") as f:
                drug_data = json.load(f)
                if "TARGET_DRUGS" in drug_data and "CONTROL_DRUGS" in drug_data:
                    all_tracked_drugs = drug_data["TARGET_DRUGS"] + drug_data["CONTROL_DRUGS"]
        except Exception:
            pass

    std_name = DrugDictionary.standardize(drug_name)
    if std_name not in all_tracked_drugs:
        return json.dumps({
            "error": f"Drug '{drug_name}' (standardized as '{std_name}') is not in the tracked drug list. "
                     f"Currently tracked drugs are: {', '.join(all_tracked_drugs)}."
        })
        
    db = DatabaseManager()
    signals_query = """
        SELECT reaction_name, a, prr, ror, ror_ci_lower, ror_ci_upper, chi2 
        FROM safety_signals 
        WHERE drug_name = ? AND is_signal = 1
        ORDER BY prr DESC
        LIMIT 10
    """
    df = db.execute_query(signals_query, (std_name,))
    
    if df.empty:
        return json.dumps({
            "drug_name": std_name,
            "message": "No statistically significant safety signals flagged in the database for this drug."
        })
        
    results = []
    for _, row in df.iterrows():
        results.append({
            "reaction_name": row["reaction_name"],
            "cases_count": int(row["a"]),
            "PRR": float(row["prr"]),
            "ROR": float(row["ror"]),
            "ROR_95_CI": [float(row["ror_ci_lower"]), float(row["ror_ci_upper"])],
            "chi_square_yates": float(row["chi2"])
        })
        
    return json.dumps({
        "drug_name": std_name,
        "active_safety_signals": results
    })

def list_tracked_drugs() -> str:
    """
    Returns the list of target and control drugs currently tracked by FAERSight.
    
    Returns:
        A JSON string containing lists of Target Drug Classes and Control/Comparison Set drugs.
    """
    # Load dynamic drug list to bypass Python module caching
    from src.config import DATA_DIR, TARGET_DRUGS, CONTROL_DRUGS
    target_drugs = TARGET_DRUGS
    control_drugs = CONTROL_DRUGS
    active_drugs_path = DATA_DIR / "active_drugs.json"
    if active_drugs_path.exists():
        try:
            with open(active_drugs_path, "r") as f:
                drug_data = json.load(f)
                if "TARGET_DRUGS" in drug_data:
                    target_drugs = drug_data["TARGET_DRUGS"]
                if "CONTROL_DRUGS" in drug_data:
                    control_drugs = drug_data["CONTROL_DRUGS"]
        except Exception:
            pass

    return json.dumps({
        "target_drug_classes": target_drugs,
        "control_comparison_set": control_drugs
    })

def compare_drugs(drug_name1: str, drug_name2: str) -> str:
    """
     Compares computed adverse-event safety signals and disproportionality metrics 
    between two tracked drugs.
    
    Args:
        drug_name1: The brand or generic name of the first drug.
        drug_name2: The brand or generic name of the second drug.
        
    Returns:
        A JSON string comparing the safety signals of the two drugs.
    """
    # Load dynamic drug list to bypass Python module caching
    from src.config import DATA_DIR, TARGET_DRUGS, CONTROL_DRUGS
    all_tracked_drugs = TARGET_DRUGS + CONTROL_DRUGS
    active_drugs_path = DATA_DIR / "active_drugs.json"
    if active_drugs_path.exists():
        try:
            with open(active_drugs_path, "r") as f:
                drug_data = json.load(f)
                if "TARGET_DRUGS" in drug_data and "CONTROL_DRUGS" in drug_data:
                    all_tracked_drugs = drug_data["TARGET_DRUGS"] + drug_data["CONTROL_DRUGS"]
        except Exception:
            pass

    std1 = DrugDictionary.standardize(drug_name1)
    std2 = DrugDictionary.standardize(drug_name2)
    
    errors = []
    if std1 not in all_tracked_drugs:
        errors.append(f"Drug '{drug_name1}' (standardized as '{std1}') is not tracked.")
    if std2 not in all_tracked_drugs:
        errors.append(f"Drug '{drug_name2}' (standardized as '{std2}') is not tracked.")
        
    if errors:
        return json.dumps({"error": " | ".join(errors)})
        
    db = DatabaseManager()
    query = """
        SELECT reaction_name, a, prr, ror, chi2 
        FROM safety_signals 
        WHERE drug_name = ? AND is_signal = 1
        ORDER BY prr DESC
    """
    df1 = db.execute_query(query, (std1,))
    df2 = db.execute_query(query, (std2,))
    
    sigs1 = []
    if not df1.empty:
        for _, r in df1.iterrows():
            sigs1.append({
                "reaction_name": r["reaction_name"],
                "cases_count": int(r["a"]),
                "PRR": float(r["prr"]),
                "ROR": float(r["ror"]),
                "chi_square_yates": float(r["chi2"])
            })
            
    sigs2 = []
    if not df2.empty:
        for _, r in df2.iterrows():
            sigs2.append({
                "reaction_name": r["reaction_name"],
                "cases_count": int(r["a"]),
                "PRR": float(r["prr"]),
                "ROR": float(r["ror"]),
                "chi_square_yates": float(r["chi2"])
            })
            
    reactions1 = {r["reaction_name"] for r in sigs1}
    reactions2 = {r["reaction_name"] for r in sigs2}
    overlapping_reactions = list(reactions1.intersection(reactions2))
    
    return json.dumps({
        "comparison": {
            std1: {
                "active_signal_count": len(sigs1),
                "signals": sigs1[:10]
            },
            std2: {
                "active_signal_count": len(sigs2),
                "signals": sigs2[:10]
            },
            "overlapping_safety_signals": overlapping_reactions
        }
    })

# --- SAFETY RAG AGENT CLASS ---

class SafetyRAGAgent:
    """
    Structured RAG Agent that maps natural language queries to database queries,
    retrieves statistical safety signals via Gemini function calling, and generates responses.
    """
    def __init__(self):
        self.db = DatabaseManager()
        self.api_key = GEMINI_API_KEY
        self.has_llm = bool(self.api_key) and GOOGLE_GENAI_AVAILABLE
        self.model = None
        self.model_name = "gemini-3.5-flash"
        
        self.system_instruction = (
            "You are FAERSight Assistant, a clinical pharmacovigilance safety expert reviewing adverse event reports from the FDA FAERS database.\n"
            "Your role is to analyze and present safety signal statistics from the database.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Grounding: You must NEVER invent or guess any numbers, case counts, or ratios (PRR, ROR, Chi-Square). Every number, statistic, or ratio in your response must be derived directly and exactly from a tool call result.\n"
            "2. Clinical Disclaimers & Guardrails:\n"
            "   - You must never provide medical or clinical advice, dosing guidance, or tell a user whether a drug is \"safe for them\" or should be taken.\n"
            "   - You must always include a standing disclaimer at the end of every response stating:\n"
            "     \"FAERSight is a pharmacovigilance research and monitoring tool and does not provide clinical or medical advice. Patients should consult their healthcare provider before making any changes to their medication.\"\n"
            "3. Scope: If asked about a drug that is not tracked, or if a tool indicates a drug is not tracked, state so clearly and list the available tracked drugs. Do not make up safety signals or statistics for untracked drugs.\n"
            "4. Tone: Maintain a highly professional, clinical, objective, and data-driven tone. Distinguish clearly between statistically significant safety signals and background noise."
        )
        
        if self.has_llm:
            try:
                genai.configure(api_key=self.api_key)
                tools = [get_drug_signals, list_tracked_drugs, compare_drugs]
                self.model = genai.GenerativeModel(
                    model_name=self.model_name,
                    tools=tools,
                    system_instruction=self.system_instruction
                )
                logger.info("Google Gemini RAG Client initialized with gemini-3.5-flash.")
            except Exception as e:
                logger.error(f"Error configuring Gemini client: {str(e)}")
                self.has_llm = False

    def _extract_drugs(self, query: str) -> list:
        """Helper to extract all mentioned tracked drugs (generics or brands) from the user query using strict boundaries."""
        # Load dynamic list
        from src.config import DATA_DIR, TARGET_DRUGS, CONTROL_DRUGS
        all_tracked_drugs = TARGET_DRUGS + CONTROL_DRUGS
        active_drugs_path = DATA_DIR / "active_drugs.json"
        if active_drugs_path.exists():
            try:
                with open(active_drugs_path, "r") as f:
                    drug_data = json.load(f)
                    if "TARGET_DRUGS" in drug_data and "CONTROL_DRUGS" in drug_data:
                        all_tracked_drugs = drug_data["TARGET_DRUGS"] + drug_data["CONTROL_DRUGS"]
            except Exception:
                pass

        query_lower = query.lower()
        extracted = set()
        
        # 1. Check direct generics
        for generic in DrugDictionary.GENERICS:
            if re.search(r'(?<![a-z])' + re.escape(generic) + r'(?![a-z])', query_lower):
                extracted.add(generic)
                
        # 2. Check brand names and map to generics
        for brand, generic in DrugDictionary.BRAND_TO_GENERIC.items():
            if re.search(r'(?<![a-z])' + re.escape(brand) + r'(?![a-z])', query_lower):
                extracted.add(generic)
                
        return sorted(list(extracted))

    def start_chat_session(self):
        """Starts a multi-turn chat session with automatic function calling enabled, handling model fallback."""
        if not self.has_llm:
            return None
            
        tools = [get_drug_signals, list_tracked_drugs, compare_drugs]
        
        try:
            chat = self.model.start_chat(enable_automatic_function_calling=True)
            return chat
        except Exception as e:
            logger.warning(f"Failed to start chat with {self.model_name}: {e}. Falling back to gemini-2.5-flash.")
            try:
                self.model_name = "gemini-2.5-flash"
                self.model = genai.GenerativeModel(
                    model_name=self.model_name,
                    tools=tools,
                    system_instruction=self.system_instruction
                )
                return self.model.start_chat(enable_automatic_function_calling=True)
            except Exception as ex:
                logger.error(f"Failed to initialize fallback gemini-2.5-flash model: {ex}")
                self.has_llm = False
                return None

    def send_message_with_fallback(self, chat, user_query: str) -> str:
        """Sends a message to the chat session, falling back to gemini-2.5-flash if gemini-3.5-flash fails."""
        try:
            response = chat.send_message(user_query)
            return response.text
        except Exception as e:
            err_str = str(e).lower()
            if self.model_name == "gemini-3.5-flash" and ("not found" in err_str or "404" in err_str or "permission" in err_str or "400" in err_str or "not available" in err_str):
                logger.warning(f"Error calling {self.model_name}: {e}. Falling back to gemini-2.5-flash.")
                self.model_name = "gemini-2.5-flash"
                tools = [get_drug_signals, list_tracked_drugs, compare_drugs]
                try:
                    self.model = genai.GenerativeModel(
                        model_name=self.model_name,
                        tools=tools,
                        system_instruction=self.system_instruction
                    )
                    new_chat = self.model.start_chat(enable_automatic_function_calling=True)
                    response = new_chat.send_message(user_query)
                    
                    # Update chat session reference in streamlit if running in context
                    try:
                        import streamlit as st
                        st.session_state.chat_session = new_chat
                    except Exception:
                        pass
                        
                    return response.text
                except Exception as ex:
                    logger.error(f"Fallback to gemini-2.5-flash failed: {ex}")
                    raise ex
            else:
                raise e

    def get_offline_response(self, user_query: str) -> str:
        """Generates offline response by extracting drugs and calling database tools directly."""
        drugs = self._extract_drugs(user_query)
        
        # Load dynamic list for disclaimer options
        from src.config import DATA_DIR, TARGET_DRUGS, CONTROL_DRUGS
        all_tracked_drugs = TARGET_DRUGS + CONTROL_DRUGS
        active_drugs_path = DATA_DIR / "active_drugs.json"
        if active_drugs_path.exists():
            try:
                with open(active_drugs_path, "r") as f:
                    drug_data = json.load(f)
                    if "TARGET_DRUGS" in drug_data and "CONTROL_DRUGS" in drug_data:
                        all_tracked_drugs = drug_data["TARGET_DRUGS"] + drug_data["CONTROL_DRUGS"]
            except Exception:
                pass

        disclaimer = (
            "\n\n*Disclaimer: FAERSight is a pharmacovigilance research and monitoring tool and does not provide clinical or medical advice. "
            "Patients should consult their healthcare provider before making any changes to their medication.*"
        )
        
        if not drugs:
            return (
                "### [Offline RAG Mode]\n"
                "*(To enable natural language Q&A, please add a `GEMINI_API_KEY` to your `.env` file.)*\n\n"
                "I couldn't identify any specific tracked drugs from your query. "
                f"Please ask about one of the tracked drugs, such as: **{', '.join(all_tracked_drugs[:4])}**."
                + disclaimer
            )
            
        if len(drugs) >= 2:
            drug1, drug2 = drugs[0], drugs[1]
            comp_res = json.loads(compare_drugs(drug1, drug2))
            
            if "error" in comp_res:
                return f"### [Offline RAG Mode]\n\n{comp_res['error']}" + disclaimer
                
            comp_data = comp_res["comparison"]
            msg = (
                f"### [Offline RAG Comparison Mode]\n"
                f"*(To enable comparative natural language Q&A, please add a `GEMINI_API_KEY` to your `.env` file.)*\n\n"
                f"Comparing safety signal profiles of **{drug1.capitalize()}** vs **{drug2.capitalize()}**:\n\n"
                f"1. **{drug1.capitalize()}** has **{comp_data[drug1]['active_signal_count']}** statistically significant safety signals.\n"
                f"2. **{drug2.capitalize()}** has **{comp_data[drug2]['active_signal_count']}** statistically significant safety signals.\n\n"
            )
            
            overlapping = comp_data["overlapping_safety_signals"]
            if overlapping:
                msg += f"**Overlapping Safety Risks:** both drugs show statistically significant safety signals for: **{', '.join([r.title() for r in overlapping])}**.\n"
            else:
                msg += "**No Overlapping Risks:** there are no overlapping safety signals between these two drugs in the database.\n"
                
            return msg + disclaimer
            
        # Single drug
        drug_name = drugs[0]
        signals_res = json.loads(get_drug_signals(drug_name))
        
        if "error" in signals_res:
            return f"### [Offline RAG Mode]\n\n{signals_res['error']}" + disclaimer
            
        msg = (
            f"### [Offline RAG Mode]\n"
            f"*(To enable natural language Q&A, please add a `GEMINI_API_KEY` to your `.env` file.)*\n\n"
            f"**Grounded Pharmacovigilance Data for {drug_name.capitalize()}:**\n\n"
        )
        
        if "active_safety_signals" in signals_res:
            msg += "#### Flagged Adverse Events:\n"
            for row in signals_res["active_safety_signals"]:
                msg += (
                    f"*   **{row['reaction_name'].title()}**: Flagged with **{row['cases_count']} reports**. "
                    f"PRR = **{row['PRR']:.2f}** | ROR = **{row['ROR']:.2f}** (95% CI: {row['ROR_95_CI'][0]:.1f}-{row['ROR_95_CI'][1]:.1f}) "
                    f"and Yates' Chi-Square is **{row['chi_square_yates']:.2f}**.\n"
                )
        else:
            msg += signals_res.get("message", "No significant safety signals flagged.")
            
        return msg + disclaimer
