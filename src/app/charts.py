import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

def plot_signal_volcano(df_signals: pd.DataFrame, drug_name: str) -> go.Figure:
    """
    Creates a volcano-like scatter plot of association strength (PRR) vs. case count (a).
    Highlights the active safety signal quadrant.
    """
    df = df_signals.copy()
    if df.empty:
        return go.Figure()
        
    # Standardize column types
    df["is_signal_str"] = df["is_signal"].map({1: "Safety Signal", 0: "Background Noise"})
    
    fig = px.scatter(
        df,
        x="a",
        y="prr",
        color="is_signal_str",
        color_discrete_map={"Safety Signal": "#f43f5e", "Background Noise": "#475569"},
        hover_data=["reaction_name", "ror", "chi2"],
        labels={
            "a": "Reports with Drug & Reaction",
            "prr": "Proportional Reporting Ratio (PRR)",
            "is_signal_str": "Signal Status"
        },
        title=f"Disproportionality Plot for {drug_name.upper()} Events",
        log_x=True # Use log scale for report count because it can vary wildly
    )
    
    # Customize marker size and styling
    fig.update_traces(
        marker=dict(size=9, line=dict(width=1, color="rgba(0,0,0,0.2)")),
        selector=dict(mode="markers")
    )
    
    # Add horizontal threshold line at PRR = 2
    fig.add_shape(
        type="line",
        x0=df["a"].min(),
        x1=df["a"].max(),
        y0=2,
        y1=2,
        line=dict(color="#f43f5e", width=1.5, dash="dash"),
    )
    
    # Add vertical threshold line at report count = 3
    fig.add_shape(
        type="line",
        x0=3,
        x1=3,
        y0=df["prr"].min(),
        y1=df["prr"].max(),
        line=dict(color="#f43f5e", width=1.5, dash="dash"),
    )
    
    # Style update
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        title_font=dict(size=16, family="Plus Jakarta Sans, sans-serif", color="#ffffff"),
        xaxis=dict(gridcolor="#1e293b", zerolinecolor="#334155"),
        yaxis=dict(gridcolor="#1e293b", zerolinecolor="#334155")
    )
    
    # Correct the log scale tick marks formatting (avoiding abbreviated 2/5 intermediate values)
    fig.update_xaxes(
        type="log",
        dtick=1,
        tickformat="d"
    )
    
    return fig

def plot_ror_forest(df_signals: pd.DataFrame, drug_name: str) -> go.Figure:
    """
    Creates a Forest Plot of ROR with 95% Confidence Intervals for the top signals.
    """
    # Filter to active signals and sort by ROR strength
    df = df_signals[df_signals["is_signal"] == 1].head(10).copy()
    if df.empty:
        return go.Figure()
        
    df = df.sort_values(by="ror", ascending=True)
    
    fig = go.Figure()
    
    # Add ROR points with 95% CI error bars
    fig.add_trace(
        go.Scatter(
            x=df["ror"],
            y=df["reaction_name"].str.title(),
            mode="markers",
            marker=dict(color="#f43f5e", size=10, line=dict(width=1, color="rgba(0,0,0,0.3)")),
            error_x=dict(
                type="data",
                symmetric=False,
                array=df["ror_ci_upper"] - df["ror"],
                arrayminus=df["ror"] - df["ror_ci_lower"],
                color="#fda4af",
                thickness=2,
                width=6
            ),
            hovertemplate="Reaction: %{y}<br>ROR: %{x:.2f}<br>95% CI: %{customdata[0]:.2f} - %{customdata[1]:.2f}<extra></extra>",
            customdata=np.stack((df["ror_ci_lower"], df["ror_ci_upper"]), axis=-1)
        )
    )
    
    # Add vertical line at ROR = 1.0 (baseline/no-risk line)
    fig.add_shape(
        type="line",
        x0=1.0,
        x1=1.0,
        y0=-1,
        y1=len(df),
        line=dict(color="#475569", width=2, dash="dash")
    )
    
    fig.update_layout(
        title=f"Forest Plot of ROR (95% CI) for Top {drug_name.upper()} Signals",
        xaxis_title="Reporting Odds Ratio (ROR)",
        yaxis_title="Adverse Reaction",
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        title_font=dict(size=16, family="Plus Jakarta Sans, sans-serif", color="#ffffff"),
        xaxis=dict(gridcolor="#1e293b", zerolinecolor="#334155"),
        yaxis=dict(gridcolor="#1e293b", zerolinecolor="#334155")
    )
    
    return fig

def plot_demographics(df_demographics: pd.DataFrame) -> go.Figure:
    """
    Plots patient age distribution and sex breakdown.
    """
    if df_demographics.empty:
        return go.Figure()
        
    # Fill missing values for sex
    df = df_demographics.copy()
    df["sex"] = df["sex"].fillna("Unknown")
    
    # Pie chart for Sex
    sex_counts = df["sex"].value_counts().reset_index()
    sex_counts.columns = ["Sex", "Count"]
    
    fig = px.pie(
        sex_counts,
        values="Count",
        names="Sex",
        color="Sex",
        color_discrete_map={"Male": "#38bdf8", "Female": "#f43f5e", "Unknown": "#475569"},
        hole=0.4,
        title="Patient Sex Distribution"
    )
    
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        title_font=dict(size=16, family="Plus Jakarta Sans, sans-serif", color="#ffffff"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
    )
    
    return fig
