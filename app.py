import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
import docx
from datetime import datetime
import re
import requests
import math
import time

# ==============================================================================
# 1. Configuration et Design Premium
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - Évaluation Ultime", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .warning-box { background-color: #856404; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #ffeeba; border: 1px solid #ffeeba;}
    
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; line-height: 1.6; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires Système
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur_session(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    if not any(err['question'] == question for err in st.session_state['cahier_memoire'][matiere]):
        st.session_state['cahier_memoire'][matiere].append({
            "date": datetime.now().strftime("%d/%m/%Y"),
            "question": question,
            "choix_user": choix_user,
            "bonnes_rep": bonnes_rep,
            "explication": explication
        })

def assembler_texte_html(champ):
    texte = '<br><br>'.join([str(c) for c in champ]) if isinstance(champ, list) else str(champ)
    texte = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', texte)
    return texte

def nettoyer_question(texte):
    t = str(texte)
    t = re.sub(r'</?h[1-6]>', '', t) 
    t = t.replace('<br>', ' ')
    t = t.replace('<strong>', '**').replace('</strong>', '**')
    return t.strip()

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
# 3. Moteur IA (Hybride : Découpage rapide + JSON Natif Garanti)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1. Ton unique but est d'évaluer l'étudiant de manière rigoureuse sur le cours fourni.
Matière : {matiere} | Difficulté : {difficulte}/10 

Tu dois générer EXACTEMENT {nb_qcu} questions "QCU" et EXACTEMENT {nb_ouverte} questions "OUVERTE".

RÈGLES INFORMATIQUES CRITIQUES :
1. Réponds UNIQUEMENT via l'objet JSON valide demandé.
2. N'utilise JAMAIS de guillemets doubles (") dans tes textes. Remplace-les par des apostrophes (').
3. Aucun HTML dans les champs "question" et "options".

FORMAT JSON REQUIS :
{{
  "questions": [
    {{
      "type": "QCU",
      "question": "Énoncé de la question",
      "options": {{"A": "Proposition A", "B": "Proposition B", "C": "Proposition C", "D": "Proposition D", "E": "Proposition E"}},
      "reponse_correcte": "A", 
      "explication": ["<strong>A) VRAI</strong> : explication...", "<strong>B) FAUX</strong> : description du piège..."], 
      "indice": "Indice...", "mnemotechnique": "Moyen mémo..."
    }},
    {{
      "type": "OUVERTE",
      "question": "Énoncé textuel de la question ouverte",
      "reponse_attendue": "Grille de réponse idéale",
      "mots_cles": ["mot1", "mot2", "mot3"],
      "explication": ["Rappel fondamental du cours..."],
      "indice": "Piste...", "mnemotechnique": "Astuce..."
    }}
  ]
}}
"""

def generer_donnees_hybrides(txt_complet, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    lots_pages = [p for p in txt_complet.split(' PAGE ') if p.strip()]
    
    TAILLE_LOT = 15 
    chunks_texte = []
    for i in range(0, len(lots_pages), TAILLE_LOT):
        paquet = lots_pages[i:i+TAILLE_LOT]
        chunks_texte.append(" ".join(paquet))
    
    if not chunks_texte:
        chunks_texte = [txt_complet]
        
    all_questions = []
    questions_par_chunk = max(1, math.ceil(nombre_qcm / len(chunks_texte)))
    
    nb_qcu = max(1, round(questions_par_chunk * 0.8))
    nb_ouverte = max(1, questions_par_chunk - nb_qcu)
    
    barre_progression = st.progress(0.0)
    dernier_bug = "Aucune erreur détectée."
    
    # NETTOYAGE CRITIQUE DE LA CLÉ API ICI
    api_key_propre = api_key.strip()
    
    for idx, chunk in enumerate(chunks_texte):
        if len(all_questions) >= nombre_qcm:
            break
            
        barre_progression.progress(idx / len(chunks_texte))
        
        prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte)
        url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key_propre}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt + "\\nNOTES WORD EXTRA:\\n" + (texte_word or "") + "\\n\\nEXTRAIT DU COURS :\\n" + chunk}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json" 
            }
        }
        
        try:
            rep = requests.post(url, json=payload)
            if rep.status_code == 200:
                texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                
                texte_ia = texte_ia.replace("```json", "").replace("```", "").strip()
                
                donnees_chunk = json.loads(texte_ia, strict=False)
                all_questions.extend(donnees_chunk.get('questions', []))
            
            elif rep.status_code == 429:
                time.sleep(4)
            else:
                raise Exception(f"Refus API {rep.status_code} : {rep.text}")
                
        except Exception as e:
            dernier_bug = str(e)
            st.toast(f"Alerte sur ce bloc de pages. Détail de l'erreur : {dernier_bug[:80]}...", icon="⚠️")
            pass
            
    barre_progression.empty()
    
    if not all_questions:
        raise Exception(f"Échec total de la génération. Erreur interne remontée : {dernier_bug}")
        
    return {"questions": all_questions[:nombre_qcm]}

# ==============================================================================
# 4. Interface Graphique Streamlit
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Niveau de pièges :", 1, 10, 8)
    nombre_qcm = st.number_input("Volume total de questions désiré :", 1, 50, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Concours (Masquer indices)")

st.title("🎓 Simulateur d'Évaluation Hybride (Ultra-Stable)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. Support de cours (PDF volumineux accepté)", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes personnelles (Word)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Sélectionner la plage de pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Lancer l'Évaluation", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Clé API absente.")
        else:
            with st.spinner("Analyse du document et construction des QCU / Rédaction en cours..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    
                    # VERIFICATION DU PDF VIDE / SCAN :
                    if len(txt.strip()) < 50 and len(txt_w.strip()) < 50:
                        st.error("❌ Ton PDF semble vide ou est composé uniquement d'images/scans. L'application ne peut pas lire le texte dessus. Saisis tes notes dans un fichier Word et charge-le dans l'étape 2 !")
                    else:
                        st.session_state['data'] = generer_donnees_hybrides(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                        st.session_state['examen_soumis'] = False
                        st.rerun()
                except Exception as e: 
                    st.error(f"Incident technique : {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Grille d'Entraînement", "📓 Mon Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)
            
        for i, q in enumerate(liste_questions):
            type_q = q.get('type', 'QCU')
            question_propre = nettoyer_question(q.get('question', ''))
            
            st.markdown(f"**Question {i+1}** 🔹 *{type_q}* : {question_propre}")
            
            if type_q == "QCU":
                opts = q.get('options', {})
                choix = st.radio(
                    "Sélectionner l'affirmation correcte :", options=list(opts.keys()), 
                    format_func=lambda x: f"{x}. {nettoyer_question(opts.get(x, ''))}",
                    index=None, key=f"widget_qcu_{i}", disabled=is_disabled
                )
            elif type_q == "OUVERTE":
                reponse_user = st.text_area("✍️ Saisis ta réponse rédigée :", key=f"widget_ouv_{i}", height=120, disabled=is_disabled)
            
            if not is_disabled and not mode_examen:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    with st.expander("💡 Indice de réflexion"): st.info(nettoyer_question(q.get('indice', 'Aucun indice.')))
                with col_h2:
                    with st.expander("🧠 Point d'ancrage mnémotechnique"): st.warning(f"{nettoyer_question(q.get('mnemotechnique', 'Aucune astuce.'))}")
            
            if is_disabled:
                if type_q == "QCU":
                    bonne_rep = q.get('reponse_correcte', '')
                    choix_propre = choix if choix else "Aucune réponse"
                    juste = (choix == bonne_rep and choix is not None)
                    
                    if juste:
                        st.markdown(f"<div class='correct-box'>✅ <b>Proposition Exacte !</b> La réponse attendue était {bonne_rep}.</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='error-box'>❌ <b>Erreur !</b> Tu as coché la lettre {choix_propre}. L'affirmation vraie était la {bonne_rep}.</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, str(choix_propre), bonne_rep, assembler_texte_html(q.get('explication')))
                    
                    with st.expander("Analyse détaillée"): st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
                
                elif type_q == "OUVERTE":
                    mots_cles = q.get('mots_cles', [])
                    reponse_str = str(reponse_user) if reponse_user else ""
                    mots_trouves = [m for m in mots_cles if str(m).lower() in reponse_str.lower()]
                    ratio = len(mots_trouves) / max(1, len(mots_cles))
                    
                    if ratio >= 0.5:
                        st.markdown(f"<div class='correct-box'>✅ <b>Validation réussie !</b> ({len(mots_trouves)}/{len(mots_cles)} mots-clés présents).</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='warning-box'>⚠️ <b>Incomplet :</b> Restitution trop imprécise ({len(mots_trouves)}/{len(mots_cles)} mots-clés présents).</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, reponse_str[:60]+"...", ", ".join(mots_cles), assembler_texte_html(q.get('explication')))
                    
                    st.markdown(f"<b>Mots-clés requis :</b> <code>{', '.join(mots_cles)}</code>", unsafe_allow_html=True)
                    with st.expander("Grille analytique de correction"): 
                        st.success(f"**Modèle idéal :** {nettoyer_question(q.get('reponse_attendue', ''))}")
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()
        
        if not st.session_state['examen_soumis']:
            if st.button("🏁 Clôturer la Session et Corriger ma Copie", type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            if st.button("🔄 Initialiser une Nouvelle Évaluation Active", use_container_width=True):
                st.session_state['examen_soumis'] = False
                st.rerun()

    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: 
            st.info("Aucune erreur enregistrée pour le moment.")
        else:
            for mat, errs in mem.items():
                with st.expander(f"Discipline : {mat} ({len(errs)} fautes stockées)", expanded=True):
                    for e in reversed(errs):
                        st.markdown(f"""
                        <div class='erreur-log'>
                            <strong>Question :</strong> {e['question']}<br>
                            <span style='color:#ff4b4b'><b>Ta réponse :</b> {e['choix_user']}</span> | 
                            <span style='color:#28a745'><b>Donnée attendue :</b> {e['bonnes_rep']}</span><br><br>
                            <strong>Justification :</strong><br>{e['explication']}
                        </div>
                        """, unsafe_allow_html=True)
