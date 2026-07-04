import logging
import numpy as np
import pandas as pd
from src.config import SILVER_DIR
from src.utils.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

def calculate_disproportionality(df_reports: pd.DataFrame, 
                                df_drugs: pd.DataFrame, 
                                df_reactions: pd.DataFrame) -> pd.DataFrame:
    """
    Computes PRR, ROR, 95% Confidence Intervals, and Chi-Square for all drug-reaction pairs.
    Uses vectorization for high-speed processing.
    """
    logger.info("Calculating disproportionality metrics (Gold layer)...")
    
    # 1. Calculate global counts
    N_total = len(df_reports)
    if N_total == 0:
        logger.error("No reports found to analyze.")
        return pd.DataFrame()
        
    # Get total cases containing each drug (N_drug = a + b)
    drug_totals = df_drugs.groupby("drug_name").size().rename("N_drug")
    
    # Get total cases containing each reaction (N_event = a + c)
    reaction_totals = df_reactions.groupby("reaction_name").size().rename("N_event")
    
    # Merge drugs and reactions on case_id to find co-occurrences
    co_occurrences = pd.merge(df_drugs, df_reactions, on="case_id")
    
    # Group by drug-reaction pair to get observed counts 'a'
    df_signals = co_occurrences.groupby(["drug_name", "reaction_name"]).size().rename("a").reset_index()
    
    # 2. Map marginal totals into the drug-reaction pairs
    df_signals = df_signals.merge(drug_totals, on="drug_name", how="left")
    df_signals = df_signals.merge(reaction_totals, on="reaction_name", how="left")
    
    # 3. Calculate contingency table cells: a, b, c, d
    # a = observed count of (Drug, Reaction)
    # b = reports with Drug but WITHOUT Reaction (N_drug - a)
    # c = reports with Reaction but WITHOUT Drug (N_event - a)
    # d = reports with NEITHER Drug nor Reaction (N_total - a - b - c)
    #   Simplifies to: N_total - N_drug - N_event + a
    a = df_signals["a"].astype(float)
    N_drug = df_signals["N_drug"].astype(float)
    N_event = df_signals["N_event"].astype(float)
    
    b = N_drug - a
    c = N_event - a
    d = N_total - N_drug - N_event + a
    
    # 4. Handle zeros using Continuity Correction (add 0.5 to cells if any cell is 0)
    # This prevents division-by-zero errors in ROR/PRR calculations.
    zero_cells = (a == 0) | (b == 0) | (c == 0) | (d == 0)
    
    a_corrected = np.where(zero_cells, a + 0.5, a)
    b_corrected = np.where(zero_cells, b + 0.5, b)
    c_corrected = np.where(zero_cells, c + 0.5, c)
    d_corrected = np.where(zero_cells, d + 0.5, d)
    
    # 5. Compute PRR
    # PRR = (a / (a + b)) / (c / (c + d))
    prr = (a_corrected / (a_corrected + b_corrected)) / (c_corrected / (c_corrected + d_corrected))
    
    # 6. Compute ROR & Standard Error & 95% Confidence Intervals
    # ROR = (a * d) / (b * c)
    ror = (a_corrected * d_corrected) / (b_corrected * c_corrected)
    
    # SE(ln(ROR)) = sqrt(1/a + 1/b + 1/c + 1/d)
    se_ln_ror = np.sqrt((1.0 / a_corrected) + (1.0 / b_corrected) + (1.0 / c_corrected) + (1.0 / d_corrected))
    
    ror_ci_lower = np.exp(np.log(ror) - 1.96 * se_ln_ror)
    ror_ci_upper = np.exp(np.log(ror) + 1.96 * se_ln_ror)
    
    # 7. Compute Chi-Square with Yates' continuity correction
    # Chi2 = N * (max(0, |a*d - b*c| - N/2))^2 / ((a+b)*(c+d)*(a+c)*(b+d))
    numerator = N_total * np.power(np.maximum(0.0, np.abs(a * d - b * c) - (N_total / 2.0)), 2)
    denominator = (a + b) * (c + d) * (a + c) * (b + d)
    
    # Prevent divide by zero in chi-square
    chi2 = np.where(denominator > 0, numerator / denominator, 0.0)
    
    # Assign calculated metrics
    df_signals["b"] = b.astype(int)
    df_signals["c"] = c.astype(int)
    df_signals["d"] = d.astype(int)
    df_signals["prr"] = np.round(prr, 3)
    df_signals["ror"] = np.round(ror, 3)
    df_signals["ror_ci_lower"] = np.round(ror_ci_lower, 3)
    df_signals["ror_ci_upper"] = np.round(ror_ci_upper, 3)
    df_signals["chi2"] = np.round(chi2, 3)
    
    # 8. Define Flagging Thresholds (MHRA safety signal criteria)
    # - a >= 3 reports
    # - PRR >= 2.0
    # - Chi2 >= 3.84 (critical value for alpha = 0.05, 1 dof)
    is_signal = (df_signals["a"] >= 3) & (df_signals["prr"] >= 2.0) & (df_signals["chi2"] >= 3.84)
    df_signals["is_signal"] = is_signal.astype(int)
    
    # Sort signals by strength of association (PRR) and case count
    df_signals = df_signals.sort_values(by=["is_signal", "prr", "a"], ascending=[False, False, False])
    
    logger.info(f"Calculated safety signals for {len(df_signals)} drug-reaction pairs. "
                f"Flagged {df_signals['is_signal'].sum()} active safety signals.")
    
    return df_signals

def run_gold_analysis():
    """
    Loads Silver data, computes disproportionality metrics, and saves to SQL database.
    """
    logger.info("Starting Gold analysis and Database loading stage...")
    
    # Define Silver input paths
    reports_path = SILVER_DIR / "reports.csv"
    drugs_path = SILVER_DIR / "report_drugs.csv"
    reactions_path = SILVER_DIR / "report_reactions.csv"
    
    if not (reports_path.exists() and drugs_path.exists() and reactions_path.exists()):
        logger.error("Silver layer files are missing. Run Cleaning/Silver stage first.")
        return
        
    # Read Silver data
    df_reports = pd.read_csv(reports_path)
    df_drugs = pd.read_csv(drugs_path)
    df_reactions = pd.read_csv(reactions_path)
    
    # Calculate safety signals
    df_signals = calculate_disproportionality(df_reports, df_drugs, df_reactions)
    
    if df_signals.empty:
        logger.warning("No signals computed. Database loading skipped.")
        return
        
    # Initialize Database and Load Tables
    db = DatabaseManager()
    db.initialize_schema(force=True)
    
    logger.info("Loading tables into the database...")
    db.save_dataframe(df_reports, "reports", if_exists="replace")
    db.save_dataframe(df_drugs, "report_drugs", if_exists="replace")
    db.save_dataframe(df_reactions, "report_reactions", if_exists="replace")
    db.save_dataframe(df_signals, "safety_signals", if_exists="replace")
    
    logger.info("Gold Layer processing and database loading complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    run_gold_analysis()
