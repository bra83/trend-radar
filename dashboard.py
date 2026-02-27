import os
import json
import time
from datetime import datetime

import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="3D Trend Radar", layout="wide")

st.title("3D Trend Radar — Perplexity (manual) → Gemini (API)")
st.caption("Cole o texto do Perplexity e o app usa a API do Gemini para estruturar em oportunidades e itens.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

DEFAULT_COUNTRY = os.getenv("TREND_COUNTRY_DEFAULT", "Brazil")
DEFAULT_PROMPT_STYLE = os.getenv("TREND_PROMPT_STYLE", "empreendedorismo impressão 3D, foco em margem e diferenciação")

with st.sidebar:
    st.header("Configuração")
    if not GEMINI_API_KEY:
        st.error("Falta configurar a secret/env var GEMINI_API_KEY no Streamlit Cloud.")
    country = st.text_input("Mercado (country)", value=DEFAULT_COUNTRY)
    prompt_style = st.text_input("Foco do analista", value=DEFAULT_PROMPT_STYLE)
    temperature = st.slider("Criatividade (temperature)", 0.0, 1.0, 0.3, 0.05)
    max_chars = st.number_input("Máx. caracteres enviados", min_value=20000, max_value=200000, value=120000, step=5000)

st.subheader("1) Cole aqui o texto do Perplexity")
pplx_text = st.text_area(
    "Texto do Perplexity",
    value="",
    height=260,
    placeholder="Abra o Perplexity → faça a pesquisa → copie a resposta inteira → cole aqui."
)

run_now = st.button("Analisar agora", type="primary", use_container_width=True)

SCHEMA_HINT = {
    "generated_at": "string ISO",
    "items": [
        {
            "product": "string",
            "category": "string",
            "why_trending": "string",
            "signals": ["string"],
            "price_mentions": [{"price": "string", "currency": "string", "context": "string", "source_url": "string"}],
            "keywords": ["string"],
            "risk": "low|medium|high",
            "differentiation": ["string"],
            "mvp_steps": ["string"]
        }
    ],
    "top_opportunities": ["string"],
    "notes": ["string"]
}

def gemini_generate_structured(perplexity_text: str, country: str, style: str, temperature: float, model: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    system_text = (
        "Você é um analista sênior de mercado para uma empresa brasileira de impressão 3D.\n"
        f"Foco: {style}.\n\n"
        "A partir do TEXTO (copiado do Perplexity) abaixo, gere um JSON ESTRITO no schema:\n"
        + json.dumps(SCHEMA_HINT, ensure_ascii=False) +
        "\n\nRegras:\n"
        "- Escreva em pt-BR.\n"
        "- Se o texto não trouxer preços/urls, deixe price_mentions vazio.\n"
        "- Não invente links.\n"
        "- Saída SOMENTE JSON (sem markdown, sem comentários).\n"
        f"- Mercado-alvo: {country}\n\n"
        "TEXTO:\n"
    )

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": system_text + perplexity_text}]
        }],
        "generationConfig": {
            "temperature": float(temperature)
        }
    }

    r = requests.post(url, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    raw = (data.get("candidates", [{}])[0]
              .get("content", {})
              .get("parts", [{}])[0]
              .get("text", "")) or ""
    try:
        return json.loads(raw)
    except Exception:
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "items": [],
            "top_opportunities": [],
            "notes": ["Falha ao parsear JSON do Gemini. Veja 'raw' abaixo.", raw[:2000]]
        }

if not run_now:
    st.stop()

if not GEMINI_API_KEY:
    st.stop()

if not pplx_text.strip():
    st.warning("Cole o texto do Perplexity antes de rodar.")
    st.stop()

pplx_text = pplx_text.strip()[: int(max_chars)]

with st.spinner("Chamando Gemini e estruturando dados..."):
    try:
        result = gemini_generate_structured(
            perplexity_text=pplx_text,
            country=country,
            style=prompt_style,
            temperature=temperature,
            model=GEMINI_MODEL
        )
    except Exception as e:
        st.error(f"Falha na chamada do Gemini: {e}")
        st.stop()

generated_at = result.get("generated_at")
items = result.get("items", []) or []
top_ops = result.get("top_opportunities", []) or []
notes = result.get("notes", []) or []

c1, c2, c3 = st.columns(3)
c1.metric("Itens encontrados", len(items))
c2.metric("Top oportunidades", len(top_ops))
c3.metric("Gerado em", generated_at or "—")

st.subheader("2) Top oportunidades")
if top_ops:
    for i, op in enumerate(top_ops, 1):
        st.markdown(f"**{i}.** {op}")
else:
    st.write("Sem oportunidades listadas.")

rows = []
for it in items:
    price_mentions = it.get("price_mentions", []) or []
    prices_str = "; ".join([f"{p.get('price','')} {p.get('currency','')}".strip() for p in price_mentions if p])[:300]
    source_urls = "; ".join([p.get("source_url","") for p in price_mentions if p and p.get("source_url")])[:900]
    rows.append({
        "Produto": it.get("product",""),
        "Categoria": it.get("category",""),
        "Risco": it.get("risk",""),
        "Por que está bombando": it.get("why_trending",""),
        "Preços (menções)": prices_str,
        "URLs (preço)": source_urls,
        "Keywords": ", ".join(it.get("keywords", []) or [])[:300],
    })

df = pd.DataFrame(rows)

st.subheader("3) Itens detectados")
if df.empty:
    st.write("Nenhum item retornado (ou o Gemini retornou vazio).")
else:
    colf1, colf2, colf3 = st.columns([2,1,1])
    q = colf1.text_input("Filtrar por texto", "")
    risk = colf2.selectbox("Risco", ["(todos)","low","medium","high"], index=0)
    category = colf3.text_input("Categoria contém", "")

    dff = df.copy()
    if q:
        mask = dff.apply(lambda r: q.lower() in " ".join([str(x).lower() for x in r.values]), axis=1)
        dff = dff[mask]
    if risk != "(todos)":
        dff = dff[dff["Risco"] == risk]
    if category:
        dff = dff[dff["Categoria"].str.lower().str.contains(category.lower(), na=False)]

    st.dataframe(dff, use_container_width=True, hide_index=True)

st.subheader("4) Detalhes")
if items:
    options = [f"{i+1}. {it.get('product','(sem nome)')}" for i, it in enumerate(items)]
    sel = st.selectbox("Escolha um item", options, index=0)
    idx = int(sel.split(".")[0]) - 1
    it = items[idx]

    left, right = st.columns([1,1])
    with left:
        st.markdown(f"### {it.get('product','')}")
        st.write(it.get("why_trending",""))
        st.markdown("**Sinais**")
        for s in it.get("signals", []) or []:
            st.markdown(f"- {s}")
        st.markdown("**Diferenciação**")
        for s in it.get("differentiation", []) or []:
            st.markdown(f"- {s}")

    with right:
        st.markdown("**MVP (passos)**")
        for s in it.get("mvp_steps", []) or []:
            st.markdown(f"- {s}")
        st.markdown("**Menções de preço**")
        for p in it.get("price_mentions", []) or []:
            st.markdown(f"- {p.get('price','')} {p.get('currency','')} — {p.get('context','')}".strip())
            if p.get("source_url"):
                st.code(p["source_url"])

if notes:
    st.subheader("Notas")
    for n in notes:
        st.write(f"- {n}")
