import pytest
import pandas as pd
from src.utils.drug_dictionary import DrugDictionary
from src.pipeline.clean_silver import extract_case_details

def test_drug_standardization():
    """Verify that messy drug names map correctly to standardized generics."""
    assert DrugDictionary.standardize("Humira Pen 40mg") == "adalimumab"
    assert DrugDictionary.standardize("ADALIMUMAB-ADAZ") == "adalimumab"
    assert DrugDictionary.standardize("Humira") == "adalimumab"
    assert DrugDictionary.standardize("remicade vial") == "infliximab"
    assert DrugDictionary.standardize("Enbrel PFS") == "etanercept"
    assert DrugDictionary.standardize("Stelara 90mg") == "ustekinumab"
    assert DrugDictionary.standardize("Cimzia syringe") == "certolizumab pegol"
    assert DrugDictionary.standardize("Simponi Aria") == "golimumab"
    assert DrugDictionary.standardize("Advil Liqui-Gels") == "ibuprofen"
    assert DrugDictionary.standardize("Aleve") == "naproxen"
    assert DrugDictionary.standardize("Celebrex 200mg") == "celecoxib"
    assert DrugDictionary.standardize("Tylenol Extra Strength") == "acetaminophen"
    assert DrugDictionary.standardize("Paracetamol") == "acetaminophen"
    
    # Check unknown drug fallback
    assert DrugDictionary.standardize("Lipitor") == "unknown"
    assert DrugDictionary.standardize("") == "unknown"
    assert DrugDictionary.standardize(None) == "unknown"

def test_extract_case_details():
    """Verify raw report JSON details are correctly parsed and normalized."""
    mock_report = {
        "safetyreportid": "US-123456",
        "receivedate": "20240510",
        "seriousness": "1",
        "death": "1",
        "hospitalization": "1",
        "occurcountry": "CA",
        "patient": {
            "patientonsetage": "45",
            "patientsex": "2"
        }
    }
    
    details = extract_case_details(mock_report)
    
    assert details["case_id"] == "US-123456"
    assert details["case_version"] == 1
    assert details["received_date"] == "20240510"
    assert details["age"] == 45.0
    assert details["sex"] == "Female"
    assert details["country"] == "CA"
    assert details["seriousness"] == 1
    assert "Death" in details["serious_outcome"]
    assert "Hospitalization" in details["serious_outcome"]

def test_case_deduplication():
    """Verify that multiple versions of the same case are deduplicated, keeping the highest safetyreportversion."""
    mock_cases = [
        {"case_id": "US-001", "case_version": 1, "received_date": "20240101", "age": 50},
        {"case_id": "US-001", "case_version": 3, "received_date": "20240103", "age": 52}, # Highest version
        {"case_id": "US-001", "case_version": 2, "received_date": "20240102", "age": 51},
        {"case_id": "US-002", "case_version": 1, "received_date": "20240101", "age": 30},
    ]
    
    df = pd.DataFrame(mock_cases)
    
    # Run the sort and drop duplicates logic
    df = df.sort_values(by=["case_id", "case_version"])
    df_dedup = df.drop_duplicates(subset=["case_id"], keep="last")
    
    assert len(df_dedup) == 2
    
    # Verify that for US-001, version 3 is retained (age 52)
    case_1 = df_dedup[df_dedup["case_id"] == "US-001"].iloc[0]
    assert case_1["case_version"] == 3
    assert case_1["age"] == 52
    
    # Verify that for US-002, version 1 is retained
    case_2 = df_dedup[df_dedup["case_id"] == "US-002"].iloc[0]
    assert case_2["case_version"] == 1
