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
# 1. Configuration et Design Premium de l'Application
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - Évaluation Illimitée", page_icon="🎓", layout="wide")

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
# 2. Utilitaires Système & Traitement des Fichiers
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
# 3. Analyseur Textuel par Expressions Régulières (Regex) - Anti-Crash
# ==============================================================================
def extraire_questions_texte(texte_ia):
    blocs = re.findall(r'===QUESTION_START===(.*?)===QUESTION_END===', texte_ia, re.DOTALL)
    questions_chargees = []
    
    for b in blocs:
        try:
            type_q_match = re.search(r'TYPE:\s*(QCU|OUVERTE)', b, re.IGNORECASE)
            type_q = type_q_match.group(1).upper().strip() if type_q_match else "QCU"
            
            enonce_match = re.search(r'ENONCE:\s*(.*?)\s*(?=A:|REPONSE:|EXPLICATION:)', b, re.DOTALL | re.IGNORECASE)
            enonce = enonce_match.group(1).strip() if enonce_match else "Énoncé non récupéré"
            
            explication_match = re.search(r'EXPLICATION:\s*(.*?)\s*(?=INDICE:|MNEMO:|$)', b, re.DOTALL | re.IGNORECASE)
            explication = explication_match.group(1).strip() if explication_match else ""
            
            indice_match = re.search(r'INDICE:\s*(.*?)\s*(?=MNEMO:|$)', b, re.DOTALL | re.IGNORECASE)
            indice = indice_match.group(1).strip() if indice_match else ""
            
            mnemo_match = re.search(r'MNEMO:\s*(.*?)\s*$', b, re.DOTALL | re.IGNORECASE)
            mnemo = mnemo_match.group(1).strip() if mnemo_match else ""
            
            if type_q == "QCU":
                opt_A = re.search(r'\bA:\s*(.*?)\s*(?=\bB:)', b, re.DOTALL | re.IGNORECASE)
                opt_B = re.search(r'\bB:\s*(.*?)\s*(?=\bC:)', b, re.DOTALL | re.IGNORECASE)
                opt_C = re.search(r'\bC:\s*(.*?)\s*(?=\bD:)', b, re.DOTALL | re.IGNORECASE)
                opt_D = re.search(r'\bD:\s*(.*?)\s*(?=\bE:)', b, re.DOTALL | re.IGNORECASE)
                opt_E = re.search(r'\bE:\s*(.*?)\s*(?=\bREPONSE:)', b, re.DOTALL | re.IGNORECASE)
                rep_match = re.search(r'REPONSE:\s*([A-E])', b, re.IGNORECASE)
                
                options = {
                    "A": opt_A.group(1).strip() if opt_A else "Option A",
                    "B": opt_B.group(1).strip() if opt_B else "Option B",
                    "C": opt_C.group(1).strip() if opt_C else "Option C",
                    "D": opt_D.group(1).strip() if opt_D else "Option D",
                    "E": opt_E.group(1).strip() if opt_E else "Option E"
                }
                reponse_correcte = rep_match.group(1).upper().strip() if rep_match else "A"
                
                questions_chargees.append({
                    "type": "QCU", "question": enonce, "options": options,
                    "reponse_correcte": reponse_correcte, "explication": explication,
                    "indice": indice, "mnemotechnique": mnemo
                })
            else:
                rep_match = re.search(r'REPONSE:\s*(.*?)\s*(?=MOTS_CLES:|EXPLICATION:)', b, re.DOTALL | re.IGNORECASE)
                rep_attendue = rep_match.group(1).strip() if rep_match else ""
                
                mots_match = re.search(r'MOTS_CLES:\s*(.*?)\s*(?=EXPLICATION:)', b, re.DOTALL | re.IGNORECASE)
                mots_cles = [m.strip() for m in mots_match.group(1).split(',')] if mots_match else []
                
                questions_chargees.append({
                    "type": "OUVERTE", "question": enonce, "reponse_attendue": rep_attendue,
                    "mots_cles": mots_cles, "explication": explication,
                    "indice": indice, "mnemotechnique": mnemo
                })
        except:
            continue
    return {"questions": questions_chargees}

# ==============================================================================
# 4. Moteur IA Séquentiel (Haute Capacité)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1. Évalue l'étudiant sur le texte fourni.
Matière : {matiere} | Difficulté : {difficulte}/10 

Génère EXACTEMENT {nb_qcu} questions de type "QCU" et EXACTEMENT {nb_ouverte} questions de type "OUVERTE".

RÈGLE ABSOLUE : N'utilise JAMAIS de format JSON. Tu dois répondre uniquement en utilisant l'architecture textuelle suivante :

===QUESTION_START===
TYPE: QCU
ENONCE: [Insère l'énoncé de la question ici]
A: [Option A]
B: [Option B]
C: [Option C]
D: [Option D]
E: [Option E]
REPONSE: [Met uniquement la lettre de la bonne réponse, ex: A]
EXPLICATION: <strong>A) VRAI</strong> : ... <br><strong>B) FAUX</strong> : ...
INDICE: [Indice]
MNEMO: [Astuce mémo]
===QUESTION_END===

===QUESTION_START===
TYPE: OUVERTE
ENONCE: [Insère la question ouverte de réflexion scientifique]
REPONSE: [Insère le modèle idéal de réponse attendue]
MOTS_CLES: [mot1, mot2, mot3, mot4]
EXPLICATION: [Explication physiologique ou méthodologique]
INDICE: [Piste]
MNEMO: [Moyen mnémotechnique]
===QUESTION_END===
"""

def generer_donnees_illimitees(txt_complet, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    # Séparation automatique par bloc de pages pour avaler n'importe quel volume
    lots_pages = [p for p in txt_complet.split(' PAGE ') if p.strip()]
    
    TAILLE_LOT = 5
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
    
    for idx, chunk in enumerate(chunks_texte):
        if len(all_questions) >= nombre_qcm:
            break
            
        barre_progression.progress(idx / len(chunks_texte))
        
        prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt + "\nNOTES WORD EXTRA:\n" + (texte_word or "") + "\n\nEXTRAIT DU PDF DU COURS :\n" + chunk}]}],
            "generationConfig": {"temperature": 0.2}
        }
        
        try:
            rep = requests.post(url, json=payload)
            if rep.status_code == 200:
                texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
                res = extraire_questions_texte(texte_ia)
                all_questions.extend(res.get('questions', []))
            elif rep.status_code == 429:
                time.sleep(5) # Auto-pause si surcharge de requêtes
        except:
            pass
            
        time.sleep(0.5)
        
    barre_progression.empty()
    return {"questions": all_questions[:nombre_qcm]}

# ==============================================================================
# 5. Interface Graphique Streamlit
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Niveau de pièges :", 1, 10, 8)
    nombre_qcm = st.number_input("Volume total de questions désiré :", 1, 40, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Concours (Masquer indices)")

st.title("🎓 Simulateur d'Évaluation Intensive Haute Capacité")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. Support de cours (PDF volumineux accepté)", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes personnelles (Word)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Sélectionner la plage de pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Lancer l'Évaluation Globale (Sans Limite)", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Clé API absente.")
        else:
            with st.spinner("Digestion intégrale du document et ciblage des pièges en cours..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees_illimitees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: 
                    st.error(f"Incident technique de traitement : {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Grille d'Entraînement", "📓 Mon Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)
        
        if not liste_questions:
            st.warning("Aucune question n'a pu être extraite. Relance la génération.")
            
        for i, q in enumerate(liste_questions):
            type_q = q.get('type', 'QCU')
            question_propre = nettoyer_question(q.get('question', ''))
            
            st.markdown(f"**Question {i+1}** 🔹 *{type_q}* : {question_propre}")
            
            if type_q == "QCU":
                opts = q.get('options', {})
                choix = st.radio(
                    "Sélectionner l'affirmation correcte :", options=list(opts.keys()), 
                    format_func=lambda x: f"{x}. {nettoyer_question(opts[x])}",
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
            st.info("Aucune erreur enregistrée.")
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
