import os
from pathlib import Path
from dotenv import load_dotenv

# Find the project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / ".env")

# Define Data Directories (Medallion Architecture Layers)
DATA_DIR = PROJECT_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

# Ensure all directories exist
for directory in [BRONZE_DIR, SILVER_DIR, GOLD_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# API Keys & Configurations
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DB_URI = os.getenv("DB_URI", "")

# Fallback to Streamlit secrets if running in Streamlit Cloud context
try:
    import streamlit as st
    if "GEMINI_API_KEY" in st.secrets:
        GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    if "OPENFDA_API_KEY" in st.secrets:
        OPENFDA_API_KEY = st.secrets["OPENFDA_API_KEY"]
    if "DB_URI" in st.secrets:
        DB_URI = st.secrets["DB_URI"]
except Exception:
    pass

# If DB_URI is not set, default to a local SQLite database in the Gold layer
if not DB_URI:
    DB_URI = f"sqlite:///{GOLD_DIR / 'safety_signals.db'}"

# Standard parameters for drug safety ingestion
# Target drug classes (Biologics / TNF Inhibitors)
TARGET_DRUGS = [
    "adalimumab",
    "infliximab",
    "etanercept",
    "ustekinumab",
    "certolizumab pegol",
    "golimumab"
]

# Standard control / comparison drug set (commonly used NSAIDs and others to form a baseline)
CONTROL_DRUGS = [
    "ibuprofen",
    "naproxen",
    "celecoxib",
    "aspirin",
    "acetaminophen"
]

# Load dynamic drug list if active_drugs.json exists in DATA_DIR
import json
active_drugs_path = DATA_DIR / "active_drugs.json"
if active_drugs_path.exists():
    try:
        with open(active_drugs_path, "r") as f:
            drug_data = json.load(f)
            if "TARGET_DRUGS" in drug_data:
                TARGET_DRUGS = drug_data["TARGET_DRUGS"]
            if "CONTROL_DRUGS" in drug_data:
                CONTROL_DRUGS = drug_data["CONTROL_DRUGS"]
    except Exception:
        pass

# Combined list of drugs to monitor
ALL_TRACKED_DRUGS = TARGET_DRUGS + CONTROL_DRUGS
