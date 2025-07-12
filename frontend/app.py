"""Streamlit front-end for the Zero-Shot Classification API"""
import os
import requests
import streamlit as st
import pandas as pd
import json
from sqlalchemy import create_engine, text as sa_text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = os.getenv("API_URL", "http://localhost:8000")  # Overridden in docker-compose
# DB connection vars (internal Docker DNS defaults)
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")
DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

DEFAULT_LABELS = [
    "Analyst Update",
    "Fed | Central Banks",
    "Company | Product News",
    "Treasuries | Corporate Debt",
    "Dividend",
    "Earnings",
    "Energy | Oil",
    "Financials",
    "Currencies",
    "General News | Opinion",
    "Gold | Metals | Materials",
    "IPO",
    "Legal | Regulation",
    "M&A | Investments",
    "Macro",
    "Markets",
    "Politics",
    "Personnel Change",
    "Stock Commentary",
    "Stock Movement",
]

# ---------------------------------------------------------------------------
# Page config & styles
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Zero-Shot Classifier",
    page_icon="🤖",
    layout="centered",
)

st.title("🔮 Zero-Shot Text Classifier")

@st.cache_resource(show_spinner=False)
def get_engine():
    try:
        return create_engine(DB_URL, pool_pre_ping=True)
    except Exception as e:
        st.warning(f"No se pudo conectar a la base de datos: {e}")
        return None
st.caption("Clasifica texto en tópicos financieros usando BART Large M-NLI.")

# ---------------------------------------------------------------------------
# Sidebar settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Ajustes")
    multi_label = st.checkbox("Permitir múltiples etiquetas", value=False)
    custom_api = st.text_input("Backend API URL", value=API_URL)
    st.markdown(
        "\n<sub>Deja en blanco para usar la URL interna definida en la variable de entorno.</sub>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Main input area
# ---------------------------------------------------------------------------
user_text = st.text_area("Texto a clasificar", height=200)
labels_input = st.multiselect(
    "Etiquetas personalizadas (opcional)", options=DEFAULT_LABELS, help="Si no seleccionas ninguna se usarán las 20 etiquetas por defecto."
)

if st.button("⚡ Clasificar", type="primary"):
    if not user_text.strip():
        st.warning("Por favor ingresa un texto.")
    else:
        payload = {"text": user_text, "multi_label": multi_label}
        if labels_input:
            payload["candidate_labels"] = labels_input

        # Decide which URL to hit
        url = custom_api.strip() or API_URL
        classify_endpoint = url.rstrip("/") + "/classify"

        try:
            with st.spinner("Clasificando..."):
                r = requests.post(classify_endpoint, json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            st.error(f"Error al llamar la API: {e}")
        else:
            st.success("✅ Clasificación completada")
            # Show top 5
            df = (
                pd.DataFrame({"label": data["labels"], "score": data["scores"]})
                .set_index("label")
                .head(10)
            )
            st.bar_chart(df)
            with st.expander("Ver resultado completo"):
                st.json(data, expanded=False)

st.markdown("---")

# ---------------------------------------------------------------------------
# Analytics section (via backend /stats endpoint)
# ---------------------------------------------------------------------------
st.header("📊 Estadísticas históricas")
if st.button("Actualizar estadísticas"):
    try:
        resp = requests.get((custom_api.strip() or API_URL).rstrip("/") + "/stats", timeout=30)
        resp.raise_for_status()
        stats_json = resp.json()
        if not stats_json.get("counts"):
            st.info("Aún no hay registros.")
        else:
            st.subheader("Distribución de etiquetas más frecuentes")
            st.bar_chart(pd.Series(stats_json["counts"]))

            st.subheader("Número total de predicciones")
            st.metric(label="Total", value=stats_json["total"])

            if stats_json.get("last_timestamp"):
                st.caption(f"Última predicción: {stats_json['last_timestamp']}")
    except Exception as e:
        st.error(f"Error al obtener estadísticas: {e}")
st.write(
    "<center><sub>Construido por Sebastian Ramirez © 2025 - TalentoTech Arquitectura en la nube</sub></center>",
    unsafe_allow_html=True,
)
