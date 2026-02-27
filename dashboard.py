import streamlit as st
import json
from google import genai
from google.genai import types

st.set_page_config(page_title="Trend Radar 3D", layout="wide")
st.title("Trend Radar 3D — Perplexity → Gemini")

API_KEY = st.secrets.get("GEMINI_API_KEY")
MODEL = st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash")

if not API_KEY:
    st.error("Configure GEMINI_API_KEY em Settings → Secrets.")
    st.stop()

client = genai.Client(api_key=API_KEY)

def analyze_text(text):
    prompt = f"""
Você é um analista de mercado especializado em negócios de impressão 3D no Brasil.

Analise o texto abaixo e identifique oportunidades estruturadas.

Retorne SOMENTE JSON no formato:

{{
  "opportunities": [
    {{
      "product": "",
      "niche": "",
      "estimated_ticket_brl": "",
      "saturation_level": "low|medium|high",
      "margin_potential": "low|medium|high",
      "target_audience": "",
      "competitive_edge": "",
      "mvp_suggestion": "",
      "risk_level": "low|medium|high"
    }}
  ]
}}

Texto:
{text}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1500
        )
    )

    return response.text

st.subheader("Cole o texto do Perplexity")
input_text = st.text_area("", height=250)

if st.button("Analisar"):
    if not input_text.strip():
        st.warning("Cole o texto primeiro.")
        st.stop()

    with st.spinner("Analisando..."):
        try:
            raw = analyze_text(input_text)
            data = json.loads(raw)

            opportunities = data.get("opportunities", [])

            st.success(f"{len(opportunities)} oportunidades identificadas")

            for i, item in enumerate(opportunities, 1):
                with st.expander(f"{i}. {item['product']}"):
                    col1, col2 = st.columns(2)
                    col1.write(f"**Nicho:** {item['niche']}")
                    col1.write(f"**Ticket estimado:** {item['estimated_ticket_brl']}")
                    col1.write(f"**Saturação:** {item['saturation_level']}")
                    col1.write(f"**Margem potencial:** {item['margin_potential']}")
                    col2.write(f"**Público:** {item['target_audience']}")
                    col2.write(f"**Diferencial:** {item['competitive_edge']}")
                    col2.write(f"**MVP:** {item['mvp_suggestion']}")
                    col2.write(f"**Risco:** {item['risk_level']}")

        except Exception as e:
            st.error(f"Erro: {e}")
