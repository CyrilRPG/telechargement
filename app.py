import os
import re
import io
import tempfile
import subprocess
from pathlib import Path

import streamlit as st
from yt_dlp import YoutubeDL

st.set_page_config(page_title="Moodle / Crystalink Downloader", page_icon="⬇️", layout="centered")

st.title("⬇️ Téléchargeur simple : Moodle / Crystalink")
st.caption("⚠️ Assurez‑vous d’avoir le droit de télécharger ce contenu et de respecter les CGU des plateformes.")

# -----------------------------
# Helpers
# -----------------------------
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) "
    "AppleWebKit/601.7.8 (KHTML, like Gecko) Version/9.1.3 Safari/537.86.7"
)

@st.cache_data(show_spinner=False)
def _write_temp_file(upload) -> str:
    """Sauve un fichier téléchargé (cookies.txt) et retourne le chemin"""
    if upload is None:
        return ""
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(upload.read())
    tmp.flush()
    tmp.close()
    return tmp.name


def _quality_to_format(q: str) -> str:
    if q == "Meilleure qualité":
        return "bestvideo*+bestaudio/best"
    if q == "720p":
        return "bv*[height<=720]+ba/b"
    if q == "480p":
        return "bv*[height<=480]+ba/b"
    if q == "Audio seulement":
        return "bestaudio/best"
    return "best"


def _run_ffmpeg(video_m3u8: str, audio_m3u8: str | None, out_path: Path) -> None:
    """Télécharge/merge via ffmpeg comme dans votre script bash."""
    base_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-user_agent",
        UA,
    ]
    if audio_m3u8:
        cmd = base_cmd + ["-i", video_m3u8, "-i", audio_m3u8, "-c:v", "copy", "-c:a", "aac", str(out_path)]
    else:
        cmd = base_cmd + ["-i", video_m3u8, "-c", "copy", str(out_path)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Échec ffmpeg")


def _download_with_ytdlp(url: str, fmt: str, cookiefile: str | None, referer: str | None) -> tuple[bytes, str]:
    """Télécharge via yt‑dlp et retourne (bytes, filename)."""
    # Dossier temporaire isolé
    tmpdir = tempfile.mkdtemp()
    outtmpl = os.path.join(tmpdir, "%(title)s.%(ext)s")

    headers = {}
    if referer:
        headers["Referer"] = referer

    opts = {
        "outtmpl": outtmpl,
        "format": fmt,
        "merge_output_format": "mp4",
        "http_headers": headers,
        "concurrent_fragment_downloads": 5,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile

    progress = st.progress(0.0, text="Préparation…")

    def hook(d):
        if d.get('status') == 'downloading':
            # d.get('_percent_str') comme " 12.3%"
            p = d.get('downloaded_bytes', 0)
            t = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            if t:
                progress.progress(min(0.99, p / t), text=f"Téléchargement… {d.get('_percent_str','').strip()}")
        elif d.get('status') == 'finished':
            progress.progress(1.0, text="Fusion/finition…")

    opts["progress_hooks"] = [hook]

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        out_path = ydl.prepare_filename(info)
        # si merge_output_format a changé l’extension
        if os.path.exists(os.path.splitext(out_path)[0] + ".mp4"):
            out_path = os.path.splitext(out_path)[0] + ".mp4"

    progress.empty()

    filename = os.path.basename(out_path)
    with open(out_path, "rb") as f:
        data = f.read()

    return data, filename


# -----------------------------
# UI
# -----------------------------
platform = st.selectbox("Plateforme", ["Moodle", "Crystalink"], index=0)
mode = st.radio("Mode", ["URL de la page (simple)", "Lien M3U8 direct (avancé)"])

st.divider()

if mode == "URL de la page (simple)":
    url = st.text_input("Collez l’URL de la page vidéo (Moodle/Crystalink/Panopto)")
    quality = st.selectbox("Qualité", ["Meilleure qualité", "720p", "480p", "Audio seulement"], index=0)
    cookies_up = st.file_uploader("cookies.txt (souvent nécessaire si la vidéo est privée)", type=["txt"], help="Exportez vos cookies avec une extension comme 'Get cookies.txt'.")
    referer = st.text_input("Référent (optionnel)", value=url if url else "", help="Laisse vide si inutile. Sert parfois à contourner des protections de hotlink.")

    col1, col2 = st.columns([1,1])
    with col1:
        start = st.button("Télécharger", type="primary", disabled=not url)
    with col2:
        st.write("")

    if start and url:
        try:
            cookie_path = _write_temp_file(cookies_up) if cookies_up else None
            fmt = _quality_to_format(quality)
            with st.spinner("Téléchargement en cours…"):
                data, fname = _download_with_ytdlp(url, fmt, cookie_path, referer or None)
            st.success("Terminé !")
            st.download_button("Enregistrer la vidéo", data=data, file_name=fname, mime="video/mp4")
        except Exception as e:
            st.error(f"Échec : {e}")

else:
    st.markdown("**Mode avancé :** collez directement le ou les liens M3U8.")
    v_m3u8 = st.text_input("URL vidéo .m3u8")
    a_m3u8 = st.text_input("URL audio .m3u8 (optionnel)")
    filename = st.text_input("Nom du fichier de sortie (sans extension)", value="video")

    start = st.button("Télécharger", type="primary", disabled=not v_m3u8)

    if start and v_m3u8:
        try:
            safe = re.sub(r"[^\w\-\s\.]+", "_", filename).strip() or "video"
            out_path = Path(tempfile.mkdtemp()) / f"{safe}.mkv"
            with st.spinner("Téléchargement via ffmpeg…"):
                _run_ffmpeg(v_m3u8, a_m3u8 or None, out_path)
            st.success("Terminé !")
            with open(out_path, "rb") as f:
                data = f.read()
            st.download_button("Enregistrer la vidéo", data=data, file_name=out_path.name, mime="video/x-matroska")
        except Exception as e:
            st.error(f"Échec : {e}")

st.divider()
st.caption("Astuce : si la vidéo est derrière une connexion, exportez vos cookies du navigateur sur la page de la vidéo et importez le fichier ici.")
