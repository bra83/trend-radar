import os
import json
import time
from datetime import datetime

import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="3D Trend Radar", layout="wide")

st.title("3D Trend Radar — Perplexity + Gemini")
st.caption("Dashboard que consulta um endpoint do n8n e exibe oportunidades e itens trend.")

N8N_URL = os.getenv("N8N_TREND_WEBHOOK_URL", "").strip()
DEFAULT_TOPIC = os.getenv("TREND_TOPIC_DEFAULT", "viral 3d printed products on TikTok and Instagram this week; include typical price ranges and keywords/hashtags")
DEFAULT_COUNTRY = os.getenv("TREND_COUNTRY_DEFAULT", "Brazil")

with st.sidebar:
    st.header("Configuração")
    if not N8N_URL:
        st.warning("Defina a env var N8N_TREND_WEBHOOK_URL com a URL Production do seu Webhook no n8n (GET /trend-scan).")
    topic = st.text_area("Tema / consulta", value=DEFAULT_TOPIC, height=120)
    country = st.text_input("País / mercado", value=DEFAULT_COUNTRY)
    colA, colB = st.columns(2)
    run_now = colA.button("Rodar agora", use_container_width=True)
    auto_refresh = colB.toggle("Auto-atualizar", value=False)

@st.cache_data(ttl=120, show_spinner=False)
def fetch_trends(n8n_url: str, topic: str, country: str) -> dict:
    if not n8n_url:
        return {"generated_at": None, "items": [], "top_opportunities": [], "notes": ["N8N_TREND_WEBHOOK_URL não configurado."]}
    params = {"topic": topic, "country": country}
    r = requests.get(n8n_url, params=params, timeout=180)
    r.raise_for_status()
    return r.json()

if auto_refresh and N8N_URL and not run_now:
    st.info("Auto-atualização ligada. Atualiza quando o cache expirar (TTL=120s).")
    time.sleep(0.2)

try:
    data = fetch_trends(N8N_URL, topic, country)
except Exception as e:
    st.error(f"Falha ao consultar n8n: {e}")
    st.stop()

generated_at = data.get("generated_at")
items = data.get("items", []) or []
top_ops = data.get("top_opportunities", []) or []
notes = data.get("notes", []) or []

c1, c2, c3 = st.columns(3)
c1.metric("Itens encontrados", len(items))
c2.metric("Top oportunidades", len(top_ops))
c3.metric("Gerado em", generated_at or "—")

st.subheader("Top oportunidades")
if top_ops:
    for i, op in enumerate(top_ops, 1):
        st.markdown(f"**{i}.** {op}")
else:
    st.write("Sem oportunidades listadas.")

rows = []
for it in items:
    price_mentions = it.get("price_mentions", []) or []
    prices_str = "; ".join([f"{p.get('price','')} {p.get('currency','')}".strip() for p in price_mentions if p])[:300]
    source_urls = "; ".join([p.get("source_url","") for p in price_mentions if p and p.get("source_url")])[:500]
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

st.subheader("Itens detectados")
if df.empty:
    st.write("Nenhum item retornado ainda.")
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

st.subheader("Detalhes")
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
