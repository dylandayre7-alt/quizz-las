import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
import json
import pandas as pd
import docx
from datetime import datetime
import re

# ==============================================================================
# 1. Configuration et Design
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - IA Premium", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    .synth-box { padding: 25px; background-color: #1e1e1e; color: #ffffff; border-left: 8px solid #ff4b4b; border-radius: 10px; margin-bottom: 25px; }
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; }
    .concept-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #007bff; margin-bottom: 10px; color: #333; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & Mémoire
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    st.session_state['cahier_memoire'][matiere].append({
        "date": datetime.now().strftime("%d/%m/%Y"), "question": question,
        "choix_user": choix_user, "bonnes_rep": bonnes_rep, "explication": explication
    })

def extraire_vrai_json(texte):
    try:
        debut = texte.find('{')
        fin = texte.rfind('}') + 1
        texte_propre = texte[debut:fin].replace('\n', ' ')
        return json.loads(texte_propre)
    except Exception as e:
        raise Exception(f"L'IA a mal formaté sa réponse (Surcharge). Relance simplement l'analyse.")

def assembler_texte(champ):
    if isinstance(champ, list): return '<br><br>'.join([str(c) for c in champ])
    return str(champ)

def lire_fichiers(f_pdf, f_word, p_deb, p_fin):
    f_pdf.seek(0)
    doc = fitz.open(stream=f_pdf.read(), filetype="pdf")
    txt_pdf = "".join([f" PAGE {i+1} " + doc[i].get_text("text") for i in range(p_deb - 1, min(p_fin, len(doc)))])
    doc.close()
    txt_word = " ".join([p.text for p in docx.Document(f_word).paragraphs]) if f_word else "Aucune note."
    return txt_pdf, txt_word

# ==============================================================================
# 3. Moteur IA (VERROUILLÉ SUR GEMINI 2.5 FLASH)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1. Matière: {matiere} | Difficulté: {difficulte}/10 | Nombre QCM: {nombre_qcm} | Style: {style_question} | Notes: {notes_etudiant}

⚠️ RÈGLES CRITIQUES:
1. Pas de guillemets doubles (") dans le texte, utilise (').
2. Écris TOUT le JSON sur UNE SEULE LIGNE (pas de retours à la ligne).
3. Utilise <br> pour sauter des lignes dans le texte.
4. Varie le nombre de bonnes réponses aux QCM (de 1 à 5).

FORMAT JSON ATTENDU :
{{"fiche_synthese": ["### Titre<br>Texte..."], "concepts_cles": [{{"nom": "...", "role": "...", "objectif": "...", "avec_quoi": "...", "comment": "..."}}], "qcm": [{{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "reponses_correctes": ["A"], "explication": ["**A) VRAI** : ...<br>**B) FAUX** : ..."], "indice": "...", "mnemotechnique": "..."}}]}}
"""

def generer_cours(txt_pdf, txt_word, matiere, difficulte, nb_qcm, mode_exam, api_key):
    genai.configure(api_key=api_key)
    # LE MOTEUR 2.5 EST FORCÉ ICI
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    style = 'Type concours, très difficile.' if mode_exam else 'Apprentissage clair.'
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nb_qcm, notes_etudiant=txt_word, style_question=style)
    
    reponse = model.generate_content([prompt, "TEXTE A ANALYSER : " + txt_pdf], generation_config={'temperature': 0.3})
    return extraire_vrai_json(reponse.text)

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Config")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie", "Biostats", "Anatomie", "Pharmaco", "Droit"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Mode Examen")

# ==============================================================================
# 5. Interface Principale
# ==============================================================================
st.title("🎓 Prépa LAS 1 (Moteur 2.5)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF", type=['pdf'])
with c2: f_word = st.file_uploader("2. Fiches Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    p_deb, p_fin = st.slider("Pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Lancer", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner("Analyse en cours avec Gemini 2.5 Flash..."):
                try:
                    txt_pdf, txt_word = lire_fichiers(f_pdf, f_word, p_deb, p_fin)
                    st.session_state['data'] = generer_cours(txt_pdf, txt_word, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: 
                    st.error(f"❌ Erreur : {e}")

# ==============================================================================
# 6. Affichage des Résultats
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2, t3, t4 = st.tabs(["📖 Fiche", "🎯 Concepts", "✍️ QCM", "📓 Erreurs"])

    with t1: st.markdown(f"<div class='synth-box'>{assembler_texte(data.get('fiche_synthese', ''))}</div>", unsafe_allow_html=True)
    
    with t2:
        for c in data.get('concepts_cles', []):
            with st.expander(f"🧩 {c.get('nom', 'Concept')}"):
                st.markdown(f"<div class='concept-card'><strong>Rôle:</strong> {c.get('role')}<br><strong>Objectif:</strong> {c.get('objectif')}<br><strong>Comment:</strong> {c.get('comment')}</div>", unsafe_allow_html=True)

    with t3:
        liste_qcm = data.get('qcm', [])
        if not st.session_state.get('examen_soumis'):
            for i, q in enumerate(liste_qcm):
                st.markdown(f"**Q{i+1}** : {q.get('question')}")
                if f"choix_{i}" not in st.session_state: st.session_state[f"choix_{i}"] = []
                cochees = []
                for l, t in q.get('options', {}).items():
                    if st.checkbox(f"{l}. {t}", key=f"chk_{i}_{l}"): cochees.append(l)
                st.session_state[f"choix_{i}"] = cochees
                st.divider()
            if st.button("Valider ma copie", type="primary"): 
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            score = 0
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                juste = (mes_choix == bonnes)
                if juste: score += 1
                else: ajouter_erreur(matiere, q.get('question'), mes_choix, bonnes, assembler_texte(q.get('explication')))
                st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'>Q{i+1} : {'✅' if juste else '❌'} (Rép: {', '.join(bonnes)})</div>", unsafe_allow_html=True)
                with st.expander("Correction"): st.markdown(assembler_texte(q.get('explication')), unsafe_allow_html=True)
            st.metric("Note", f"{(score/max(1, len(liste_qcm)))*20:.1f}/20")
            if st.button("Recommencer"): st.session_state['examen_soumis'] = False; st.rerun()

    with t4:
        for m, errs in st.session_state.get('cahier_memoire', {}).items():
            with st.expander(f"{m} ({len(errs)})"):
                for e in reversed(errs):
                    st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Toi: {e['choix_user']} | Vrai: {e['bonnes_rep']}<br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
