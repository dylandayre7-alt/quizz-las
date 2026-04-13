import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
import docx
from datetime import datetime
import re
import requests

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
    .synth-box h1, .synth-box h2, .synth-box h3, .synth-box h4, .synth-box p, .synth-box li { color: #ffffff !important; }
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
    .erreur-log strong { color: #ffffff; }
    .concept-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #007bff; margin-bottom: 10px; color: #333; }
    .concept-card strong { color: #007bff; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & Mémoire
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur_session(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    for err in st.session_state['cahier_memoire'][matiere]:
        if err['question'] == question: return
    st.session_state['cahier_memoire'][matiere].append({
        "date": datetime.now().strftime("%d/%m/%Y"), "question": question,
        "choix_user": choix_user, "bonnes_rep": bonnes_rep, "explication": explication
    })

def nettoyer_json(texte):
    t = texte.strip()
    t = re.sub(r'^```[a-zA-Z]*\n', '', t)
    t = re.sub(r'^```', '', t)
    t = re.sub(r'\n```$', '', t)
    t = re.sub(r'```$', '', t)
    t = t.replace('\n', ' ') 
    return t.strip()

def assembler_texte(champ):
    if isinstance(champ, list): 
        return '<br><br>'.join([str(c) for c in champ])
    return str(champ)

def extraire_texte_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    texte_complet = ""
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        texte_complet += f" PAGE {i+1} " + doc[i].get_text("text")
    doc.close()
    return texte_complet

def lire_word(buffer_fichier):
    doc = docx.Document(buffer_fichier)
    return " ".join([para.text for para in doc.paragraphs])

# ==============================================================================
# 3. Moteur IA (Le Vieux GEMINI-PRO incassable)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1. 
Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre total de QCM : {nombre_qcm}
STYLE : {style_question} | NOTES DE L'ÉTUDIANT : "{notes_etudiant}"

⚠️ RÈGLE DE SYNTAXE ABSOLUE : 
1. N'utilise JAMAIS de guillemets doubles (") dans tes textes. Utilise des guillemets simples ('). 
2. INTERDICTION de faire des retours à la ligne (Touche Entrée). Écris tout ton JSON sur une seule ligne continue.
3. Pour sauter une ligne dans le texte, utilise la balise <br>.

MISSION :
1. SYNTHÈSE (DÉTAILLÉE) : Fais un résumé pédagogique complet avec titres (###).
2. CONCEPTS CLÉS : Top 10 des concepts essentiels pour l'examen.
3. QCM : Génère EXACTEMENT {nombre_qcm} questions. Varie le nombre de bonnes réponses (de 1 à 5).
4. CORRECTION : Explique chaque lettre (A à E) avec VRAI ou FAUX en gras.

FORMAT JSON STRICT (SUR UNE SEULE LIGNE) :
{{"fiche_synthese": ["### Titre<br>Paragraphe..."], "concepts_cles": [{{"nom": "...", "role": "...", "objectif": "...", "avec_quoi": "...", "comment": "..."}}], "qcm": [{{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "reponses_correctes": ["A"], "explication": ["**A) VRAI** : ...<br>**B) FAUX** : ..."], "indice": "...", "mnemotechnique": "..."}}]}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    notes = texte_word if texte_word else 'Aucune note.'
    style = 'Style ANNALES (Piégeux, prop E).' if est_mode_examen else 'Style APPRENTISSAGE.'
    prompt_final = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm, notes_etudiant=notes, style_question=style)
    
    # 🌟 L'URL ULTIME QUI MARCHE PARTOUT : gemini-pro
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}"
    
    # On retire le "responseMimeType" car l'ancienne API v1beta de gemini-pro ne le supporte pas toujours !
    payload = {
        "contents": [{"parts": [{"text": prompt_final + " TEXTE : " + texte_pdf}]}],
        "generationConfig": {"temperature": 0.3}
    }
    
    reponse = requests.post(url, json=payload)
    
    if reponse.status_code != 200:
        raise Exception(f"Code {reponse.status_code} provenant de Google : {reponse.text}")
        
    res = reponse.json()
    texte_ia = res['candidates'][0]['content']['parts'][0]['text']
    return json.loads(nettoyer_json(texte_ia), strict=False)

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    st.divider()
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Mode Examen")

# ==============================================================================
# 5. Application Principale
# ==============================================================================
st.title("🎓 Simulateur LAS 1")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Tes fiches (Word) - Optionnel", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    p_deb, p_fin = st.slider("Pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Lancer la génération", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner("Analyse avec le moteur universel Gemini-Pro..."):
                try:
                    t_pdf = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    t_word = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees(t_pdf, t_word, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: 
                    st.error(f"Erreur Technique : {e}")

# ==============================================================================
# 6. Affichage
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2, t3, t4, t5 = st.tabs(["📖 Fiche", "🎯 Concepts", "✍️ QCM", "🗂️ Anki", "📓 Erreurs"])

    with t1: 
        st.markdown(f"<div class='synth-box'>{assembler_texte(data.get('fiche_synthese', ''))}</div>", unsafe_allow_html=True)

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
                else: ajouter_erreur_session(matiere, q.get('question'), mes_choix, bonnes, assembler_texte(q.get('explication')))
                st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'>Q{i+1} : {'✅' if juste else '❌'}</div>", unsafe_allow_html=True)
                st.write(f"Réponse: {', '.join(bonnes)}")
                with st.expander("Correction"): st.markdown(assembler_texte(q.get('explication')), unsafe_allow_html=True)
            st.metric("Note", f"{(score/len(liste_qcm))*20:.1f}/20")

    with t5:
        mem = st.session_state.get('cahier_memoire', {})
        for m, errs in mem.items():
            with st.expander(f"{m} ({len(errs)})"):
                for e in reversed(errs):
                    st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Ton choix: {e['choix_user']} | Rep: {e['bonnes_rep']}<br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
