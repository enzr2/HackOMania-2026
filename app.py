import streamlit as st
import os, re, csv, tempfile, base64
from datetime import datetime
from openai import OpenAI

OPENAI_API_KEY = "API KEY HERE"
#API Key will be added by the user
LOG_PATH = "pab_session_log.csv"
LOG_FIELDS = [
    "log_timestamp", "filename", "processed_at", "topic",
    "urgency_original", "urgency_current", "severity_score",
    "confidence", "language", "misclick", "status",
    "cleared_as", "transcript", "translated_transcript", "raw_ai_output",
]

st.set_page_config(page_title="PAB · Emergency Triage", page_icon="", layout="wide", initial_sidebar_state="collapsed")

for key, val in [("results", []), ("active_tab", "dashboard"), ("history", [])]:
    if key not in st.session_state:
        st.session_state[key] = val

URGENCY_COLORS = {
    "URGENT_EMPTY": "#ff3333", "URGENT": "#ff5c5c",
    "MEDIUM": "#f59e0b", "LOW": "#22c55e",
    "MISCLICK": "#4a5568", "UNKNOWN": "#6366f1",
}
SECTION_ORDER  = ["URGENT_EMPTY", "URGENT", "MEDIUM", "LOW", "MISCLICK"]
SECTION_LABELS = {
    "URGENT_EMPTY": "🔴 URGENT — No Message", "URGENT": "🔴 URGENT",
    "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW", "MISCLICK": "⚫ MISCLICK",
}
STATUS_OPTIONS = ["New", "Acknowledged", "Dispatched", "Resolved"]
STATUS_COLORS  = {"New": "#60a5fa", "Acknowledged": "#fbbf24", "Dispatched": "#a78bfa", "Resolved": "#4ade80"}

def cleared_label(urgency, status):
    if urgency == "MISCLICK" or status == "Resolved": return "Ignored / Resolved"
    if urgency in ("URGENT_EMPTY", "URGENT", "MEDIUM"): return "Dispatched to Paramedics"
    return "Logged / Monitored"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
* { font-family: 'Space Grotesk', sans-serif; }
.stApp { background: #080b10; color: #e2e8f0; }
.main .block-container { padding: 0 2rem 2rem 2rem; max-width: 1400px; }
#MainMenu, footer, header { visibility: hidden; }

.topbar { display:flex; align-items:flex-end; justify-content:space-between; padding:1.2rem 0 0 0; border-bottom:2px solid #1a2030; margin-bottom:1.8rem; }
.pab-logo { font-family:'JetBrains Mono',monospace; font-size:1.6rem; font-weight:700; color:#ff3c3c; letter-spacing:.15em; }
.pab-sub { font-size:.68rem; color:#ffffff; text-transform:uppercase; letter-spacing:.12em; margin-top:2px; }



.sec-label { font-size:.63rem; color:#ffffff; text-transform:uppercase; letter-spacing:.14em; font-weight:700; margin-bottom:.4rem; }
.field-label { font-size:.6rem; color:#ffffff; text-transform:uppercase; letter-spacing:.12em; font-weight:600; margin-bottom:2px; }

.mbox { background:#0d1117; border:1px solid #1a2030; border-radius:10px; padding:.8rem; text-align:center; }
.mval { font-size:1.8rem; font-weight:700; font-family:'JetBrains Mono',monospace; line-height:1; }
.mlbl { font-size:.6rem; color:#4a5568; text-transform:uppercase; letter-spacing:.1em; margin-top:.25rem; }

.card { background:#0d1117; border:1px solid #1a2030; border-radius:10px; padding:1rem 1.2rem; margin-bottom:.8rem; }
.upill { display:inline-block; padding:2px 9px; border-radius:20px; font-size:.66rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; font-family:'JetBrains Mono',monospace; }
.tx-box { background:#060810; border:1px solid #1a2030; border-radius:6px; padding:.6rem .9rem; font-size:.83rem; color:#a0b0c8; line-height:1.6; margin-top:.3rem; }
.tr-box { background:#04090f; border:1px solid #0e2535; border-radius:6px; padding:.6rem .9rem; font-size:.83rem; color:#7ab8d4; line-height:1.6; margin-top:.3rem; }
.cbar-bg { background:#1a2030; border-radius:3px; height:4px; overflow:hidden; }
.cbar-fill { height:100%; border-radius:3px; background:linear-gradient(90deg,#2563eb,#60a5fa); }
.sevbar-fill { height:100%; border-radius:3px; background:linear-gradient(90deg,#ff3c3c,#ff8080); }
.big-num { font-size:1.05rem; font-family:'JetBrains Mono',monospace; color:#c0cfe0; }
audio { width:100%; height:30px; border-radius:6px; filter:invert(1) hue-rotate(180deg) brightness(.85); }

.sec-ue [data-testid="stExpander"]>div:first-child { background:#1a0505!important; border:1px solid #5c1010!important; border-radius:8px!important; color:#ff6b6b!important; }
.sec-u  [data-testid="stExpander"]>div:first-child { background:#150808!important; border:1px solid #4a1515!important; border-radius:8px!important; color:#ff8080!important; }
.sec-m  [data-testid="stExpander"]>div:first-child { background:#141005!important; border:1px solid #4a3510!important; border-radius:8px!important; color:#fbbf24!important; }
.sec-l  [data-testid="stExpander"]>div:first-child { background:#071410!important; border:1px solid #0f4025!important; border-radius:8px!important; color:#4ade80!important; }
.sec-mc [data-testid="stExpander"]>div:first-child { background:#0d1018!important; border:1px solid #2a3448!important; border-radius:8px!important; color:#94a3b8!important; }
[data-testid="stExpander"] summary p { color:inherit!important; font-family:'JetBrains Mono',monospace!important; font-size:.83rem!important; font-weight:700!important; }

[data-testid="stButton"] button[kind="secondary"] { background:transparent!important; border:1px solid #2a3448!important; color:#4a5568!important; font-size:.75rem!important; padding:2px 6px!important; border-radius:6px!important; }
[data-testid="stButton"] button[kind="secondary"]:hover { border-color:#ff4444!important; color:#ff6b6b!important; background:#1a0505!important; }
[data-testid="stFileUploader"] button { background:#1d4ed8!important; color:#fff!important; border:1px solid #2563eb!important; border-radius:6px!important; }

.stat-row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:1.2rem; }
.stat-chip { padding:4px 12px; border-radius:20px; font-size:.7rem; font-family:'JetBrains Mono',monospace; font-weight:600; border:1px solid; }
.empty-state { text-align:center; padding:4rem 2rem; color:#ffffff; }
</style>
""", unsafe_allow_html=True)

# ── Logging ───────────────────────────────────────────────────────────────────
def ensure_log():
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()

def log_entry(r):
    ensure_log()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=LOG_FIELDS).writerow({
            "log_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filename": r.get("filename",""), "processed_at": r.get("timestamp",""),
            "topic": r.get("topic",""), "urgency_original": r.get("urgency_original", r.get("urgency","")),
            "urgency_current": r.get("urgency",""), "severity_score": r.get("severity_score",""),
            "confidence": r.get("confidence",""), "language": r.get("language",""),
            "misclick": r.get("misclick", False), "status": r.get("status","New"),
            "cleared_as": r.get("cleared_as",""), "transcript": r.get("original_transcript",""),
            "translated_transcript": r.get("translated_transcript",""), "raw_ai_output": r.get("raw",""),
        })

def update_log(filename, status, urgency, cleared_as=""):
    ensure_log()
    try:
        rows = list(csv.DictReader(open(LOG_PATH, encoding="utf-8")))
    except Exception: return
    for row in reversed(rows):
        if row.get("filename") == filename:
            row["urgency_current"] = urgency; row["status"] = status
            if cleared_as: row["cleared_as"] = cleared_as
            break
    with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS); w.writeheader(); w.writerows(rows)

def read_log_bytes():
    ensure_log()
    return open(LOG_PATH, "rb").read()

# ── Text helpers ──────────────────────────────────────────────────────────────
def ep(t):
    t = t.strip(); return t + "." if t and t[-1] not in ".!?" else t

def fmt_bullet(raw):
    t = raw.lstrip("•-* ").strip()
    return ep(t[0].upper() + t[1:]) if t else t

def fmt_tx(raw):
    if not raw: return raw
    t = re.sub(r' {2,}', ' ', raw.strip())
    t = re.sub(r'([.!?])\s+([a-z])', lambda m: m.group(1)+' '+m.group(2).upper(), t)
    return ep(t[0].upper() + t[1:] if t else t)

def derive_topic(bullets, urgency):
    if bullets:
        t = bullets[0]
        for prefix in ("the caller reports ", "caller reports ", "the caller is ", "caller is ",
                       "no verbal response detected.", "no verbal response detected,"):
            if t.lower().startswith(prefix):
                t = t[len(prefix):].strip()
                t = t[0].upper() + t[1:] if t else t
                break
        return t[:52].rstrip(" ,.") + ("…" if len(t) > 52 else "")
    return urgency.replace("_"," ").title()

# ── AI parser ─────────────────────────────────────────────────────────────────
def parse_ai(text):
    r = {"summary_bullets":[], "urgency":"UNKNOWN", "misclick":False,
         "confidence":0, "language":"English", "translated_transcript":"",
         "severity_score":50, "raw":text}
    r["summary_bullets"] = [fmt_bullet(l.strip()) for l in text.splitlines()
                             if l.strip().startswith(("•","-","*")) and len(l.strip())>2][:3]
    for lvl in ["URGENT","MEDIUM","LOW"]:
        if lvl in text.upper(): r["urgency"] = lvl; break
    if any(w in text.lower() for w in ["misclick: yes","misclick likelihood: yes"]):
        r["misclick"] = True; r["urgency"] = "MISCLICK"
    m = re.search(r'confidence[^\d]*(\d{1,3})\s*%', text, re.I) or re.search(r'(\d{1,3})\s*%', text)
    if m: r["confidence"] = min(int(m.group(1)),100)
    m = re.search(r'language[^\n:]*[:\-]\s*([A-Za-z]+)', text, re.I)
    if m: r["language"] = m.group(1).strip()
    m = re.search(r'(?:translated message|english translation|translation)[^\n]*\n(.+?)(?:\n\n|\n[-*•]|\Z)', text, re.I|re.S)
    if m:
        v = m.group(1).strip()
        if v.upper() not in ("N/A","NA","NONE",""): r["translated_transcript"] = fmt_tx(v)
    m = re.search(r'severity[^\d]*(\d{1,3})', text, re.I)
    if m: r["severity_score"] = min(int(m.group(1)),100)
    return r

# ── Audio processing ──────────────────────────────────────────────────────────
def process_audio(file_bytes, filename):
    client = OpenAI(api_key=OPENAI_API_KEY)
    suffix = os.path.splitext(filename)[-1].lower() or ".m4a"
    mime_map = {".m4a":"audio/mp4",".mp4":"audio/mp4",".mp3":"audio/mpeg",
                ".mpga":"audio/mpeg",".wav":"audio/wav",".ogg":"audio/ogg",
                ".oga":"audio/ogg",".flac":"audio/flac",".webm":"audio/webm"}
    mime = mime_map.get(suffix,"audio/mp4")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes); tmp_path = tmp.name
    with open(tmp_path,"rb") as af:
        tx = client.audio.transcriptions.create(model="gpt-4o-transcribe", file=(filename,af,mime))
    transcript = fmt_tx(tx.text)
    os.unlink(tmp_path)

    prompt = f"""You are an AI assistant for emergency hotline responders. Analyze the transcript below.

READ THIS FIRST

MISCLICK definition (STRICT):
A misclick is ONLY when ALL of the following are true:
  1. The transcript is completely empty, OR contains only non-human sounds
     (dial tones, hold music, static, white noise, pocket sounds).
  2. There are zero intelligible words or voices of any kind.
  3. There is no emotional content — no crying, shouting, groaning, or distress sounds.
If ANY human voice, word, or emotional sound is detected, it is NOT a misclick.
A faint voice, a voice in the background, or a voice in a foreign language is still a real call, but attempt to identify whether it was really a misclick or not.
Ambient street noise, crowd noise, or a TV in the background alone does NOT make it a misclick
if a human voice is also present.

URGENT (No Response) definition:
The transcript is empty or near-empty (fewer than 5 meaningful words) AND it is not a misclick
(e.g. there was audio but no intelligible speech, or the caller said nothing but the line was open).
This must be treated as a potential emergency — the caller may be unable to speak.

============================

STEP 1 - SUMMARY
Write up to 3 bullet points summarising the situation.
Each bullet should be concise, while including key words or phrases.
Focus on: nature of emergency, location if mentioned, caller condition.
If the transcript is empty or has no useful content, write a single bullet:
  - "No verbal response detected. Caller may be unable to speak."

STEP 2 - MISCLICK CHECK
Apply the STRICT misclick definition above.
Answer exactly one line: Misclick: Yes  OR  Misclick: No

STEP 3 - URGENCY
(Complete this step even if you answered Misclick: Yes — assign MISCLICK as the urgency.)
Assign ONE of these levels:
- URGENT: life-threatening or immediate danger (cardiac arrest, stroke, severe bleeding,
  fire, assault, unconscious, no verbal response from caller, etc.)
- MEDIUM: significant but not immediately life-threatening (moderate injury, fall with pain,
  mental health crisis, distressed caller)
- LOW: minor or non-emergency (minor cut, headache, wellness check, calm caller with
  minor complaint)
- MISCLICK: only if you answered Misclick: Yes above

STEP 4 - SEVERITY SCORE
Rate the specific severity 1-100 within the urgency tier, so calls can be ranked against each other.
Use clinical logic — higher = more immediately life-threatening or time-critical.
Examples: cardiac arrest=98, building fire=92, severe unconscious fall=85, assault in progress=80,
broken arm=60, moderate fall with pain=45, minor fall=30, headache=15, misclick=0.
Answer exactly one line: Severity: <number>

STEP 5 - LANGUAGE & TRANSLATION
Detect the language spoken. Even partial words count for language detection.
Answer on exactly two lines:
Language: <language name>
Translated message: <full English translation of the transcript, or N/A if already English>

STEP 6 - CONFIDENCE
How confident are you in your overall assessment?
Answer exactly one line: Confidence: <number>%

Transcript: {transcript}"""

    resp = client.chat.completions.create(model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}], max_tokens=800)
    parsed = parse_ai(resp.choices[0].message.content)
    parsed.update({"filename":filename, "timestamp":datetime.now().strftime("%H:%M:%S"),
                   "date":datetime.now().strftime("%Y-%m-%d"), "original_transcript":transcript,
                   "audio_bytes":file_bytes, "audio_mime":mime, "status":"New", "cleared_as":""})
    if parsed["urgency"] == "URGENT" and len(transcript.strip()) < 10:
        parsed["urgency"] = "URGENT_EMPTY"
    parsed["urgency_original"] = parsed["urgency"]
    parsed["topic"] = derive_topic(parsed["summary_bullets"], parsed["urgency"])
    log_entry(parsed)
    return parsed

def audio_b64(b, m): return f"data:{m};base64,{base64.b64encode(b).decode()}"
def audio_html(uri): return f'<audio controls preload="metadata"><source src="{uri}"></audio>'

def bucket_sort(results):
    bkts = {k:[] for k in SECTION_ORDER}
    for r in results:
        k = r.get("urgency","UNKNOWN"); bkts[k if k in bkts else "URGENT"].append(r)
    for k in bkts: bkts[k].sort(key=lambda x:(-x.get("severity_score",0),-x.get("confidence",0)))
    return bkts

SEC_CSS = {"URGENT_EMPTY":"sec-ue","URGENT":"sec-u","MEDIUM":"sec-m","LOW":"sec-l","MISCLICK":"sec-mc"}

# ── Card ──────────────────────────────────────────────────────────────────────
def render_card(r, rank, gidx):
    urgency  = r.get("urgency","UNKNOWN")
    color    = URGENCY_COLORS.get(urgency,"#6366f1")
    disp_urg = "URGENT" if urgency=="URGENT_EMPTY" else urgency
    status   = r.get("status","New")
    sc       = STATUS_COLORS.get(status,"#60a5fa")
    sev      = r.get("severity_score","—")
    conf     = r.get("confidence",0)
    lang     = r.get("language","English")
    bullets  = r.get("summary_bullets",[])
    orig     = r.get("original_transcript","")
    transl   = r.get("translated_transcript","")
    ab       = r.get("audio_bytes",b"")
    am       = r.get("audio_mime","audio/mp4")
    show_tr  = bool(transl and transl.strip().upper() not in ("N/A","NA","") and lang.lower() not in ("english","en"))

    st.markdown(f"""
    <div class="card" style="border-left:4px solid {color};">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div>
          <span style="font-family:monospace;font-size:.65rem;color:#3d4f66;background:#0a0e14;border:1px solid #1a2030;border-radius:4px;padding:1px 6px;margin-right:8px;">#{rank:02d}</span>
          <strong style="font-size:.95rem;">{r.get("filename","?")}</strong>
          <span style="font-size:.65rem;color:#3d4f66;margin-left:8px;font-family:monospace;">{r.get("timestamp","")}</span>
        </div>
        <div style="display:flex;gap:6px;align-items:center;">
          <span class="upill" style="background:{color}22;color:{color};border:1px solid {color}44;">{disp_urg}</span>
          <span class="upill" style="background:{sc}15;color:{sc};border:1px solid {sc}40;">{status}</span>
          <span style="font-size:.65rem;color:#4a5568;font-family:monospace;">{lang}</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    for b in bullets:
        st.markdown(f'<div style="font-size:.86rem;color:#c0cfe0;margin:2px 0;"><span style="color:{color};margin-right:6px;">•</span>{b}</div>', unsafe_allow_html=True)
    if not bullets:
        st.markdown('<div style="font-size:.84rem;color:#4a5568;font-style:italic;">No summary.</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown('<div class="field-label">Confidence</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="cbar-bg"><div class="cbar-fill" style="width:{conf}%;"></div></div><div style="font-size:.72rem;color:#7a8fa8;font-family:monospace;margin-top:2px;">{conf}%</div>', unsafe_allow_html=True)
    with m2:
        st.markdown('<div class="field-label">Severity</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="cbar-bg"><div class="sevbar-fill" style="width:{sev}%;"></div></div><div class="big-num" style="margin-top:2px;">{sev}/100</div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="field-label">Misclick</div><div style="font-size:.85rem;">{"🔴 Yes" if r.get("misclick") else "🟢 No"}</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    with d1:
        st.markdown('<div class="field-label">Status</div>', unsafe_allow_html=True)
        ns = st.selectbox("s", STATUS_OPTIONS, index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0, key=f"s_{gidx}", label_visibility="collapsed")
        if ns != status:
            st.session_state.results[gidx]["status"] = ns
            update_log(r.get("filename",""), ns, urgency); st.rerun()
    with d2:
        st.markdown('<div class="field-label">Override Urgency</div>', unsafe_allow_html=True)
        uopts = ["URGENT_EMPTY","URGENT","MEDIUM","LOW","MISCLICK"]
        nu = st.selectbox("u", uopts, index=uopts.index(urgency) if urgency in uopts else 1, key=f"u_{gidx}", label_visibility="collapsed")
        if nu != urgency:
            st.session_state.results[gidx]["urgency"] = nu
            update_log(r.get("filename",""), status, nu); st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    cur_urgency = st.session_state.results[gidx]["urgency"]
    cur_status  = st.session_state.results[gidx]["status"]
    clabel      = cleared_label(cur_urgency, cur_status)

    if st.button("✔ Clear & Send to History", key=f"clr_{gidx}", use_container_width=True):
        entry = st.session_state.results[gidx].copy()
        entry["cleared_as"] = clabel
        entry["cleared_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry["topic"]      = r.get("topic", derive_topic(bullets, entry["urgency"]))
        update_log(entry.get("filename",""), entry["status"], entry["urgency"], clabel)
        st.session_state.history.append(entry)
        st.session_state.results.pop(gidx)
        st.rerun()

    st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)

    if ab:
        st.markdown('<div class="field-label">Audio</div>', unsafe_allow_html=True)
        st.markdown(audio_html(audio_b64(ab, am)), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if show_tr:
        t1, t2 = st.columns(2)
        with t1: st.markdown(f'<div class="field-label">Original ({lang})</div><div class="tx-box">{orig or "—"}</div>', unsafe_allow_html=True)
        with t2: st.markdown(f'<div class="field-label" style="color:#1d6a88;">Translation</div><div class="tr-box">{transl}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="field-label">Transcript</div><div class="tx-box">{orig or "—"}</div>', unsafe_allow_html=True)

    st.divider()

def render_section(key, items):
    if not items: return
    st.markdown(f'<div class="{SEC_CSS.get(key,"")}">', unsafe_allow_html=True)
    with st.expander(f"{SECTION_LABELS[key]}  ·  {len(items)} call{'s' if len(items)!=1 else ''}", expanded=False):
        for rank, r in enumerate(items, 1):
            real_idx = next(i for i, x in enumerate(st.session_state.results) if x is r)
            render_card(r, rank, real_idx)
    st.markdown('</div>', unsafe_allow_html=True)

# ── TOP BAR ───────────────────────────────────────────────────────────────────
tab = st.session_state.active_tab
st.markdown("""
<div class="topbar">
  <div>
    <div class="pab-logo">PAB Dashboard</div>
    <div class="pab-sub">Emergency Audio Triage System</div>
  </div>
</div>
""", unsafe_allow_html=True)

_g, _d, _h = st.columns([6.5, 1, 1])
with _d:
    if st.button("Dashboard", key="nb_d", use_container_width=True):
        st.session_state.active_tab = "dashboard"; st.rerun()
with _h:
    if st.button("History", key="nb_h", use_container_width=True):
        st.session_state.active_tab = "history"; st.rerun()

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
if tab == "dashboard":
    col_l, col_r = st.columns([1, 2.2], gap="large")

    with col_l:
        st.markdown('<div class="sec-label">Upload Audio</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader("audio", type=["mp3","m4a","wav","ogg","flac","mp4","webm"],
                                    accept_multiple_files=True, label_visibility="collapsed")
        if uploaded:
            st.caption(f"{len(uploaded)} file{'s' if len(uploaded)!=1 else ''} queued")

        go = st.button("Process All Files", use_container_width=True, type="primary", disabled=not uploaded)

        if st.session_state.results:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="sec-label">Queue Stats</div>', unsafe_allow_html=True)
            bk = bucket_sort(st.session_state.results)
            a, b = st.columns(2)
            with a: st.markdown(f'<div class="mbox"><div class="mval" style="color:#ff5c5c;">{len(bk["URGENT"])+len(bk["URGENT_EMPTY"])}</div><div class="mlbl">Urgent</div></div>', unsafe_allow_html=True)
            with b: st.markdown(f'<div class="mbox"><div class="mval" style="color:#f59e0b;">{len(bk["MEDIUM"])}</div><div class="mlbl">Medium</div></div>', unsafe_allow_html=True)
            c, d = st.columns(2)
            with c: st.markdown(f'<div class="mbox"><div class="mval" style="color:#22c55e;">{len(bk["LOW"])}</div><div class="mlbl">Low</div></div>', unsafe_allow_html=True)
            with d: st.markdown(f'<div class="mbox"><div class="mval" style="color:#4a5568;">{len(bk["MISCLICK"])}</div><div class="mlbl">Misclick</div></div>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑 Clear All", use_container_width=True):
                st.session_state.results = []; st.rerun()

    with col_r:
        st.markdown('<div class="sec-label">Triage Queue</div>', unsafe_allow_html=True)

        if go and uploaded:
            pb = st.progress(0); sp = st.empty(); new = []
            for i, f in enumerate(uploaded):
                sp.caption(f"⟳ Processing {f.name} ({i+1}/{len(uploaded)})…")
                try: new.append(process_audio(f.read(), f.name))
                except Exception as e: st.error(f"Failed: {f.name} — {e}")
                pb.progress((i+1)/len(uploaded))
            st.session_state.results.extend(new)
            pb.empty(); sp.empty(); st.rerun()

        if st.session_state.results:
            bk = bucket_sort(st.session_state.results)
            for sk in SECTION_ORDER:
                render_section(sk, bk.get(sk,[]))
        else:
            st.markdown('<div class="empty-state"><div style="font-size:2.5rem;">:(</div><div style="font-size:1rem;font-weight:600;color:#ffffff;margin-top:.8rem;">No active calls.</div><div style="font-size:.8rem;color:#ffffff;margin-top:.4rem;">Upload audio and hit Process.</div></div>', unsafe_allow_html=True)

# ── HISTORY ───────────────────────────────────────────────────────────────────
elif tab == "history":
    hist = st.session_state.history
    st.markdown('<div class="sec-label">Cleared Call History</div>', unsafe_allow_html=True)

    if not hist:
        st.markdown('<div class="empty-state"><div style="font-size:2.5rem;">📋</div><div style="font-size:1rem;font-weight:600;color:#ffffff;margin-top:.8rem;">No cleared calls yet.</div><div style="font-size:.8rem;color:#ffffff;margin-top:.4rem;">Clear calls from the Dashboard to see them here.</div></div>', unsafe_allow_html=True)
    else:
        urg_c = sum(1 for r in hist if r.get("urgency","") in ("URGENT","URGENT_EMPTY"))
        med_c = sum(1 for r in hist if r.get("urgency","") == "MEDIUM")
        low_c = sum(1 for r in hist if r.get("urgency","") == "LOW")
        mis_c = sum(1 for r in hist if r.get("urgency","") == "MISCLICK")
        st.markdown(f"""<div class="stat-row">
          <span class="stat-chip" style="color:#e2e8f0;border-color:#2a3448;background:#0d1117;">Total: {len(hist)}</span>
          <span class="stat-chip" style="color:#ff5c5c;border-color:#ff5c5c40;background:#ff5c5c10;">🔴 {urg_c} Urgent</span>
          <span class="stat-chip" style="color:#fbbf24;border-color:#f59e0b40;background:#f59e0b10;">🟡 {med_c} Medium</span>
          <span class="stat-chip" style="color:#4ade80;border-color:#22c55e40;background:#22c55e10;">🟢 {low_c} Low</span>
          <span class="stat-chip" style="color:#94a3b8;border-color:#4a556840;background:#4a556810;">⚫ {mis_c} Misclick</span>
        </div>""", unsafe_allow_html=True)

        for r in reversed(hist):
            urgency    = r.get("urgency","UNKNOWN")
            color      = URGENCY_COLORS.get(urgency,"#6366f1")
            disp_urg   = "URGENT" if urgency=="URGENT_EMPTY" else urgency
            status     = r.get("status","—")
            sc         = STATUS_COLORS.get(status,"#60a5fa")
            sev        = r.get("severity_score","—")
            topic      = r.get("topic","—")
            cleared    = r.get("cleared_as","—")
            cleared_at = r.get("cleared_at","")
            fname      = r.get("filename","—")
            lang       = r.get("language","English")
            orig       = r.get("original_transcript","")
            transl     = r.get("translated_transcript","")
            conf       = r.get("confidence","—")
            bullets    = r.get("summary_bullets",[])
            show_tr    = bool(transl and transl.strip().upper() not in ("N/A","NA","") and lang.lower() not in ("english","en"))

            urg_tag  = "🔴" if urgency in ("URGENT","URGENT_EMPTY") else ("🟡" if urgency=="MEDIUM" else ("🟢" if urgency=="LOW" else "⚫"))
            time_str = cleared_at[11:16] if len(cleared_at) >= 16 else cleared_at
            date_str = cleared_at[:10]   if len(cleared_at) >= 10 else ""
            hdr = f"{urg_tag} [{disp_urg}  ·  Sev {sev}]  {date_str} {time_str}  —  {topic}"

            with st.expander(hdr, expanded=False):
                h1, h2 = st.columns([3,2])
                with h1:
                    st.markdown(f'<div style="font-size:.72rem;color:#4a5568;font-family:monospace;">{fname} · {cleared_at}</div><div style="font-size:.8rem;color:#7ab8d4;margin-top:3px;">↳ {cleared}</div>', unsafe_allow_html=True)
                with h2:
                    st.markdown(f'<div style="display:flex;justify-content:flex-end;gap:6px;flex-wrap:wrap;align-items:center;"><span class="upill" style="background:{color}22;color:{color};border:1px solid {color}44;">{disp_urg}</span><span class="upill" style="background:{sc}15;color:{sc};border:1px solid {sc}40;">{status}</span><span style="font-size:.68rem;color:#4a5568;font-family:monospace;">Sev {sev}/100</span></div>', unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                for b in bullets:
                    st.markdown(f'<div style="font-size:.84rem;color:#c0cfe0;margin-bottom:2px;"><span style="color:{color};margin-right:6px;">•</span>{b}</div>', unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

                s1, s2, s3 = st.columns(3)
                with s1: st.markdown(f'<div class="field-label">Confidence</div><span style="font-family:monospace;font-size:.85rem;color:#c0cfe0;">{conf}%</span>', unsafe_allow_html=True)
                with s2: st.markdown(f'<div class="field-label">Severity</div><span style="font-family:monospace;font-size:.85rem;color:#c0cfe0;">{sev}/100</span>', unsafe_allow_html=True)
                with s3: st.markdown(f'<div class="field-label">Language</div><span style="font-size:.85rem;color:#c0cfe0;">{lang}</span>', unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

                if show_tr:
                    tc1, tc2 = st.columns(2)
                    with tc1: st.markdown(f'<div class="field-label">Original ({lang})</div><div class="tx-box">{orig or "—"}</div>', unsafe_allow_html=True)
                    with tc2: st.markdown(f'<div class="field-label" style="color:#1d6a88;">Translation</div><div class="tr-box">{transl}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="field-label">Transcript</div><div class="tx-box">{orig or "—"}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button("⬇ Download Log (CSV)", data=read_log_bytes(),
                           file_name=f"pab_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")
