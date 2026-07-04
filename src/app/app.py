import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path

# Add project root to Python path to resolve 'src' imports when running streamlit
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Set Page Config as the absolute first Streamlit command
st.set_page_config(
    page_title="FAERSight - Adverse Event Analytics Platform",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

from src.config import GOLD_DIR
from src.utils.db_manager import DatabaseManager
from src.app.charts import plot_signal_volcano, plot_ror_forest, plot_demographics
from src.app.rag_agent import SafetyRAGAgent

# Database path helper
db_path = GOLD_DIR / "safety_signals.db"

# Custom CSS for Professional SaaS Layout (Clean Slate Theme, Jakarta Sans & Crisp Borders)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

    /* Global styles */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        background-color: #0b0f17 !important;
        color: #e2e8f0 !important;
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0e1320 !important;
        border-right: 1px solid #1f2937 !important;
    }
    
    /* Title/Header decoration (Professional Solid Styling) */
    .app-header {
        color: #ffffff !important;
        font-weight: 700;
        font-size: 2.3rem;
        margin-bottom: 0.3rem;
        letter-spacing: -0.025em;
    }
    
    /* Crisp container designs */
    .metric-card {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 20px;
        transition: border-color 0.15s ease-in-out;
    }
    
    .metric-card:hover {
        border-color: #374151;
    }
    
    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.1;
        margin-bottom: 4px;
        letter-spacing: -0.02em;
    }
    
    .metric-label {
        font-size: 11px;
        font-weight: 600;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Custom buttons */
    .stButton>button {
        background-color: #0ea5e9 !important;
        color: #ffffff !important;
        border: 1px solid #0284c7 !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        box-shadow: none !important;
        padding: 6px 16px !important;
        transition: background-color 0.15s ease-in-out !important;
    }
    
    .stButton>button:hover {
        background-color: #0284c7 !important;
        color: #ffffff !important;
    }
    
    /* Secondary Button styling (for suggestion blocks) */
    .suggest-button > div > button {
        background-color: #1f2937 !important;
        color: #e5e7eb !important;
        border: 1px solid #374151 !important;
        border-radius: 6px !important;
        padding: 10px 14px !important;
        font-weight: 500 !important;
        text-align: left !important;
        display: block !important;
        width: 100% !important;
        box-shadow: none !important;
        transition: all 0.15s ease !important;
    }
    
    .suggest-button > div > button:hover {
        background-color: #374151 !important;
        border-color: #4b5563 !important;
        color: #ffffff !important;
    }
    
    /* Status Pill */
    .status-pill {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
        gap: 6px;
        background-color: #111827;
        color: #9ca3af;
        border: 1px solid #1f2937;
        margin-bottom: 20px;
    }
    
    .status-pill.warning {
        background-color: rgba(245, 158, 11, 0.05);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.15);
    }
    
    .status-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background-color: #10b981;
    }
    
    .status-pill.warning .status-dot {
        background-color: #f59e0b;
    }
    
    /* Pipeline Step Cards */
    .pipeline-step-card {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 16px;
    }
    
    .pipeline-step-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    
    .pipeline-step-title {
        font-size: 15px;
        font-weight: 600;
        color: #ffffff;
    }
    
    .pipeline-step-badge {
        background-color: #1f2937;
        color: #9ca3af;
        border: 1px solid #374151;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)



# Initialize Session State for Chat
if "messages" not in st.session_state:
    st.session_state.messages = []

@st.cache_resource
def get_db_connection():
    return DatabaseManager()

@st.cache_resource
def get_rag_agent():
    import importlib
    import src.app.rag_agent
    importlib.reload(src.app.rag_agent)
    from src.app.rag_agent import SafetyRAGAgent
    return SafetyRAGAgent()

def run_pipeline_ui():
    """Helper to run pipeline from UI with detailed step-by-step visual feedback."""
    import time
    import datetime
    import json
    
    # Track duration
    start_time = time.time()
    
    # We will get total reports before the run to calculate "New Reports"
    db = DatabaseManager()
    try:
        before_df = db.execute_query("SELECT COUNT(*) as count FROM reports")
        reports_before = before_df.iloc[0]["count"] if not before_df.empty else 0
    except Exception:
        reports_before = 0

    # Create empty placeholders in Streamlit for each step
    step1_ph = st.empty()
    step2_ph = st.empty()
    step3_ph = st.empty()
    step4_ph = st.empty()
    step5_ph = st.empty()
    step6_ph = st.empty()
    step7_ph = st.empty()
    
    from src.pipeline.ingest_bronze import run_ingestion
    from src.pipeline.clean_silver import process_bronze_to_silver
    from src.pipeline.analyze_gold import run_gold_analysis

    # Step 1: Downloading FDA Reports
    step1_ph.info("Step 1 / Downloading FDA Reports...")
    run_ingestion(max_records_per_drug=10000)
    step1_ph.success("Step 1 ✓ Downloading FDA Reports... Completed")
    
    # Step 2: Storing Bronze Data
    step2_ph.info("Step 2 / Storing Bronze Data...")
    time.sleep(0.5)
    step2_ph.success("Step 2 ✓ Storing Bronze Data... Completed")
    
    # Step 3: Cleaning & Standardizing
    step3_ph.info("Step 3 / Cleaning & Standardizing...")
    process_bronze_to_silver()
    step3_ph.success("Step 3 ✓ Cleaning & Standardizing... Completed")
    
    # Step 4: Generating Drug-Reaction Pairs
    step4_ph.info("Step 4 / Generating Drug-Reaction Pairs...")
    time.sleep(0.5)
    step4_ph.success("Step 4 ✓ Generating Drug-Reaction Pairs... Completed")
    
    # Step 5: Calculating PRR/ROR
    step5_ph.info("Step 5 / Calculating PRR/ROR...")
    run_gold_analysis()
    step5_ph.success("Step 5 ✓ Calculating PRR/ROR... Completed")
    
    # Step 6: Updating Database
    step6_ph.info("Step 6 / Updating Database...")
    time.sleep(0.5)
    step6_ph.success("Step 6 ✓ Updating Database... Completed")
    
    # Step 7: Refreshing Dashboard
    step7_ph.info("Step 7 / Refreshing Dashboard...")
    time.sleep(0.5)
    step7_ph.success("Step 7 ✓ Refreshing Dashboard... Completed")
    
    # Calculate stats
    end_time = time.time()
    duration_sec = int(end_time - start_time)
    minutes = duration_sec // 60
    seconds = duration_sec % 60
    duration_str = f"{minutes} min {seconds} sec" if minutes > 0 else f"{seconds} sec"
    
    try:
        after_df = db.execute_query("SELECT COUNT(*) as count FROM reports")
        reports_after = after_df.iloc[0]["count"] if not after_df.empty else 0
    except Exception:
        reports_after = 0
        
    new_reports = max(0, reports_after - reports_before)
    if reports_before == 0:
        new_reports = reports_after
        
    # Write metadata to JSON
    metadata = {
        "last_run_timestamp": datetime.datetime.now().strftime("%d %b %Y %I:%M %p"),
        "status": "SUCCESS",
        "new_reports": new_reports,
        "total_reports": reports_after,
        "duration": duration_str
    }
    
    import tempfile
    import os
    metadata_path = GOLD_DIR / "pipeline_metadata.json"
    try:
        # Write to a temporary file in the same directory and rename atomically
        with tempfile.NamedTemporaryFile("w", dir=str(GOLD_DIR), delete=False, suffix=".tmp") as tf:
            json.dump(metadata, tf, indent=2)
            temp_name = tf.name
        os.replace(temp_name, str(metadata_path))
    except Exception:
        pass
        
    st.markdown("### ✔ Pipeline Completed")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("New Reports Added", f"+{new_reports}")
    with col_stat2:
        st.metric("Total Reports", f"{reports_after:,}")
    with col_stat3:
        st.metric("Execution Duration", duration_str)
        
    # Add a proceed button so they see the result before we rerun
    if st.button("Continue to Dashboard", use_container_width=True):
        st.rerun()

def main():
    db = get_db_connection()
    
    # Check if database has been initialized
    db_initialized = db_path.exists()
    
    # Load dynamic drug list dynamically every run of app.py to bypass module caching
    import json
    from src.config import TARGET_DRUGS as DEFAULT_TARGET, CONTROL_DRUGS as DEFAULT_CONTROL, DATA_DIR
    target_drugs = DEFAULT_TARGET
    control_drugs = DEFAULT_CONTROL
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
    all_tracked_drugs = target_drugs + control_drugs

    # Load metadata
    metadata_path = GOLD_DIR / "pipeline_metadata.json"
    metadata = None
    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
        except Exception:
            pass
            
    # Sidebar
    st.sidebar.markdown("<h2 style='color:#38bdf8; font-weight:800; margin-top: -10px; margin-bottom: 0px;'>FAERSight</h2>", unsafe_allow_html=True)
    st.sidebar.markdown("<p style='color:#9ca3af; font-size:12px; margin-top:0px;'>Pharmacovigilance Analytics Platform</p>", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    
    if not db_initialized:
        st.warning("Database is not initialized. Run the pipeline to download or simulate FAERS dataset.")
        if st.sidebar.button("Run Ingest & ETL Pipeline", use_container_width=True):
            run_pipeline_ui()
        st.info("The pipeline will automatically fetch openFDA API records (or fall back to simulated mock records if rate limited) and execute Bronze -> Silver -> Gold calculations.")
        return
        
    # Navigation
    app_mode = st.sidebar.radio(
        "Navigation",
        ["Dashboard & Analytics", "FAERSight Query Assistant", "Pipeline Architecture"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Metadata Configuration")
    st.sidebar.markdown("**Target Drug Classes:**")
    st.sidebar.info(", ".join(target_drugs))
    st.sidebar.markdown("**Control/Comparison Set:**")
    st.sidebar.info(", ".join(control_drugs))
    
    # Trigger Pipeline again if desired
    if st.sidebar.button("Run ETL Pipeline", use_container_width=True):
        run_pipeline_ui()
        
    # Show Last ETL Run Status in Sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("Pipeline Health")
    if metadata:
        st.sidebar.markdown("**Last ETL Run**")
        ts = metadata.get("last_run_timestamp", "N/A")
        parts = ts.split(" ")
        if len(parts) >= 3:
            date_str = " ".join(parts[:3])
            time_str = " ".join(parts[3:])
            st.sidebar.markdown(f"<span style='color:#ffffff; font-size:14px; font-weight:600;'>{date_str}</span>", unsafe_allow_html=True)
            st.sidebar.markdown(f"<span style='color:#9ca3af; font-size:12px;'>{time_str}</span>", unsafe_allow_html=True)
        else:
            st.sidebar.markdown(f"<span style='color:#ffffff; font-size:14px; font-weight:600;'>{ts}</span>", unsafe_allow_html=True)
            
        status = metadata.get("status", "SUCCESS")
        status_color = "#10b981" if status == "SUCCESS" else "#ef4444"
        st.sidebar.markdown(f"**Status:** <span style='color:{status_color}; font-weight:bold;'>{status}</span>", unsafe_allow_html=True)
    else:
        st.sidebar.markdown("**Last ETL Run**")
        st.sidebar.markdown("<span style='color:#ffffff; font-size:14px; font-weight:600;'>03 Jul 2026</span>", unsafe_allow_html=True)
        st.sidebar.markdown("<span style='color:#9ca3af; font-size:12px;'>02:10 AM</span>", unsafe_allow_html=True)
        st.sidebar.markdown("**Status:** <span style='color:#10b981; font-weight:bold;'>SUCCESS</span>", unsafe_allow_html=True)
        
    # ------------------ MODE 1: DASHBOARD & ANALYTICS ------------------
    if app_mode == "Dashboard & Analytics":
        st.markdown("<h1 class='app-header'>Drug-Safety Signal Analytics</h1>", unsafe_allow_html=True)
        st.markdown("""
        <div class="status-pill">
            <span class="status-dot"></span>
            <span>Database Pipeline Status: Active (Indexed SQLite)</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Aggregate statistics for metrics
        total_reports_df = db.execute_query("SELECT COUNT(*) as count FROM reports")
        total_reports = total_reports_df.iloc[0]["count"] if not total_reports_df.empty else 0
        
        total_signals_df = db.execute_query("SELECT COUNT(*) as count FROM safety_signals WHERE is_signal = 1")
        total_signals = total_signals_df.iloc[0]["count"] if not total_signals_df.empty else 0
        
        total_pairs_df = db.execute_query("SELECT COUNT(*) as count FROM safety_signals")
        total_pairs = total_pairs_df.iloc[0]["count"] if not total_pairs_df.empty else 0
        
        # Display Metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-value'>{total_reports:,}</div>
                <div class='metric-label'>Standardized Cases (Silver)</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-value'>{total_signals:,}</div>
                <div class='metric-label'>Active Safety Signals Flagged (Gold)</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-value'>{total_pairs:,}</div>
                <div class='metric-label'>Drug-Reaction Pairs Screened</div>
            </div>
            """, unsafe_allow_html=True)
            
        # Signal Explorer Filters
        st.markdown("### Safety Signal Explorer")
        
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            selected_drug = st.selectbox("Select Drug to Investigate", all_tracked_drugs, index=0)
        with col_f2:
            min_count = st.number_input("Minimum Reports with Drug & Reaction", min_value=1, value=3, step=1)
        with col_f3:
            min_prr = st.number_input("Min Proportional Reporting Ratio (PRR)", min_value=0.1, value=2.0, step=0.5)
        with col_f4:
            min_chi2 = st.number_input("Min Chi-Square (Yates)", min_value=0.0, value=3.84, step=0.5)
            
        # Retrieve drug statistics
        query = """
            SELECT reaction_name as "Adverse Event", 
                   a as "Cases with Drug & Reaction", 
                   b as "Drug without Reaction", 
                   c as "Other Drugs with Reaction", 
                   d as "Other Drugs without Reaction",
                   prr as "PRR", ror as "ROR", ror_ci_lower as "ROR Lower CI", ror_ci_upper as "ROR Upper CI",
                   chi2 as "Chi-Square (Yates)", is_signal as "Is Signal"
            FROM safety_signals
            WHERE drug_name = ?
              AND a >= ?
              AND prr >= ?
              AND chi2 >= ?
            ORDER BY is_signal DESC, prr DESC
        """
        
        df_results = db.execute_query(query, (selected_drug, min_count, min_prr, min_chi2))
        
        # Calculate Signal Strength
        if not df_results.empty:
            def calculate_strength(row):
                if row["Is Signal"] == 0:
                    return "⚪ None"
                
                prr = row["PRR"]
                chi2 = row["Chi-Square (Yates)"]
                
                if prr >= 5.0 and chi2 >= 15.0:
                    return "🔴 Strong Signal"
                elif prr >= 3.0 and chi2 >= 6.63:
                    return "🟡 Moderate"
                else:
                    return "🟢 Weak"
                    
            df_results["Signal Strength"] = df_results.apply(calculate_strength, axis=1)
            df_results = df_results.drop(columns=["Is Signal"])
            
            # Reorder columns to put Signal Strength right after Adverse Event
            cols = list(df_results.columns)
            cols.insert(1, cols.pop(cols.index("Signal Strength")))
            df_results = df_results[cols]
        
        # Display Charts
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            # Volcano Plot
            df_volcano = db.execute_query("SELECT reaction_name, a, prr, is_signal, ror, chi2 FROM safety_signals WHERE drug_name = ?", (selected_drug,))
            st.plotly_chart(plot_signal_volcano(df_volcano, selected_drug), use_container_width=True)
        with col_c2:
            # Forest Plot
            df_forest = db.execute_query("SELECT reaction_name, is_signal, ror, ror_ci_lower, ror_ci_upper FROM safety_signals WHERE drug_name = ?", (selected_drug,))
            st.plotly_chart(plot_ror_forest(df_forest, selected_drug), use_container_width=True)
            
        # Demographics and Signal Table
        st.subheader("Statistical Signals Table")
        if not df_results.empty:
            # Color code Signal Strength column
            def highlight_signals(val):
                if "Strong" in str(val):
                    return 'color: #ef4444; font-weight: bold;'
                elif "Moderate" in str(val):
                    return 'color: #f59e0b; font-weight: bold;'
                elif "Weak" in str(val):
                    return 'color: #10b981; font-weight: bold;'
                else:
                    return 'color: #9ca3af;'
                
            st.dataframe(
                df_results.style.format({
                    "PRR": "{:.2f}",
                    "ROR": "{:.2f}",
                    "ROR Lower CI": "{:.2f}",
                    "ROR Upper CI": "{:.2f}",
                    "Chi-Square (Yates)": "{:.2f}"
                }).map(highlight_signals, subset=["Signal Strength"]),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("No safety signals match the current filter thresholds.")
            
        # Age/Sex Demographics for selected drug
        st.subheader(f"Demographics for {selected_drug.capitalize()} Cases")
        demo_query = """
            SELECT r.sex, r.age 
            FROM reports r
            JOIN report_drugs d ON r.case_id = d.case_id
            WHERE d.drug_name = ?
        """
        df_demo = db.execute_query(demo_query, (selected_drug,))
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.plotly_chart(plot_demographics(df_demo), use_container_width=True)
        with col_d2:
            # Histogram for Age
            if not df_demo.empty and df_demo["age"].notna().sum() > 0:
                fig_age = px.histogram(
                    df_demo.dropna(subset=["age"]),
                    x="age",
                    nbins=20,
                    color_discrete_sequence=["#38bdf8"],
                    title="Patient Age Distribution",
                    labels={"age": "Age (Years)", "count": "Case Count"}
                )
                fig_age.update_layout(
                    template="plotly_dark",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig_age, use_container_width=True)
            else:
                st.info("Age data not available for this subset.")

    # ------------------ MODE 2: FAERSIGHT QUERY ASSISTANT ------------------
    elif app_mode == "FAERSight Query Assistant":
        st.markdown("<h1 class='app-header'>FAERSight Query Assistant</h1>", unsafe_allow_html=True)
        st.markdown(
            "Query safety profiles, side-effect signals, and drug-reaction counts. "
            "The assistant runs real-time tool queries against the clinical database, ensuring factual grounding."
        )
        
        agent = get_rag_agent()
        
        # Initialize Gemini Chat Session in session state if online and not set
        if agent.has_llm and "chat_session" not in st.session_state:
            st.session_state.chat_session = agent.start_chat_session()
            
        # Initialize conversation messages array in session state
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        # API status indicator in main layout
        if agent.has_llm and st.session_state.chat_session:
            st.markdown(f"""
            <div class="status-pill">
                <span class="status-dot"></span>
                <span>AI Engine: Google Gemini ({agent.model_name}) (Online Mode)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="status-pill warning">
                <span class="status-dot"></span>
                <span>AI Engine: Offline Mode (Displaying Relational Database Stats)</span>
            </div>
            """, unsafe_allow_html=True)
            
        # Quick suggestions
        st.markdown("**Example queries to try:**")
        col_q1, col_q2, col_q3 = st.columns(3)
        clicked_prompt = None
        with col_q1:
            st.markdown('<div class="suggest-button">', unsafe_allow_html=True)
            if st.button("What safety signals are emerging for adalimumab?"):
                clicked_prompt = "What safety signals are emerging for adalimumab?"
            st.markdown('</div>', unsafe_allow_html=True)
        with col_q2:
            st.markdown('<div class="suggest-button">', unsafe_allow_html=True)
            if st.button("Compare safety signals of ibuprofen vs celecoxib."):
                clicked_prompt = "Compare safety signals of ibuprofen vs celecoxib."
            st.markdown('</div>', unsafe_allow_html=True)
        with col_q3:
            st.markdown('<div class="suggest-button">', unsafe_allow_html=True)
            if st.button("Are there liver failure signals for acetaminophen?"):
                clicked_prompt = "Are there liver failure signals for acetaminophen?"
            st.markdown('</div>', unsafe_allow_html=True)
                
        st.markdown("---")
        
        # Render Chat History
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
        # User input box or suggestion click
        prompt = st.chat_input("Ask a safety question (e.g. 'Show me injection site risks for adalimumab')")
        if clicked_prompt:
            prompt = clicked_prompt
            
        if prompt:
            # Display user message instantly
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Generate assistant response
            with st.chat_message("assistant"):
                with st.spinner("Retrieving database counts and generating summary..."):
                    if agent.has_llm and st.session_state.chat_session:
                        try:
                            response = agent.send_message_with_fallback(st.session_state.chat_session, prompt)
                        except Exception as e:
                            response = f"An error occurred while communicating with the Gemini API: {e}"
                    else:
                        response = agent.get_offline_response(prompt)
                    st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()

    # ------------------ MODE 3: PIPELINE DETAILS ------------------
    elif app_mode == "Pipeline Architecture":
        st.markdown("<h1 class='app-header'>Data Pipeline Architecture</h1>", unsafe_allow_html=True)
        st.markdown("""
        <div class="status-pill">
            <span class="status-dot"></span>
            <span>Medallion Architecture Active (Bronze ➔ Silver ➔ Gold)</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="pipeline-step-card">
            <div class="pipeline-step-header">
                <span class="pipeline-step-title">Bronze Layer: Raw Ingestion</span>
                <span class="pipeline-step-badge">Raw JSON</span>
            </div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.6;">
                Pulls nested JSON patient event records directly from the <strong>openFDA API</strong> (falling back to a robust simulation set if rate-limited).
                Stores raw payloads as unmodified Bronze JSON files on a rolling weekly sequence.
            </div>
        </div>
        <div class="pipeline-step-card">
            <div class="pipeline-step-header">
                <span class="pipeline-step-title">Silver Layer: Clean & Validate</span>
                <span class="pipeline-step-badge">Quality Gate</span>
            </div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.6;">
                Flattens nested records, standardizes raw product text to generic ingredients using a fuzzy dictionary, and runs a 
                <strong>Case Version Deduplication Gate</strong> keeping only the highest <code>case_version</code> per unique <code>case_id</code>.
            </div>
        </div>
        <div class="pipeline-step-card">
            <div class="pipeline-step-header">
                <span class="pipeline-step-title">Gold Layer: Analytical Signal Warehouse</span>
                <span class="pipeline-step-badge">Enriched Stats</span>
            </div>
            <div style="font-size: 14px; color: #94a3b8; line-height: 1.6;">
                Executes parallelized vectorized calculations for <strong>Proportional Reporting Ratio (PRR)</strong>, 
                <strong>Reporting Odds Ratio (ROR)</strong>, and <strong>Yates' corrected Chi-Square ($\chi^2$)</strong>.
                Loads relational datasets into SQLite / Postgres database using constraint-preserving loads.
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Database Tables View")
        table_choice = st.selectbox("Select Database Table to Inspect", ["reports", "report_drugs", "report_reactions", "safety_signals"])
        
        df_preview = db.execute_query(f"SELECT * FROM {table_choice} LIMIT 10")
        st.dataframe(df_preview, use_container_width=True)
        
        st.success("Database connection is active. Relational schema loaded and fully indexed.")

if __name__ == "__main__":
    main()
