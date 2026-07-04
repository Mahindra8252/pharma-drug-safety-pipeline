import pytest
import pandas as pd
import numpy as np
from src.pipeline.analyze_gold import calculate_disproportionality

def test_safety_signal_statistics():
    """
    Verifies that the vectorized PRR, ROR, Yates' Chi2, and Confidence Interval 
    formulas compute correct outputs for a known contingency table.
    
    Test Matrix setup:
    N_total = 100 reports
    DrugA = 20 reports
    ReactionX = 15 reports
    Co-occurrence (a) = 10 reports
    
    Cell calculations:
    a = 10 (DrugA + ReactionX)
    b = N_drug - a = 10 (DrugA + Other Reactions)
    c = N_event - a = 5 (Other Drugs + ReactionX)
    d = N_total - a - b - c = 75 (Other Drugs + Other Reactions)
    
    Expected stats (Manual Calculation):
    PRR = (10/20) / (5/80) = 0.5 / 0.0625 = 8.0
    ROR = (10 * 75) / (10 * 5) = 15.0
    SE(ln(ROR)) = sqrt(1/10 + 1/10 + 1/5 + 1/75) = sqrt(0.41333) = 0.64291
    ROR Lower CI = exp(ln(15) - 1.96 * 0.64291) = exp(2.70805 - 1.2601) = 4.254
    ROR Upper CI = exp(ln(15) + 1.96 * 0.64291) = exp(2.70805 + 1.2601) = 52.887
    Chi2 Yates = 100 * (abs(10*75 - 10*5) - 50)^2 / (20 * 80 * 15 * 85)
               = 100 * 650^2 / 2040000 = 42250000 / 2040000 = 20.711
    """
    
    # 1. Create mock reports (N_total = 100)
    reports = [{"case_id": f"C-{i}"} for i in range(1, 101)]
    df_reports = pd.DataFrame(reports)
    
    # 2. Create mock drugs (20 reports have DrugA)
    # C-1 to C-20 have 'adalimumab' (DrugA)
    # C-21 to C-100 have 'ibuprofen' (DrugB)
    drugs = []
    for i in range(1, 21):
        drugs.append({"case_id": f"C-{i}", "drug_name": "adalimumab", "role": "Primary Suspect"})
    for i in range(21, 101):
        drugs.append({"case_id": f"C-{i}", "drug_name": "ibuprofen", "role": "Concomitant"})
    df_drugs = pd.DataFrame(drugs)
    
    # 3. Create mock reactions (15 reports have ReactionX)
    # Co-occurrence 'a': 10 reports (C-1 to C-10 have both 'adalimumab' and 'headache')
    # Reaction in other drug 'c': 5 reports (C-21 to C-25 have 'ibuprofen' and 'headache')
    reactions = []
    for i in range(1, 11):
        reactions.append({"case_id": f"C-{i}", "reaction_name": "headache"})
    for i in range(21, 26):
        reactions.append({"case_id": f"C-{i}", "reaction_name": "headache"})
    
    # Fill remaining reports with background reaction to complete database (total N=100)
    for i in range(11, 21):
        reactions.append({"case_id": f"C-{i}", "reaction_name": "nausea"})
    for i in range(26, 101):
        reactions.append({"case_id": f"C-{i}", "reaction_name": "nausea"})
    df_reactions = pd.DataFrame(reactions)
    
    # Run calculation
    df_signals = calculate_disproportionality(df_reports, df_drugs, df_reactions)
    
    # Extract target pair results
    target_signal = df_signals[
        (df_signals["drug_name"] == "adalimumab") & 
        (df_signals["reaction_name"] == "headache")
    ].iloc[0]
    
    # Assertions
    assert target_signal["a"] == 10
    assert target_signal["b"] == 10
    assert target_signal["c"] == 5
    assert target_signal["d"] == 75
    
    # Verify calculated ratios
    assert np.isclose(target_signal["prr"], 8.0, atol=0.01)
    assert np.isclose(target_signal["ror"], 15.0, atol=0.01)
    assert np.isclose(target_signal["ror_ci_lower"], 4.254, atol=0.01)
    assert np.isclose(target_signal["ror_ci_upper"], 52.887, atol=0.01)
    assert np.isclose(target_signal["chi2"], 20.711, atol=0.01)
    assert target_signal["is_signal"] == 1
