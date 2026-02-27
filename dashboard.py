import os
import time
import streamlit as st
from google import genai
from google.genai import types

# Streamlit Secrets: coloque GEMINI_API_KEY lá
API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    st.error("Faltou configurar GEMINI_API_KEY em Settings -> Secrets.")
    st.stop()

client = genai.Client(api_key=API_KEY)

MODEL = st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash")  # você pode trocar depois

def gemini_with_backoff(prompt: str, temperature: float = 0.4, max_attempts: int = 5) -> str:
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=float(temperature),
                    max_output_tokens=1200,
                ),
            )
            # resp.text já vem pronto
            return (resp.text or "").strip()
        except Exception as e:
            last_err = e
            # backoff simples (resolve 429 na maioria dos casos)
            sleep_s = min(20, 2 ** attempt)
            time.sleep(sleep_s)
    raise last_err
