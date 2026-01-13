import streamlit as st

st.set_page_config(page_title="YouTube Scraper", layout="wide")

st.title("🎬 YouTube Keyword Research Tool")
st.write("Recherche des vidéos YouTube et extrait les commentaires")

col1, col2 = st.columns(2)

with col1:
    keyword = st.text_input("🔍 Mot-clé:", placeholder="guerre en Irak")

with col2:
    max_videos = st.slider("📊 Nombre de vidéos:", 1, 20, 5)

if st.button("🚀 Lancer la recherche", use_container_width=True):
    st.success(f"✅ Recherche: **{keyword}**")
    st.info(f"Vidéos à analyser: **{max_videos}**")
