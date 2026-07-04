import json
import logging
from pathlib import Path
import pandas as pd
from src.config import BRONZE_DIR, SILVER_DIR, ALL_TRACKED_DRUGS
from src.utils.drug_dictionary import DrugDictionary

logger = logging.getLogger(__name__)

def extract_case_details(report: dict) -> dict:
    """Extracts top-level report details from a FAERS record."""
    case_id = report.get("safetyreportid")
    if not case_id:
        return None
        
    received_date = report.get("receivedate", "")
    
    # Parse demographics
    patient = report.get("patient", {})
    age_raw = patient.get("patientonsetage")
    age = None
    if age_raw:
        try:
            # age unit check (1 = decade, 2 = year, 3 = month, etc. Year is default)
            # For simplicity, if it's digit, cast to float.
            age = float(age_raw)
        except ValueError:
            pass
            
    sex = patient.get("patientsex", "U") # U = Unknown, 1 = Male, 2 = Female
    if sex == "1":
        sex = "Male"
    elif sex == "2":
        sex = "Female"
    else:
        sex = "Unknown"
        
    country = report.get("occurcountry", "Unknown")
    
    # Seriousness check
    seriousness_raw = report.get("seriousness")
    seriousness = 1 if seriousness_raw == "1" else 0
    
    # Seriousness outcomes
    outcomes = []
    if report.get("death") == "1":
        outcomes.append("Death")
    if report.get("hospitalization") == "1":
        outcomes.append("Hospitalization")
    if report.get("lifethreatening") == "1":
        outcomes.append("Life Threatening")
    if report.get("disability") == "1":
        outcomes.append("Disability")
    if report.get("congenitalanomoly") == "1":
        outcomes.append("Congenital Anomaly")
        
    outcome_str = ", ".join(outcomes) if outcomes else "Other Serious" if seriousness == 1 else "Non-Serious"
    
    # Extract safetyreportversion (defaulting to 1 if missing)
    version_raw = report.get("safetyreportversion", "1")
    try:
        case_version = int(version_raw)
    except (ValueError, TypeError):
        case_version = 1
        
    return {
        "case_id": case_id,
        "case_version": case_version,
        "received_date": received_date,
        "age": age,
        "sex": sex,
        "country": country,
        "seriousness": seriousness,
        "serious_outcome": outcome_str
    }

def process_bronze_to_silver():
    """
    Reads Bronze raw JSON files, flattens, deduplicates, and standardizes.
    Saves results as normalized tables in Silver.
    """
    logger.info("Starting Silver cleaning and standardization stage...")
    
    # Check for raw files in Bronze
    json_files = list(BRONZE_DIR.glob("*.json"))
    if not json_files:
        logger.error("No JSON files found in Bronze layer. Run Ingestion stage first.")
        return
        
    all_reports = []
    all_drugs = []
    all_reactions = []
    
    for file_path in json_files:
        logger.info(f"Processing Bronze file: {file_path.name}...")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            results = data.get("results", [])
            for report in results:
                # 1. Extract Case Details
                case = extract_case_details(report)
                if not case:
                    continue
                
                # 2. Extract and Standardize Drugs
                patient = report.get("patient", {})
                drugs_list = patient.get("drug", [])
                
                has_tracked_drug = False
                case_drugs = []
                
                for drug in drugs_list:
                    raw_product = drug.get("medicinalproduct", "")
                    # Standardize using our dictionary
                    std_name = DrugDictionary.standardize(raw_product)
                    
                    if std_name in ALL_TRACKED_DRUGS:
                        has_tracked_drug = True
                        role_code = drug.get("drugcharacterization", "2")
                        role = "Primary Suspect" if role_code == "1" else "Concomitant"
                        
                        case_drugs.append({
                            "case_id": case["case_id"],
                            "drug_name": std_name,
                            "role": role
                        })
                
                # If the report doesn't contain any of our monitored drugs, skip it
                if not has_tracked_drug:
                    continue
                    
                # 3. Extract Reactions
                reactions_list = patient.get("reaction", [])
                case_reactions = []
                for rx in reactions_list:
                    rx_raw = rx.get("reactionmeddrapt", "")
                    if rx_raw:
                        # Standardize reaction to lowercase for comparison consistency
                        rx_clean = rx_raw.strip().lower()
                        case_reactions.append({
                            "case_id": case["case_id"],
                            "reaction_name": rx_clean
                        })
                        
                # Skip cases with no reactions reported
                if not case_reactions:
                    continue
                    
                # Add to aggregate lists
                all_reports.append(case)
                all_drugs.extend(case_drugs)
                all_reactions.extend(case_reactions)
                
        except Exception as e:
            logger.error(f"Error parsing file {file_path.name}: {str(e)}")
            
    if not all_reports:
        logger.warning("No valid reports extracted from Bronze layer data.")
        return
        
    # Create DataFrames
    df_reports = pd.DataFrame(all_reports)
    df_drugs = pd.DataFrame(all_drugs)
    df_reactions = pd.DataFrame(all_reactions)
    
    # --- Deduplication (Silver Quality Gate) ---
    logger.info(f"Extracted {len(df_reports)} raw report entries. Starting deduplication...")
    
    # Standard FAERS deduplication: keep the record with the highest case version for any case_id
    # Ensure case_version is sorted ascending
    df_reports = df_reports.sort_values(by=["case_id", "case_version"])
    # Drop duplicates, keeping the last (highest version)
    df_reports = df_reports.drop_duplicates(subset=["case_id"], keep="last")
    
    # Filter drugs and reactions tables to match only deduplicated reports
    valid_case_ids = set(df_reports["case_id"])
    df_drugs = df_drugs[df_drugs["case_id"].isin(valid_case_ids)].drop_duplicates()
    df_reactions = df_reactions[df_reactions["case_id"].isin(valid_case_ids)].drop_duplicates()
    
    logger.info(f"Deduplication complete. Remaining records: {len(df_reports)} cases, "
                f"{len(df_drugs)} drug entries, {len(df_reactions)} reaction entries.")
    
    # Save processed CSVs to Silver Layer
    reports_path = SILVER_DIR / "reports.csv"
    drugs_path = SILVER_DIR / "report_drugs.csv"
    reactions_path = SILVER_DIR / "report_reactions.csv"
    
    df_reports.to_csv(reports_path, index=False)
    df_drugs.to_csv(drugs_path, index=False)
    df_reactions.to_csv(reactions_path, index=False)
    
    logger.info(f"Silver layer files written successfully:\n"
                f" - Reports: {reports_path}\n"
                f" - Drugs: {drugs_path}\n"
                f" - Reactions: {reactions_path}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    process_bronze_to_silver()
