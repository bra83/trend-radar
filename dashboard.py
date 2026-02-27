import os
import json
import time
from datetime import datetime

import requests
import streamlit as st

st.set_page_config(page_title="3D Trend Radar", layout="wide")

st.title("3D Trend Radar — Perplexity (manual) → Gemini (API)")
st.caption("Cole o texto do Perplexity e o app usa a API do Gemini para estruturar oportunidades e itens.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

DEFAULT_COUNTRY = os.getenv("TREND_COUNTRY_DEFAULT", "Brazil")
DEFAULT_PROMPT_STYLE = os.getenv("TREND_PROMPT_STYLE", "empreendedorismo impressão 3D, foco em margem e diferenciação")

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

def build_prompt(perplexity_text: str, country: str, style: str) -> str:
    return (
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
        + perplexity_text
    )

def call_gemini(prompt: str, temperature: float) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurado. Defina nos Secrets do Streamlit Cloud.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": float(temperature)},
    }

    r = requests.post(url, json=payload, timeout=180)

    if r.status_code >= 400:
        # Avoid leaking URL (contains key). Show only status and a short response excerpt.
        snippet = (r.text or "")[:1000]
        raise requests.HTTPError(
            f"Gemini HTTP {r.status_code}. Response (first 1000 chars): {snippet}",
            response=r,
        )

    return r.json()

def parse_gemini_json(api_response: dict) -> dict:
    raw = (
        (api_response.get("candidates") or [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    ) or ""
    try:
        return json.loads(raw)
    except Exception:
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "items": [],
            "top_opportunities": [],
            "notes": [
                "Falha ao parsear JSON do Gemini. Veja 'raw' abaixo.",
                raw[:2000],
            ],
        }

def extract_retry_after(headers: dict):
    ra = headers.get("Retry-After") or headers.get("retry-after")
    if ra:
        try:
            return int(float(ra))
        except Exception:
            return None
    return None

def run_with_backoff(prompt: str, temperature: float, max_attempts: int = 4) -> dict:
    wait = 2
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return call_gemini(prompt, temperature)
        except requests.HTTPError as e:
            last_err = e
            status = e.response.status_code if e.response is not None else None
            if status in (429, 503):
                retry_after = extract_retry_after(e.response.headers) if e.response is not None else None
                sleep_s = retry_after if retry_after is not None else wait
                sleep_s = max(1, min(int(sleep_s), 60))
                st.warning(f"Limite/instabilidade do Gemini (HTTP {status}). Tentativa {attempt}/{max_attempts}. Aguardando {sleep_s}s e tentando novamente...")
                time.sleep(sleep_s)
                wait = min(wait * 2, 60)
                continue
            raise
        except Exception as e:
            last_err = e
            break
    raise last_err if last_err else RuntimeError("Falha desconhecida ao chamar Gemini.")

def safe_str(x) -> str:
    return "" if x is None else str(x)

def matches_query(row: dict, q: str) -> bool:
    blob = " ".join([safe_str(v).lower() for v in row.values()])
    return q.lower() in blob

with st.sidebar:
    st.header("Configuração")
    if not GEMINI_API_KEY:
        st.error("Falta configurar a secret/env var GEMINI_API_KEY no Streamlit Cloud.")
    st.caption(f"Modelo: {GEMINI_MODEL}")
    country = st.text_input("Mercado (country)", value=DEFAULT_COUNTRY)
    prompt_style = st.text_input("Foco do analista", value=DEFAULT_PROMPT_STYLE)
    temperature = st.slider("Criatividade (temperature)", 0.0, 1.0, 0.3, 0.05)
    max_chars = st.slider("Máx. caracteres enviados", 10000, 120000, 60000, 5000)

    colx, coly = st.columns(2)
    if colx.button("Limpar resultado", use_container_width=True):
        st.session_state.pop("last_result", None)
        st.session_state.pop("last_input_hash", None)
        st.rerun()

st.subheader("1) Cole aqui o texto do Perplexity")
pplx_text = st.text_area(
    "Texto do Perplexity",
    value="",
    height=260,
    placeholder="Abra o Perplexity → faça a pesquisa → copie a resposta inteira → cole aqui."
)

colA, colB = st.columns([1, 1])
run_now = colA.button("Analisar agora", type="primary", use_container_width=True)
reuse_last = colB.toggle("Reusar último resultado", value=True, help="Evita novas chamadas se você mexer em filtros depois de analisar.")

if not GEMINI_API_KEY:
    st.stop()

input_hash = str(hash((pplx_text.strip()[:max_chars], country, prompt_style, round(float(temperature), 2), GEMINI_MODEL)))

if reuse_last and ("last_result" in st.session_state) and (st.session_state.get("last_input_hash") == input_hash):
    result = st.session_state["last_result"]
else:
    result = None

if run_now:
    if not pplx_text.strip():
        st.warning("Cole o texto do Perplexity antes de rodar.")
        st.stop()

    clipped = pplx_text.strip()[:max_chars]
    prompt = build_prompt(clipped, country, prompt_style)

    with st.spinner("Chamando Gemini e estruturando dados..."):
        try:
            api_response = run_with_backoff(prompt, temperature, max_attempts=4)
            result = parse_gemini_json(api_response)
        except requests.HTTPError as e:
            st.error(f"Falha na chamada do Gemini: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Falha inesperada: {e}")
            st.stop()

    st.session_state["last_result"] = result
    st.session_state["last_input_hash"] = input_hash

if result is None:
    st.info("Cole um resultado do Perplexity e clique em **Analisar agora**.")
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

st.subheader("3) Itens detectados")
if not rows:
    st.write("Nenhum item retornado (ou o Gemini retornou vazio).")
else:
    colf1, colf2, colf3 = st.columns([2, 1, 1])
    q = colf1.text_input("Filtrar por texto", "")
    risk = colf2.selectbox("Risco", ["(todos)", "low", "medium", "high"], index=0)
    category = colf3.text_input("Categoria contém", "")

    filtered = rows
    if q.strip():
        filtered = [r for r in filtered if matches_query(r, q)]
    if risk != "(todos)":
        filtered = [r for r in filtered if safe_str(r.get("Risco")) == risk]
    if category.strip():
        filtered = [r for r in filtered if category.lower() in safe_str(r.get("Categoria")).lower()]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

st.subheader("4) Detalhes")
if items:
    options = [f"{i+1}. {it.get('product','(sem nome)')}" for i, it in enumerate(items)]
    sel = st.selectbox("Escolha um item", options, index=0)
    idx = int(sel.split(".")[0]) - 1
    it = items[idx]

    left, right = st.columns([1, 1])
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
