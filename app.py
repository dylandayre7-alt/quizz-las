import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
import docx
from datetime import datetime
import re
import requests

# ==============================================================================
# 1. Configuration et Design Premium
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - Masterclass", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    
    .synth-box { padding: 30px; background-color: #1e1e1e; color: #ffffff; border-left: 8px solid #ff4b4b; border-radius: 15px; margin-bottom: 30px; line-height: 1.8; }
    .synth-box h3 { color: #e74c3c !important; font-weight: bold; font-size: 1.4em; margin-top: 20px; border-bottom: 1px solid #444; padding-bottom: 5px; } 
    .synth-box p, .synth-box li { color: #ffffff !important; font-size: 1.1em; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
    .concept-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #007bff; margin-bottom: 10px; color: #333; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur_session(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    if not any(err['question'] == question for err in st.session_state['cahier_memoire'][matiere]):
        st.session_state['cahier_memoire'][matiere].append({
            "date": datetime.now().strftime("%d/%m/%Y"), "question": question,
            "choix_user": choix_user, "bonnes_rep": bonnes_rep, "explication": explication
        })

def assembler_texte_html(champ):
    texte = '<br><br>'.join([str(c) for c in champ]) if isinstance(champ, list) else str(champ)
    texte = re.sub(r'###\s*(.*?)(<br>|$)', r'<h3>\1</h3>\2', texte)
    texte = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', texte)
    return texte

def extraire_texte_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    texte = "".join([f" PAGE {i+1} " + doc[i].get_text("text") for i in range(page_debut - 1, min(page_fin, len(doc)))])
    doc.close()
    return texte

def lire_word(buffer_fichier):
    doc = docx.Document(buffer_fichier)
    return " ".join([para.text for para in doc.paragraphs])

# ==============================================================================
# 3. Moteur IA (Optimisé pour ne plus couper la réponse)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1.
Matière : {matiere} | Difficulté : {difficulte}/10 | QCM : {nombre_qcm}

RÈGLES DE FORMATAGE (CRITIQUE) :
1. Réponds UNIQUEMENT avec un objet JSON valide.
2. Échappe proprement les guillemets internes ou utilise des guillemets simples (') dans le texte.
3. Utilise le HTML pour la mise en forme (<h3>, <strong>, <br>). Ne mets pas de Markdown.

MISSION :
1. COURS EXHAUSTIF MAIS OPTIMISÉ : Retranscris tous les mécanismes, classifications et définitions importantes. Sois très précis sur le fond, mais va à l'essentiel dans tes phrases pour que ta réponse ne soit pas coupée par manque de mémoire (privilégie les listes à puces et phrases courtes). Structure avec <h3> et mets les concepts vitaux en rouge (<span style='color:#ff4b4b'>...</span>).
2. CONCEPTS CLÉS : 5 à 10 fiches réflexes indispensables.
3. QCM : {nombre_qcm} questions type concours, réponses variables (1 à 5).
4. CORRECTION DÉTAILLÉE : Justifie CHAQUE lettre (A, B, C, D, E) individuellement.
5. AIDE & MÉMO : Un indice et une astuce de mémorisation par question.

FORMAT JSON STRICT :
{{
  "fiche_synthese": ["<h3>...</h3>", "Explication détaillée mais directe..."],
  "concepts_cles": [{{"nom": "...", "role": "...", "objectif": "...", "avec_quoi": "...", "comment": "..."}}],
  "qcm": [{{
    "question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
    "reponses_correctes": ["A", "D"], 
    "explication": [
      "<strong>A) VRAI</strong> : explication...",
      "<strong>B) FAUX</strong> : explication du piège..."
    ], 
    "indice": "...", "mnemotechnique": "..."
  }}]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    style = 'ANNALES' if est_mode_examen else 'APPRENTISSAGE'
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm, notes_etudiant=texte_word or 'Aucune', style_question=style)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt + "\nCOURS :\n" + texte_pdf}]}], 
        "generationConfig": {
            "temperature": 0.3, 
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    rep = requests.post(url, json=payload)
    if rep.status_code != 200: raise Exception(f"Erreur Google : {rep.text}")
    
    texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    
    # 🌟 EXTRACTION CHIRURGICALE : On isole uniquement ce qui est entre { et }
    debut = texte_ia.find('{')
    fin = texte_ia.rfind('}') + 1
    if debut != -1 and fin != 0:
        texte_ia = texte_ia[debut:fin]
    
    try:
        return json.loads(texte_ia, strict=False)
    except json.JSONDecodeError as e:
        raise Exception(f"Le cours généré était trop massif et a été coupé. Essaie de sélectionner moins de pages d'un coup (ex: 2 ou 3 pages) ! Détail: {e}")

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

# ==============================================================================
# 5. Application
# ==============================================================================
st.title("🎓 Simulateur LAS 1 Masterclass")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    # Conseil d'utilisation affiché
    st.info("💡 Si ton cours est très dense, analyse 3 à 5 pages maximum par session pour garantir une fiche ultra-détaillée.")
    p_deb, p_fin = st.slider("Pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Générer la session", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner("Rédaction du cours complet en cours (avec Gemini 2.5)..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: st.error(f"❌ {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2, t3, t4 = st.tabs(["📖 Fiche Magistrale", "🎯 Concepts Clés", "✍️ QCM", "📓 Cahier d'Erreurs"])

    with t1: st.markdown(f"<div class='synth-box'>{assembler_texte_html(data.get('fiche_synthese', ''))}</div>", unsafe_allow_html=True)

    with t2:
        for c in data.get('concepts_cles', []):
            with st.expander(f"🧩 {c.get('nom', 'Concept')}"):
                st.markdown(f"<div class='concept-card'><strong>Rôle:</strong> {c.get('role')}<br><strong>Objectif:</strong> {c.get('objectif')}<br><strong>Comment:</strong> {c.get('comment')}</div>", unsafe_allow_html=True)

    with t3:
        liste_qcm = data.get('qcm', [])
        if not st.session_state.get('examen_soumis'):
            for i, q in enumerate(liste_qcm):
                st.markdown(f"**Question {i+1}** : {q.get('question')}")
                if f"choix_{i}" not in st.session_state: st.session_state[f"choix_{i}"] = []
                cochees = []
                for l, t in q.get('options', {}).items():
                    if st.checkbox(f"{l}. {t}", key=f"chk_{i}_{l}"): cochees.append(l)
                st.session_state[f"choix_{i}"] = cochees
                
                if not mode_examen:
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        with st.expander("💡 Aide (Indice)"): st.info(q.get('indice', 'Pas d indice.'))
                    with col_h2:
                        with st.expander("🧠 Mémorisation Active"): st.warning(f"**Point d'ancrage :** {q.get('mnemotechnique', 'Rappelle-toi du mécanisme principal.')}")
                    
                    if st.button(f"Vérifier Q{i+1}", key=f"v_{i}"):
                        bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                        mes_choix = sorted(cochees)
                        explication_propre = assembler_texte_html(q.get('explication', ''))
                        
                        if mes_choix == bonnes and len(bonnes) > 0: st.success("Vrai !")
                        else:
                            st.error(f"Faux ! Rep: {', '.join(bonnes)}")
                            ajouter_erreur_session(matiere, q.get('question', ''), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), explication_propre)
                        
                        st.success("**Correction détaillée :**")
                        st.markdown(explication_propre, unsafe_allow_html=True)

                st.divider()
            
            texte_btn = "🏁 Valider ma copie" if mode_examen else "✅ Valider et enregistrer mes erreurs"
            if st.button(texte_btn, type="primary", use_container_width=True): 
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            score = 0
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                juste = (mes_choix == bonnes and len(bonnes) > 0)
                if juste: score += 1
                else: ajouter_erreur_session(matiere, q.get('question'), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), assembler_texte_html(q.get('explication')))
                st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'>Q{i+1} : {'✅' if juste else '❌'} (Rép: {', '.join(bonnes)})</div>", unsafe_allow_html=True)
                with st.expander("Correction détaillée"): st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.metric("Note finale", f"{(score/max(1, len(liste_qcm)))*20:.1f} / 20")
            if st.button("Nouveau test"): st.session_state['examen_soumis'] = False; st.rerun()

    with t4:
        for mat, errs in st.session_state.get('cahier_memoire', {}).items():
            with st.expander(f"{mat} ({len(errs)} erreurs)"):
                for e in reversed(errs):
                    st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Toi : {e['choix_user']} | Vrai : {e['bonnes_rep']}<br><br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
