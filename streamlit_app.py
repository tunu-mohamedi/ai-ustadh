# 🕌 AI USTADH — Msaidizi wa Kusoma Qur'an (Web)
# by Mpenzi — Dar es Salaam, Tanzania
# Hosting: Streamlit Community Cloud (bure) | AI: Groq Whisper API (bure)

import re, json, urllib.request
import requests
import streamlit as st
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

st.set_page_config(page_title="AI Ustadh 🕌", page_icon="🕌", layout="centered")

# ====== WEKA LINK YA GOOGLE FORM YAKO YA MAONI HAPA ======
MAONI_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeuUNkwqq5RwlLP49ziqoGuG8-nzI9fRpMVMfLoG-0ouwPK4A/viewform?usp=header"

# ================= QURAN DATA (cached) =================
@st.cache_data(show_spinner="⏳ Napakua Qur'ani...")
def load_surahs():
    def fetch(url):
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())

    arabic  = fetch("https://api.alquran.cloud/v1/juz/30/quran-simple")["data"]["ayahs"]
    swahili = fetch("https://api.alquran.cloud/v1/juz/30/sw.barwani")["data"]["ayahs"]

    surahs = {}
    for ar, sw in zip(arabic, swahili):
        num = ar["surah"]["number"]
        if num not in surahs:
            surahs[num] = {"jina": ar["surah"]["englishName"], "ayah": [], "tafsiri": []}
        surahs[num]["ayah"].append(ar["text"])
        surahs[num]["tafsiri"].append(sw["text"])

    fat_ar = fetch("https://api.alquran.cloud/v1/surah/1/quran-simple")["data"]["ayahs"]
    fat_sw = fetch("https://api.alquran.cloud/v1/surah/1/sw.barwani")["data"]["ayahs"]
    surahs[1] = {"jina": "Al-Fatihah",
                 "ayah":    [a["text"] for a in fat_ar],
                 "tafsiri": [a["text"] for a in fat_sw]}

    # Bismillah fix
    BIS = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
    plain_b = re.sub(r'[\u064B-\u0652\u0670\u0653]', '', BIS)
    for num, s in surahs.items():
        if num == 1:
            continue
        first = s["ayah"][0]
        plain = re.sub(r'[\u064B-\u0652\u0670\u0653]', '', first)
        if plain.strip().startswith(plain_b):
            s["ayah"][0] = " ".join(first.split()[4:]).strip()
    return surahs

surahs = load_surahs()

# ================= BRAIN =================
WORD_TOLERANCE = 85
AYAH_PERFECT   = 92
ACCEPT_SCORE   = 60
GRAY_ZONE_LOW  = 45

def normalize(text):
    text = re.sub(r'[\u064B-\u0652\u0670\u0653\u0640]', '', text)
    text = re.sub(r'[\u0622\u0623\u0625\u0671]', '\u0627', text)
    text = text.replace('\u0629', '\u0647').replace('\u0649', '\u064A')
    text = text.replace('\u0624', '\u0648').replace('\u0626', '\u064A')
    text = text.replace('\u0621', '')
    return re.sub(r'\s+', ' ', text).strip()

def check_recitation(reference, student):
    ref_n, stu_n = normalize(reference), normalize(student)
    if fuzz.ratio(ref_n, stu_n) >= AYAH_PERFECT:
        return []
    ref_words, stu_words = ref_n.split(), stu_n.split()
    errors = []
    for op in Levenshtein.editops(ref_words, stu_words):
        if op.tag == 'delete':
            errors.append(f"⚠️ Umeruka neno: «{ref_words[op.src_pos]}» (nafasi ya {op.src_pos+1})")
        elif op.tag == 'replace':
            expected, heard = ref_words[op.src_pos], stu_words[op.dest_pos]
            if fuzz.ratio(expected, heard) >= WORD_TOLERANCE:
                continue
            errors.append(f"⚠️ Ulitakiwa kusema «{expected}» lakini ulisema «{heard}»")
        elif op.tag == 'insert':
            errors.append(f"⚠️ Umeongeza neno: «{stu_words[op.dest_pos]}»")
    return errors

def _ina_dalili_za_uongo(text):
    words = normalize(text).split()
    if len(words) < 2:
        return True
    for a, b in zip(words, words[1:]):
        if a == b and len(a) > 2:
            return True
    if len(set(words)) / len(words) < 0.5 and len(words) >= 4:
        return True
    return False

def ni_quran(student_text, match_score):
    if match_score >= ACCEPT_SCORE:
        return True
    if match_score < GRAY_ZONE_LOW:
        return False
    return not _ina_dalili_za_uongo(student_text)

# ================= GROQ WHISPER API =================
def transcribe(audio_bytes):
    api_key = st.secrets.get("GROQ_API_KEY", "")
    if not api_key:
        return None, "⚠️ GROQ_API_KEY haijawekwa kwenye Secrets za app."
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("rec.wav", audio_bytes, "audio/wav")},
            data={"model": "whisper-large-v3", "language": "ar",
                  "prompt": "قرآن كريم تلاوة"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["text"], None
    except Exception as e:
        return None, f"⚠️ Tatizo la mtandao/API: {e}"

# ================= UI =================
st.title("🕌 AI USTADH")
st.markdown("**Msaidizi wa Kusoma Qur'an — masahihisho kwa Kiswahili** 🇹🇿  \n"
            "*Juzuu Amma + Al-Fatihah | by Mpenzi, Dar es Salaam*")

with st.expander("🌟 Adabu za Kusoma Qur'ani — soma kwanza!", expanded=False):
    st.markdown("""
1. Kuwa na **twahara** — tawadha kabla ya kusoma
2. Kaa **mahali safi na tulivu**, ukielekea Qibla ikiwezekana
3. Anza kwa **Ta'awwudh**: *A'udhu billahi minash shaytanir rajim*
4. Soma kwa unyenyekevu, **taratibu na tartil**
5. Sikiliza kwa makini unaposahihishwa — **usikate tamaa** 💪
""")

# --- Chagua surah na ayah ---
col1, col2 = st.columns([3, 1])
with col1:
    surah_num = st.selectbox(
        "1️⃣ Chagua Surah",
        sorted(surahs),
        index=len(surahs) - 1,
        format_func=lambda n: f"{n} — {surahs[n]['jina']} ({len(surahs[n]['ayah'])} ayah)",
    )
with col2:
    total = len(surahs[surah_num]["ayah"])
    ayah_num = st.number_input("Ayah", min_value=1, max_value=total, value=1, step=1)

na_tafsiri = st.toggle("🇹🇿 Onyesha tafsiri ya Kiswahili", value=True)

s = surahs[surah_num]
correct = s["ayah"][ayah_num - 1]

st.markdown(f"### 📖 {s['jina']} — Ayah ya {ayah_num}/{total}")
st.markdown(f"<div dir='rtl' style='font-size:2rem; line-height:2.2; text-align:center; "
            f"padding:1rem; background:rgba(0,128,0,0.06); border-radius:12px'>{correct}</div>",
            unsafe_allow_html=True)
if na_tafsiri:
    st.info(f"🇹🇿 **Tafsiri:** {s['tafsiri'][ayah_num - 1]}")

# --- Sheikh audio (moja kwa moja kutoka everyayah) ---
st.markdown("**👂 2️⃣ Msikilize Sheikh Alafasy:**")
st.audio(f"https://everyayah.com/data/Alafasy_128kbps/{surah_num:03d}{ayah_num:03d}.mp3")

# --- Rekodi ---
st.markdown("**🎤 3️⃣ Sasa soma wewe** — bonyeza mic, soma ayah, bonyeza tena kusimamisha:")
rec = st.audio_input("Rekodi usomaji wako", label_visibility="collapsed")

if rec is not None:
    if st.button("✅ 4️⃣ SAHIHISHA USOMAJI WANGU", type="primary", use_container_width=True):
        with st.spinner("🎧 Ustadh anasikiliza..."):
            student, err = transcribe(rec.getvalue())
        if err:
            st.error(err)
        elif not student or not student.strip():
            st.warning("🎤 Sauti haikusikika — karibia mic na usome kwa uwazi.")
        else:
            st.markdown(f"🗣️ **Nilichosikia:** {student}")
            best = max(fuzz.ratio(normalize(student), normalize(a)) for a in s["ayah"])
            if not ni_quran(student, best):
                st.warning("🤔 Samahani, sikusikia Qur'ani vizuri. Soma ayah kwa uwazi, "
                           "mahali pasipo na kelele, kisha jaribu tena.")
            else:
                errors = check_recitation(correct, student)
                if not errors:
                    st.success("## ✅ Masha'Allah! Usomaji wako ni sahihi! 🎉")
                    st.balloons()
                    st.markdown("➡️ Badilisha namba ya ayah hapo juu kuendelea.")
                else:
                    st.error(f"📝 Kuna makosa {len(errors)}:")
                    for e in errors:
                        st.markdown(f"- {e}")
                    st.markdown("👂 **Msikilize Sheikh hapo juu tena, kisha soma tena. Usikate tamaa!** 💪")

# --- Maoni ---
st.divider()
st.markdown("### 💬 Umejaribu? Tuachie maoni yako!")
st.link_button("📨 Andika Maoni Yako Hapa", MAONI_FORM_URL, use_container_width=True)

st.caption("Toleo la majaribio (demo). AI inaweza kukosea — si mbadala wa ustadh halisi mwenye ijaza. 🤲")