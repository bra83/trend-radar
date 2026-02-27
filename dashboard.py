import streamlit as st
from google import genai

st.title("Teste Gemini")

API_KEY = st.secrets["GEMINI_API_KEY"]

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Diga apenas OK"
    )
    st.success(response.text)
except Exception as e:
    st.error(e)
