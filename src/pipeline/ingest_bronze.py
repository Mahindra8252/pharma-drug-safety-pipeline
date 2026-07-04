import json
import logging
import time
import random
import requests
from src.config import BRONZE_DIR, OPENFDA_API_KEY, ALL_TRACKED_DRUGS

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# openFDA API endpoint
FDA_EVENT_URL = "https://api.fda.gov/drug/event.json"

import datetime

def get_latest_received_date() -> str:
    """Queries the database to find the latest received_date for incremental ingestion."""
    # Import DatabaseManager dynamically to avoid circular dependencies
    from src.utils.db_manager import DatabaseManager
    db = DatabaseManager()
    try:
        res = db.execute_query("SELECT MAX(received_date) as max_date FROM reports")
        if not res.empty and res.iloc[0]["max_date"]:
            max_date = str(res.iloc[0]["max_date"]).strip()
            if len(max_date) == 8 and max_date.isdigit():
                return max_date
    except Exception as e:
        logger.debug(f"Could not read max received date, defaulting: {e}")
    return "20240101" # Default start date

def fetch_fda_data(drug_name: str, start_date: str, end_date: str, limit: int = 1000, skip: int = 0) -> dict:
    """
    Fetches raw adverse event records from openFDA API for a specific drug and date range.
    """
    search_query = f'patient.drug.medicinalproduct:"{drug_name}"'
    search_query += f" AND receivedate:[{start_date} TO {end_date}]"
    
    params = {
        "search": search_query,
        "limit": limit,
        "skip": skip
    }
    
    if OPENFDA_API_KEY:
        params["api_key"] = OPENFDA_API_KEY
        
    logger.info(f"Querying openFDA for '{drug_name}' ({start_date} TO {end_date}, limit={limit}, skip={skip})...")
    
    try:
        response = requests.get(FDA_EVENT_URL, params=params, timeout=30)
        
        # Handle rate limiting (status 429)
        if response.status_code == 429:
            logger.warning("Rate limit hit. Sleeping for 5 seconds...")
            time.sleep(5)
            # Retry once
            response = requests.get(FDA_EVENT_URL, params=params, timeout=30)
            
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            logger.info(f"No records found for drug '{drug_name}' in range {start_date} to {end_date} (skip={skip}).")
            return {}
        else:
            logger.error(f"Error querying openFDA API: {response.status_code} - {response.text}")
            return {}
            
    except Exception as e:
        logger.error(f"Exception during openFDA query: {str(e)}")
        return {}

def generate_mock_bronze_data():
    """
    Generates high-quality mock FAERS JSON data as a fallback to ensure 
    the pipeline is testable without internet or API key limits.
    """
    logger.info("Generating mock Bronze data as fallback...")
    
    # Define common reactions for specific drugs to create simulated signals
    drug_reaction_profiles = {
        "adalimumab": [("injection site reaction", 0.35), ("sinusitis", 0.15), ("headache", 0.10), ("psoriasis", 0.08), ("fatigue", 0.12)],
        "infliximab": [("infusion related reaction", 0.30), ("tuberculosis", 0.08), ("hepatic function abnormal", 0.12), ("nausea", 0.15), ("arthralgia", 0.15)],
        "etanercept": [("injection site reaction", 0.30), ("nasopharyngitis", 0.20), ("headache", 0.15), ("cellulitis", 0.08)],
        "ustekinumab": [("nasopharyngitis", 0.25), ("headache", 0.15), ("fatigue", 0.10), ("injection site erythema", 0.10)],
        "certolizumab pegol": [("injection site reaction", 0.25), ("upper respiratory tract infection", 0.20), ("arthralgia", 0.15)],
        "golimumab": [("upper respiratory tract infection", 0.25), ("alanin aminotransferase increased", 0.12), ("bronchitis", 0.10)],
        
        "ibuprofen": [("gastritis", 0.25), ("nausea", 0.20), ("acute kidney injury", 0.15), ("dyspepsia", 0.20), ("headache", 0.10)],
        "naproxen": [("gastritis", 0.22), ("gastrointestinal hemorrhage", 0.12), ("acute kidney injury", 0.10), ("nausea", 0.15)],
        "celecoxib": [("dyspepsia", 0.20), ("myocardial infarction", 0.08), ("gastroesophageal reflux disease", 0.15), ("abdominal pain", 0.15)],
        "aspirin": [("gastrointestinal hemorrhage", 0.25), ("tinnitus", 0.15), ("nausea", 0.15), ("dyspepsia", 0.15)],
        "acetaminophen": [("hepatic failure", 0.20), ("hepatotoxicity", 0.20), ("transaminases increased", 0.15), ("nausea", 0.15), ("vomiting", 0.15)]
    }
    
    # Generic background reactions that occur across all drugs randomly
    background_reactions = ["dizziness", "rash", "pruritus", "somnolence", "diarrhea", "constipation", "insomnia", "anxiety"]
    
    mock_results = []
    
    # Generate 10,000 total mock cases (approx 900 per drug)
    for case_idx in range(1, 10001):
        case_id = f"US-MOCK-{20240000 + case_idx}"
        receive_date = f"2024{random.randint(1, 12):02d}{random.randint(1, 28):02d}"
        
        # Pick primary suspect drug
        primary_drug = random.choice(list(drug_reaction_profiles.keys()))
        
        # Determine patient characteristics
        age = round(random.normalvariate(52, 18), 1)
        age = max(1.0, min(100.0, age)) # Bound age
        sex = random.choice(["1", "2"]) # 1=Male, 2=Female
        country = random.choice(["US", "US", "US", "CA", "GB", "DE", "FR", "JP"])
        
        # Determine reactions based on drug profile + background noise
        reactions = []
        profile = drug_reaction_profiles[primary_drug]
        
        # Sample from profile
        for rx, prob in profile:
            if random.random() < prob:
                reactions.append({"reactionmeddrapt": rx.upper()})
                
        # Add background reaction occasionally
        if not reactions or random.random() < 0.25:
            reactions.append({"reactionmeddrapt": random.choice(background_reactions).upper()})
            
        # Compile drug list (primary suspect + occasionally concomitant controls)
        drugs = [
            {
                "medicinalproduct": primary_drug.upper(),
                "drugcharacterization": "1" # Suspect
            }
        ]
        
        # Add a concomitant drug 30% of the time
        if random.random() < 0.3:
            concomitant_drug = random.choice(ALL_TRACKED_DRUGS)
            if concomitant_drug != primary_drug:
                drugs.append({
                    "medicinalproduct": concomitant_drug.upper(),
                    "drugcharacterization": "2" # Concomitant
                })
                
        # Seriousness outcome
        is_serious = random.choice(["1", "2"]) # 1=Serious, 2=Non-serious
        outcomes = []
        if is_serious == "1":
            outcomes = [random.choice(["death", "hospitalization", "other", "disability"])]
            
        mock_record = {
            "safetyreportid": case_id,
            "receivedate": receive_date,
            "seriousness": is_serious,
            "patient": {
                "patientonsetage": str(int(age)) if random.random() < 0.9 else None,
                "patientsex": sex,
                "reaction": reactions,
                "drug": drugs
            }
        }
        
        # Add seriousness detail if serious
        if outcomes:
            for outcome in outcomes:
                mock_record[outcome] = "1"
                
        mock_results.append(mock_record)
        
    # Save the mock results to bronze
    file_path = BRONZE_DIR / "raw_events_fallback_mock.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"results": mock_results}, f, indent=2)
    logger.info(f"Successfully wrote {len(mock_results)} mock cases to {file_path}")

def run_ingestion(max_records_per_drug: int = 5000):
    """
    Main entry point to execute the Bronze ingestion layer.
    Performs incremental ingestion by checking the database for the latest received report date
    and downloading only new records.
    """
    logger.info("Starting openFDA adverse events Bronze Ingestion stage...")
    
    # 1. Determine incremental range
    start_date = get_latest_received_date()
    end_date = datetime.datetime.today().strftime("%Y%m%d")
    
    logger.info(f"Incremental Ingestion Range: {start_date} TO {end_date}")
    
    real_data_fetched = False
    
    # Limit skip loop pages dynamically based on max_records_per_drug
    # If anonymous (no key), we restrict to 1 page to prevent 403 rate block
    max_pages = max(1, max_records_per_drug // 1000) if OPENFDA_API_KEY else 1
    page_size = 1000
    
    for drug in ALL_TRACKED_DRUGS:
        skip = 0
        page = 0
        
        while page < max_pages:
            # Output filepath includes date range and page for clear tracking
            file_name = f"raw_events_{drug.replace(' ', '_')}_{start_date}_to_{end_date}_page{page}.json"
            file_path = BRONZE_DIR / file_name
            
            # Skip if we already downloaded this exact range segment locally
            if file_path.exists():
                logger.info(f"Local Bronze file {file_name} already exists. Skipping download.")
                real_data_fetched = True
                skip += page_size
                page += 1
                continue
                
            data = fetch_fda_data(drug, start_date=start_date, end_date=end_date, limit=page_size, skip=skip)
            
            if data and "results" in data:
                results_count = len(data["results"])
                if results_count > 0:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"Saved {results_count} records for '{drug}' to {file_name}")
                    real_data_fetched = True
                    
                    # If we got fewer records than page_size, we reached the end
                    if results_count < page_size:
                        break
                        
                    skip += page_size
                    page += 1
                    # Rate limit politeness
                    time.sleep(1)
                else:
                    break
            else:
                # No data or error (e.g. rate limit, no more results)
                break
                
    # If no real data could be fetched across any drug, check for fallback mock data
    fallback_file = BRONZE_DIR / "raw_events_fallback_mock.json"
    if not real_data_fetched and not fallback_file.exists():
        logger.warning("No real data was fetched and no fallback files exist. Running mock generator.")
        generate_mock_bronze_data()
    elif not real_data_fetched:
        logger.info("Mock fallback file already exists. Skipping mock generation.")
        
    logger.info("Bronze Ingestion Stage complete.")

if __name__ == "__main__":
    run_ingestion()
