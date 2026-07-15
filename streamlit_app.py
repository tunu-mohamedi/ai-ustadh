# 🕌 AI USTADH v3 — Msaidizi wa Kusoma Qur'an (Web, full features)
# by Mpenzi-Kiboga — Dar es Salaam, Tanzania

import re, json, urllib.request, io
import requests
import streamlit as st
from gtts import gTTS
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from collections import Counter

st.set_page_config(page_title="AI Ustadh 🕌", page_icon="🕌", layout="centered")

# ====== WEKA LINK YA GOOGLE FORM YAKO YA MAONI HAPA ======
MAONI_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeuUNkwqq5RwlLP49ziqoGuG8-nzI9fRpMVMfLoG-0ouwPK4A/viewform?pli=1"

# ================= QURAN DATA =================
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
BISMILLAH = "بسم الله الرحمن الرحيم"
BISMILLAH_TAFSIRI = "Kwa jina la Mwenyezi Mungu, Mwingi wa Rehema, Mwenye Kurehemu."
ADABU = [
    "Kuwa na twahara — tawadha kabla ya kusoma Qur'ani.",
    "Kaa mahali safi na tulivu, ukielekea Qibla ikiwezekana.",
    "Anza kwa Ta'awwudh: A'udhu billahi minash shaytanir rajim.",
    "Soma kwa unyenyekevu, taratibu na tartil — usiharakishe.",
    "Sikiliza kwa makini unaposahihishwa, na usikate tamaa.",
]

# ================= BRAIN =================
WORD_TOLERANCE, AYAH_PERFECT, ACCEPT_SCORE, GRAY_ZONE_LOW = 85, 92, 60, 45

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

def detect_ayah_anywhere(student_text):
    student = normalize(student_text)
    best = {"score": 0, "surah": None, "ayah_num": None}
    for num, s2 in surahs.items():
        for i, ayah in enumerate(s2["ayah"]):
            score = fuzz.ratio(student, normalize(ayah))
            if score > best["score"]:
                best = {"score": score, "surah": num, "ayah_num": i + 1}
    return best

def best_in_surah(student_text, surah_num):
    return max(fuzz.ratio(normalize(student_text), normalize(a))
               for a in surahs[surah_num]["ayah"])

# ================= SAUTI =================
@st.cache_data(show_spinner=False)
def sauti_ya_ustadh(text_sw):
    try:
        buf = io.BytesIO()
        gTTS(text_sw, lang="sw").write_to_fp(buf)
        return buf.getvalue()
    except Exception:
        return None

def sema(text_sw):
    if st.session_state.get("sauti_on", True):
        audio = sauti_ya_ustadh(text_sw)
        if audio:
            st.audio(audio, format="audio/mp3", autoplay=True)

RECITERS = {
    "Mishary Alafasy":   "Alafasy_128kbps",
    "Abdul Basit":       "Abdul_Basit_Murattal_64kbps",
    "Mahmoud Al-Husary": "Husary_128kbps",
    "Mohamed Minshawy":  "Minshawy_Murattal_128kbps",
    "Saad Al-Ghamdi":    "Ghamadi_40kbps",
}

def sheikh_url(surah_num, ayah_num):
    folder = RECITERS[st.session_state.get("qari", "Mishary Alafasy")]
    return f"https://everyayah.com/data/{folder}/{surah_num:03d}{ayah_num:03d}.mp3"

TAFSIRI_SOURCES = ["Tafsiriyaquran",
                   "TranslationOfTheMeaningsOfTheNobleQuranInSwahilikiswahilimp3"]

@st.cache_data(show_spinner=False)
def human_tafsiri_url(surah_num):
    from urllib.parse import quote
    for archive_id in TAFSIRI_SOURCES:
        try:
            with urllib.request.urlopen(f"https://archive.org/metadata/{archive_id}") as r:
                meta = json.loads(r.read())
            files = [f["name"] for f in meta["files"]
                     if f["name"].lower().endswith((".ogg", ".mp3"))]
            match = [f for f in files if f.startswith(f"{surah_num:03d}")]
            if match:
                return f"https://archive.org/download/{archive_id}/{quote(match[0])}"
        except Exception:
            continue
    return None

# ================= GROQ API =================
def transcribe(audio_bytes):
    api_key = st.secrets.get("GROQ_API_KEY", "")
    if not api_key:
        return None, "⚠️ GROQ_API_KEY haijawekwa kwenye Secrets."
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

# ================= SESSION STATE =================
ss = st.session_state
defaults = dict(mode=None, surah=None, ayah=1, tries=0, first_try=0, attempts=0,
                completed=0, phase="adabu", peeked=0, na_tafsiri=True,
                log=[], sessions=[], last_result=None)
for k, v in defaults.items():
    if k not in ss:
        ss[k] = v

def reset_session():
    for k in ["mode", "surah"]:
        ss[k] = None
    ss.ayah, ss.tries, ss.first_try, ss.attempts = 1, 0, 0, 0
    ss.completed, ss.phase, ss.peeked, ss.last_result = 0, "adabu", 0, None

def finish_session(quit_early=False):
    total = len(surahs[ss.surah]["ayah"]) if ss.surah else 0
    ss.sessions.append({"surah": surahs[ss.surah]["jina"], "mode": ss.mode,
                        "first_try": ss.first_try,
                        "completed": ss.completed, "total": total,
                        "attempts": ss.attempts, "quit": quit_early})

def show_ayah_box(text, size="2rem"):
    st.markdown(f"<div dir='rtl' style='font-size:{size}; line-height:2.2; text-align:center; "
                f"padding:1rem; background:rgba(0,128,0,0.06); border-radius:12px'>{text}</div>",
                unsafe_allow_html=True)

def handle_recitation(correct, surah_num, ayah_num, rec, hidden=False):
    """Rudisha True kama ayah imekamilika (sahihi)."""
    student, err = transcribe(rec.getvalue())
    ss.attempts += 1
    ss.tries += 1
    if err:
        ss.last_result = ("error", err, None)
        return False
    if not student or not student.strip():
        ss.last_result = ("warn", "🎤 Sauti haikusikika — karibia mic na usome kwa uwazi.", None)
        return False
    if not ni_quran(student, best_in_surah(student, surah_num)):
        ss.last_result = ("warn",
                          f"🗣️ Nilichosikia: {student}\n\n🤔 Sikusikia Qur'ani vizuri. "
                          "Soma kwa uwazi mahali tulivu.", "Samahani, sikusikia Qur'ani vizuri. Soma tena kwa uwazi.")
        return False
    errors = check_recitation(correct, student)
    if not errors:
        if ss.tries == 1 and ss.peeked == 0:
            ss.first_try += 1
        ss.last_result = ("ok", f"🗣️ Nilichosikia: {student}", "Masha Allah! Vizuri sana.")
        return True
    for e in errors:
        ss.log.append({"surah": surahs[surah_num]["jina"], "ayah": ayah_num, "kosa": e})
    msg = f"🗣️ Nilichosikia: {student}\n\n📝 **Makosa {len(errors)}:**\n" + \
          "\n".join(f"- {e}" for e in errors)
    ss.last_result = ("err", msg,
                      f"Kuna makosa {len(errors)}. Msikilize Sheikh kwa makini, kisha soma tena.")
    return False

def show_last_result():
    if not ss.last_result:
        return
    kind, msg, voice = ss.last_result
    if kind == "ok":
        st.markdown(msg)
        st.success("## ✅ Masha'Allah! Usomaji sahihi! 🎉")
    elif kind == "err":
        st.error(msg)
    elif kind == "warn":
        st.warning(msg)
    else:
        st.error(msg)
    if voice:
        sema(voice)
    ss.last_result = None

# ================= SIDEBAR (MIPANGILIO) =================
with st.sidebar:
    st.header("⚙️ Mipangilio")
    ss.sauti_on = st.toggle("🗣️ Sauti ya Ustadh (Kiswahili)", value=ss.get("sauti_on", True))
    ss.qari = st.selectbox("🎙️ Chagua Msomaji (Qari)", list(RECITERS), index=0)
    st.divider()
    st.caption("Ukiwa ndani ya somo, bonyeza '🚪 Acha Somo' kusitisha wakati wowote — "
               "maendeleo yako yatahifadhiwa kwenye Ripoti.")

# ================= UI =================
st.title("🕌 AI USTADH")
st.markdown("**Msaidizi wa Kusoma Qur'an — masahihisho kwa Kiswahili** 🇹🇿  \n"
            "*Juzuu Amma + Al-Fatihah | by Mpenzi, Dar es Salaam*")

tab_somo, tab_hifz, tab_tambua, tab_ripoti = st.tabs(
    ["📖 Somo na Ustadh", "🧠 Hifz Mode", "🔍 Tambua Surah", "📊 Ripoti"])

# ═══════════════ TAB 1: SOMO (GUIDED SESSION) ═══════════════
with tab_somo:
    if ss.mode != "somo":
        st.markdown("### Anza somo la kuongozwa — kama madrasa halisi!")
        st.caption("Ustadh atakukumbusha adabu, mtaanza na Bismillah, kisha ayah kwa ayah: "
                   "Sheikh anasoma → wewe unasoma → unasahihishwa.")
        c1, c2 = st.columns([3, 1])
        with c1:
            pick = st.selectbox("Chagua Surah", sorted(surahs),
                                index=len(surahs) - 1,
                                format_func=lambda n: f"{n} — {surahs[n]['jina']} ({len(surahs[n]['ayah'])} ayah)",
                                key="pick_somo")
        with c2:
            ss.na_tafsiri = st.toggle("🇹🇿 Tafsiri", value=True, key="taf_somo")
        if st.button("🕌 ANZA SOMO", type="primary", use_container_width=True):
            reset_session()
            ss.mode, ss.surah, ss.phase = "somo", pick, "adabu"
            st.rerun()
    else:
        s = surahs[ss.surah]
        total = len(s["ayah"])
        top1, top2 = st.columns([3, 1])
        with top1:
            st.markdown(f"### 🕌 {s['jina']} — {'Adabu' if ss.phase=='adabu' else ('Bismillah' if ss.phase=='bismillah' else f'Ayah {ss.ayah}/{total}')}")
        with top2:
            if st.button("🚪 Acha Somo", use_container_width=True):
                finish_session(quit_early=True)
                done_at = ss.completed
                reset_session()
                st.info(f"⏸️ Somo limesitishwa — maendeleo yamehifadhiwa kwenye 📊 Ripoti.")
                st.rerun()
        st.progress(ss.completed / total)

        # ---- PHASE: ADABU ----
        if ss.phase == "adabu":
            st.markdown("#### 🌟 Ukumbusho: Adabu za Kusoma Qur'ani")
            for n, a in enumerate(ADABU, 1):
                st.markdown(f"{n}. {a}")
            sema("Bismillahir rahmanir rahim. Karibu mwanafunzi! Kabla hatujaanza, "
                 "kumbuka adabu za kusoma Qur'ani tukufu. " + " ".join(ADABU))
            if st.button("✅ Niko tayari — twende!", type="primary", use_container_width=True):
                ss.phase = "bismillah" if ss.surah != 1 else "ayah"
                ss.tries = 0
                st.rerun()

        # ---- PHASE: BISMILLAH ----
        elif ss.phase == "bismillah":
            st.markdown("#### 🌙 Tunaanza na Bismillah")
            show_ayah_box(BISMILLAH)
            if ss.na_tafsiri:
                st.info(f"🇹🇿 **Tafsiri:** {BISMILLAH_TAFSIRI}")
            st.markdown("**👂 Msikilize Sheikh:**")
            st.audio(sheikh_url(1, 1))
            st.markdown("**🎤 Sasa soma Bismillah wewe:**")
            rec = st.audio_input("Rekodi", label_visibility="collapsed",
                                 key=f"bis_{ss.attempts}")
            if rec and st.button("✅ SAHIHISHA", type="primary", use_container_width=True):
                student, err = transcribe(rec.getvalue())
                if student and fuzz.ratio(normalize(student), normalize(BISMILLAH)) >= GRAY_ZONE_LOW:
                    sema("Vizuri sana! Sasa tuanze surah.")
                    st.success("✅ Vizuri sana!")
                else:
                    sema("Haya, tuanze surah.")
                ss.phase, ss.tries = "ayah", 0
                st.rerun()

        # ---- PHASE: AYAH ----
        elif ss.phase == "ayah":
            correct = s["ayah"][ss.ayah - 1]
            show_last_result()
            show_ayah_box(correct)
            if ss.na_tafsiri and ss.tries == 0:      # tafsiri jaribio la KWANZA tu
                st.info(f"🇹🇿 **Tafsiri:** {s['tafsiri'][ss.ayah - 1]}")
            st.markdown("**👂 Msikilize Sheikh:**")
            st.audio(sheikh_url(ss.surah, ss.ayah))
            st.markdown("**🎤 Sasa soma wewe** *(baada ya kurekodi, bonyeza ▶ kujisikiliza)*:")
            rec = st.audio_input("Rekodi", label_visibility="collapsed",
                                 key=f"somo_{ss.ayah}_{ss.tries}")
            if rec and st.button("✅ SAHIHISHA", type="primary", use_container_width=True):
                ok = handle_recitation(correct, ss.surah, ss.ayah, rec)
                if ok:
                    ss.completed = ss.ayah
                    if ss.ayah >= total:
                        finish_session()
                        ss.phase = "done"
                    else:
                        ss.ayah += 1
                        ss.tries = 0
                st.rerun()

        # ---- PHASE: DONE ----
        elif ss.phase == "done":
            show_last_result()
            st.balloons()
            st.success(f"## 🏆 HONGERA! Umemaliza {s['jina']}!")
            st.markdown(f"⭐ **Sahihi mara ya kwanza:** {ss.first_try}/{total}  \n"
                        f"📊 **Majaribio jumla:** {ss.attempts}")
            sema(f"Hongera! Umemaliza surah {s['jina']}. Alhamdulillah!")
            if st.button("🔄 Somo jingine", type="primary", use_container_width=True):
                reset_session()
                st.rerun()

# ═══════════════ TAB 2: HIFZ MODE ═══════════════
with tab_hifz:
    if ss.mode != "hifz":
        st.markdown("### 🧠 Hifz Mode — ayah ZIMEFICHWA, soma kwa kumbukumbu!")
        pick_h = st.selectbox("Chagua Surah", sorted(surahs),
                              index=len(surahs) - 1,
                              format_func=lambda n: f"{n} — {surahs[n]['jina']} ({len(surahs[n]['ayah'])} ayah)",
                              key="pick_hifz")
        if st.button("🧠 ANZA HIFZ", type="primary", use_container_width=True):
            reset_session()
            ss.mode, ss.surah, ss.phase = "hifz", pick_h, "ayah"
            st.rerun()
    else:
        s = surahs[ss.surah]
        total = len(s["ayah"])
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(f"### 🧠 {s['jina']} — Ayah {ss.ayah}/{total} (imefichwa)")
        with h2:
            if st.button("🚪 Acha Hifz", use_container_width=True):
                finish_session(quit_early=True)
                reset_session()
                st.info("⏸️ Hifz imesitishwa — maendeleo yamehifadhiwa kwenye 📊 Ripoti.")
                st.rerun()
        st.progress(ss.completed / total)

        if ss.phase == "done":
            show_last_result()
            st.balloons()
            st.success(f"## 🏆 Umemaliza hifz ya {s['jina']}!")
            st.markdown(f"⭐ **Bila kuchungulia, mara ya kwanza:** {ss.first_try}/{total}")
            sema(f"Hongera! Umemaliza hifz ya surah {s['jina']}!")
            if st.button("🔄 Hifz nyingine", type="primary", use_container_width=True):
                reset_session()
                st.rerun()
        else:
            correct = s["ayah"][ss.ayah - 1]
            words = normalize(correct).split()
            show_last_result()
            if ss.peeked >= len(words):
                show_ayah_box(correct, size="1.6rem")
            elif ss.peeked > 0:
                show_ayah_box(" ".join(words[:ss.peeked]) + " …", size="1.6rem")
            else:
                show_ayah_box("🙈 " * min(len(words), 8), size="1.6rem")
            pc1, pc2 = st.columns(2)
            with pc1:
                if st.button("👀 Chungulia neno", use_container_width=True):
                    ss.peeked = min(ss.peeked + 1, len(words))
                    st.rerun()
            with pc2:
                if st.button("📜 Onyesha ayah nzima", use_container_width=True):
                    ss.peeked = len(words)
                    st.rerun()
            st.markdown("**🎤 Soma kwa kumbukumbu yako:**")
            rec = st.audio_input("Rekodi", label_visibility="collapsed",
                                 key=f"hifz_{ss.ayah}_{ss.tries}")
            if rec and st.button("✅ SAHIHISHA", type="primary", use_container_width=True):
                ok = handle_recitation(correct, ss.surah, ss.ayah, rec, hidden=True)
                if ok:
                    ss.completed = ss.ayah
                    if ss.ayah >= total:
                        finish_session()
                        ss.phase = "done"
                    else:
                        ss.ayah += 1
                        ss.tries, ss.peeked = 0, 0
                else:
                    st.session_state["show_sheikh_hint"] = True
                st.rerun()
            if ss.tries > 0:
                st.markdown("**👂 Msikilize Sheikh (msaada):**")
                st.audio(sheikh_url(ss.surah, ss.ayah))

# ═══════════════ TAB 3: TAMBUA SURAH ═══════════════
with tab_tambua:
    st.markdown("### 🔍 Soma ayah YOYOTE — AI itaitambua! (Shazam ya Qur'ani 😄)")
    rec2 = st.audio_input("Rekodi ayah yoyote", label_visibility="collapsed", key="tambua_mic")
    if rec2 and st.button("🔍 TAMBUA AYAH HII", type="primary", use_container_width=True):
        with st.spinner("🎧 Natafuta..."):
            student2, err2 = transcribe(rec2.getvalue())
        if err2:
            st.error(err2)
        elif not student2 or not student2.strip():
            st.warning("🎤 Sauti haikusikika.")
        else:
            st.markdown(f"🗣️ **Nilichosikia:** {student2}")
            m = detect_ayah_anywhere(student2)
            if not ni_quran(student2, m["score"]):
                st.warning("🤔 Samahani, sikusikia Qur'ani.")
                sema("Samahani, sikusikia Qur'ani.")
            else:
                s2 = surahs[m["surah"]]
                st.success(f"## 📖 {s2['jina']} — Ayah ya {m['ayah_num']} (uhakika: {m['score']:.0f}%)")
                show_ayah_box(s2["ayah"][m["ayah_num"] - 1], size="1.6rem")
                st.info(f"🇹🇿 **Tafsiri:** {s2['tafsiri'][m['ayah_num'] - 1]}")
                sema(f"Nimeitambua! Ni surah {s2['jina']}, ayah ya {m['ayah_num']}.")

# ═══════════════ TAB 4: RIPOTI ═══════════════
with tab_ripoti:
    st.markdown("### 📊 Ripoti ya Kipindi Hiki")
    st.caption("⚠️ Ripoti hii ni ya kipindi hiki tu — ukifunga ukurasa, inaanza upya. "
               "(Kumbukumbu ya kudumu itakuja kwenye app kamili ya simu, insha Allah.)")
    if not ss.sessions and not ss.log:
        st.info("Bado hujasoma — anza somo kwenye tab ya 📖 au 🧠!")
    if ss.sessions:
        st.markdown("#### 🏆 Vipindi vyako:")
        for sn in ss.sessions:
            icon = "🧠" if sn["mode"] == "hifz" else "📖"
            status = "⏸️ ilisitishwa" if sn["quit"] else "✅ imekamilika"
            st.markdown(f"- {icon} **{sn['surah']}** — {sn['completed']}/{sn['total']} ayah, "
                        f"⭐ {sn['first_try']} mara ya kwanza, majaribio {sn['attempts']} ({status})")
    if ss.log:
        st.markdown("#### 🔁 Sehemu ulizokosea mara nyingi (zirudie!):")
        counts = Counter((e["surah"], e["ayah"]) for e in ss.log)
        for (sr, ay), n in counts.most_common(5):
            st.markdown(f"- **{sr}, Ayah ya {ay}** — mara {n}")
        with st.expander("Angalia makosa yote"):
            for e in ss.log:
                st.markdown(f"- {e['surah']}, Ayah {e['ayah']}: {e['kosa']}")

    if st.session_state.get("na_tafsiri") is not None:
        pass
    st.divider()
    st.markdown("#### 🎧 Sikiliza surah nzima na tafsiri ya sauti halisi")
    pick_t = st.selectbox("Chagua surah", sorted(surahs),
                          format_func=lambda n: f"{n} — {surahs[n]['jina']}",
                          key="pick_taf")
    if st.button("🎧 Pakia sauti", use_container_width=True):
        url = human_tafsiri_url(pick_t)
        if url:
            st.audio(url)
        else:
            st.warning("Haipatikani kwa surah hii kwa sasa.")

# ================= MAONI =================
st.divider()
st.markdown("### 💬 Umejaribu? Tuachie maoni yako!")
st.link_button("📨 Andika Maoni Yako Hapa", MAONI_FORM_URL, use_container_width=True)
st.caption("Toleo la majaribio (demo). AI inaweza kukosea — si mbadala wa ustadh halisi mwenye ijaza. 🤲")
