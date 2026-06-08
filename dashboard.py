import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os

# Set page config
st.set_page_config(
    page_title="RAG Workbench",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Theme / CSS ---
st.markdown("""
<style>
    .stMetric {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    .certification-banner {
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 25px;
        text-align: center;
    }
    .banner-pass {
        background-color: rgba(16, 185, 129, 0.1);
        border: 1px solid #10b981;
        color: #10b981;
    }
    .banner-fail {
        background-color: rgba(239, 68, 68, 0.1);
        border: 1px solid #ef4444;
        color: #ef4444;
    }
    .sidebar .stButton button {
        width: 100%;
        text-align: left;
    }
</style>
""", unsafe_allow_html=True)

# --- Constants ---
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
API_KEY = os.getenv("API_KEY", "") # Header: X-API-Key

# --- API Helpers ---
@st.cache_data(ttl=30)
def fetch_metrics():
    try:
        resp = requests.get(
            f"{API_BASE_URL}/metrics/dashboard",
            headers={"X-API-Key": API_KEY},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Error fetching metrics: {e}")
        return None

def send_chat_message(mode, message, history):
    endpoint = "sql" if mode == "SQL" else "rag"
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.post(
            f"{API_BASE_URL}/chat/{endpoint}",
            json={"message": message, "history": history},
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"type": "error", "answer": f"Chat failed: {e}"}

# --- Sidebar Navigation ---
with st.sidebar:
    st.title("RAG Workbench")
    st.markdown("---")
    view = st.radio("Navigation", ["Dashboard", "Chat"], index=0)
    st.markdown("---")
    st.info("Phase 7: Metrics Dashboard")
    st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

# --- View: Dashboard ---
if view == "Dashboard":
    st.header("Pipeline Health Dashboard")
    
    data = fetch_metrics()
    
    if data:
        agreement = data.get("agreement")
        routing = data.get("routing")
        
        # 1. Certification Banner
        if agreement:
            rate = agreement["agreement_rate"] or 0
            is_certified = agreement["meets_production_bar"]
            
            status_class = "banner-pass" if is_certified else "banner-fail"
            status_icon = "✅" if is_certified else "⚠️"
            status_text = "AUTO TIER CERTIFIED" if is_certified else "AUTO TIER NOT CERTIFIED"
            
            st.markdown(f"""
                <div class="certification-banner {status_class}">
                    <h2 style="margin:0; color:inherit;">{status_icon} {status_text}</h2>
                    <p style="margin:5px 0 0 0; opacity:0.8;">
                        Agreement Rate: {rate*100:.1f}% (Required: 95.0%) | 
                        Window: last {data['window_size']} decisions
                    </p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("No agreement data available for certification.")

        # 2. Metric Cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_rev = agreement["total_reviewed"] if agreement else 0
            st.metric("Total Reviewed", total_rev)
        
        with col2:
            rate = (agreement["agreement_rate"] * 100) if agreement and agreement["agreement_rate"] is not None else 0
            st.metric("Agreement Rate", f"{rate:.1f}%")
            
        with col3:
            esc_rate = (routing["escalation_rate"] * 100) if routing and routing["escalation_rate"] is not None else 0
            st.metric("Escalation Rate", f"{esc_rate:.1f}%")
            
        with col4:
            st.metric("Unrecognized Concepts", data["unrecognized_concept_count"])

        # 3. Routing Distribution Bar
        st.subheader("Routing Distribution")
        if routing:
            # Horizontal stacked bar using Plotly
            fig = go.Figure()
            
            # Colors from UI-SPEC
            colors = {
                "AUTO": "#10b981",            # Emerald-500
                "SAMPLED_REVIEW": "#6366f1",  # Indigo-500
                "ESCALATE": "#ef4444"         # Red-500
            }
            
            tiers = [
                ("AUTO", routing["auto_count"], routing["auto_rate"]),
                ("SAMPLED_REVIEW", routing["sampled_review_count"], routing["sampled_review_rate"]),
                ("ESCALATE", routing["escalate_count"], routing["escalation_rate"])
            ]
            
            for name, count, rate in tiers:
                pct = (rate * 100) if rate else 0
                fig.add_trace(go.Bar(
                    y=["Distribution"],
                    x=[pct],
                    name=f"{name} ({count})",
                    orientation='h',
                    marker=dict(color=colors[name]),
                    hovertemplate=f"{name}: {pct:.1f}% ({count})<extra></extra>"
                ))

            fig.update_layout(
                barmode='stack',
                height=150,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showticklabels=True, range=[0, 100], gridcolor='#333'),
                yaxis=dict(showticklabels=False)
            )
            
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 4. Raw Data (Optional)
        with st.expander("View Raw Metrics JSON"):
            st.json(data)
    else:
        st.error("Could not load metrics. Ensure the database is seeded.")

# --- View: Chat ---
elif view == "Chat":
    st.header("Financial Analyst Chat")
    
    # Mode selector
    mode = st.radio("Search Mode", ["RAG", "SQL"], horizontal=True)
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "sql" in message and message["sql"]:
                st.code(message["sql"], language="sql")
            if "data" in message and message["data"]:
                st.dataframe(pd.DataFrame(message["data"]))

    # Chat input
    if prompt := st.chat_input("Ask a question about SEC filings or market data..."):
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")
            
            # Format history for API
            history = []
            for m in st.session_state.messages[:-1]:
                history.append({"role": m["role"], "content": m["content"]})
            
            # Call API
            # NOTE: We use the API server here because chat services have many dependencies
            # (llm, vector store, etc.) that are better managed by the FastAPI server.
            # Make sure uvicorn is running!
            result = send_chat_message(mode, prompt, history)
            
            if result.get("type") == "error":
                full_response = f"⚠️ {result.get('answer', 'Unknown error')}"
                message_placeholder.markdown(full_response)
            else:
                full_response = result.get("answer", "")
                message_placeholder.markdown(full_response)
                
                # Show SQL/Data if present
                sql = result.get("sql")
                if sql:
                    st.code(sql, language="sql")
                
                data = result.get("data")
                if data:
                    st.dataframe(pd.DataFrame(data))
                
                # Add assistant response to history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_response,
                    "sql": sql,
                    "data": data
                })
