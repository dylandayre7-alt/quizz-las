import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
import docx
from datetime import datetime
import re
import requests

# ==============================================================================
# 1. Configuration et Design Premium de l'Application
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - Évaluation Premium", page_icon="🎓", layout="wide")

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

def extraire_et_charger_json(texte_ia):
    debut = texte_ia.find('{')
    fin = texte_ia.rfind('}') + 1
    if debut == -1 or fin == 0:
        raise Exception("L'IA n'a pas renvoyé une structure de données exploitable. Relance l'analyse.")
    return json.loads(texte_ia[debut:fin].strip(), strict=False)

# ==============================================================================
# 3. Moteur IA (Format de Distribution Strict QCU / Ouvertes)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1. Ton unique objectif est d'évaluer l'étudiant de manière rigoureuse sur le cours fourni.
Matière : {matiere} | Difficulté : {difficulte}/10 

Tu dois générer IMPÉRATIVEMENT un total exact de {total_questions} questions réparties ainsi :
- EXACTEMENT {nb_qcu} questions de type "QCU"
- EXACTEMENT {nb_ouverte} questions de type "OUVERTE"

RÈGLES DE CONDUITE INFORMATIQUES :
1. Réponds STRICTEMENT avec l'objet JSON demandé. Aucune phrase explicative en dehors du JSON.
2. Interdiction d'utiliser des guillemets doubles (") dans tes textes de questions ou d'options. Utilise uniquement des apostrophes simples (').
3. N'injecte aucune balise HTML dans les champs "question" et "options".
4. Dans le champ "explication", utilise exclusivement du HTML (<strong>, <br>) pour séparer la correction de chaque proposition.

PROPRIÉTÉS DES QUESTIONS :
- QCU : 5 choix uniques (A à E), une seule et unique lettre correcte.
- OUVERTE : Question de réflexion nécessitant une rédaction complète, réponse attendue exhaustive et liste de 3 à 5 mots-clés d'évaluation.

FORMAT JSON REQUIS :
{{
  "questions": [
    {{
      "type": "QCU",
      "question": "Énoncé textuel fluide",
      "options": {{"A": "Proposition A", "B": "Proposition B", "C": "Proposition C", "D": "Proposition D", "E": "Proposition E"}},
      "reponse_correcte": "A", 
      "explication": ["<strong>A) VRAI</strong> : explication...", "<strong>B) FAUX</strong> : description du piège..."], 
      "indice": "Indice...", "mnemotechnique": "Moyen mémo..."
    }},
    {{
      "type": "OUVERTE",
      "question": "Énoncé textuel de la question ouverte",
      "reponse_attendue": "Grille de réponse idéale pour obtenir les points",
      "mots_cles": ["mot1", "mot2", "mot3"],
      "explication": ["Rappel fondamental du cours..."],
      "indice": "Piste...", "mnemotechnique": "Astuce..."
    }}
  ]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    # Calcul rigoureux du ratio 80% QCU et 20% Ouvertes
    nb_qcu = max(1, round(nombre_qcm * 0.8))
    nb_ouverte = max(1, nombre_qcm - nb_qcu)
    total_reels = nb_qcu + nb_ouverte
    
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte, total_questions=total_reels)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt + "\nCOURS DU CONCOURS À TRAITER :\n" + texte_pdf}]}], 
        "generationConfig": {
            "temperature": 0.2, 
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    rep = requests.post(url, json=payload)
    if rep.status_code != 200: raise Exception(f"Erreur d'accès aux serveurs de calcul : {rep.text}")
    
    return extraire_et_charger_json(rep.json()['candidates'][0]['content']['parts'][0]['text'])

# ==============================================================================
# 4. Interface Menu Configuration
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Niveau de pièges :", 1, 10, 8)
    nombre_qcm = st.number_input("Volume total de questions désiré :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Concours (Masquer indices)")

# ==============================================================================
# 5. Interface de Chargement Documentaire
# ==============================================================================
st.title("🎓 Simulateur d'Évaluation Intensive LAS 1")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. Charger le support de cours (PDF)", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes personnelles complémentaires (Word)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Sélectionner l'intervalle de pages à tester :", 1, p_tot, (1, min(10, p_tot)))
    
    if st.button("🚀 Initialiser la Session d'Évaluation", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Action impossible : Clé API absente de la configuration.")
        else:
            with st.spinner("Analyse sémantique et génération des questions en cours..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: 
                    st.error(f"Incident technique de traitement : {e}")

# ==============================================================================
# 6. Module d'Affichage Dynamique de l'Entraînement
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Grille d'Entraînement", "📓 Mon Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)
        
        # Affichage statique et immuable des composants d'évaluation
        for i, q in enumerate(liste_questions):
            type_q = q.get('type', 'QCU')
            question_propre = nettoyer_question(q.get('question', ''))
            
            st.markdown(f"**Question {i+1}** 🔹 *Format {type_q}* : {question_propre}")
            
            if type_q == "QCU":
                opts = q.get('options', {})
                choix = st.radio(
                    "Sélectionner l'affirmation correcte :", 
                    options=list(opts.keys()), 
                    format_func=lambda x: f"{x}. {nettoyer_question(opts[x])}",
                    index=None,
                    key=f"widget_qcu_{i}",
                    disabled=is_disabled
                )
            
            elif type_q == "OUVERTE":
                reponse_user = st.text_area("✍️ Rédiger votre démonstration doctrinale ou physiologique :", key=f"widget_ouv_{i}", height=120, disabled=is_disabled)
            
            # Affichage des outils d'aide durant la phase de recherche uniquement
            if not is_disabled and not mode_examen:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    with st.expander("💡 Obtenir un indice de contextualisation"): 
                        st.info(nettoyer_question(q.get('indice', 'Aucun indice fourni.')))
                with col_h2:
                    with st.expander("🧠 Point d'ancrage mnémotechnique"): 
                        st.warning(nettoyer_question(q.get('mnemotechnique', 'Aucune astuce.')))
            
            # Injection immédiate de la correction sous le widget correspondant après soumission
            if is_disabled:
                if type_q == "QCU":
                    bonne_rep = q.get('reponse_correcte', '')
                    juste = (choix == bonne_rep and choix is not None)
                    
                    if juste:
                        st.markdown(f"<div class='correct-box'>✅ <b>Proposition Exacte !</b> La réponse attendue était bien la lettre {bonne_rep}.</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='error-box'>❌ <b>Discordance Détectée !</b> Vous avez coché la lettre {choix if choix else 'Blanc'}. L'affirmation vraie était la {bonne_rep}.</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, str(choix), bonne_rep, assembler_texte_html(q.get('explication')))
                    
                    with st.expander("Consulter le rapport d'analyse détaillé"): 
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
                
                elif type_q == "OUVERTE":
                    mots_cles = q.get('mots_cles', [])
                    if not isinstance(mots_cles, list): mots_cles = [mots_cles] if mots_cles else []
                    
                    reponse_str = str(reponse_user) if reponse_user else ""
                    mots_trouves = [m for m in mots_cles if str(m).lower() in reponse_str.lower()]
                    ratio = len(mots_trouves) / max(1, len(mots_cles))
                    
                    if ratio >= 0.5:
                        st.markdown(f"<div class='correct-box'>✅ <b>Validation Sémantique Réussie !</b> ({len(mots_trouves)}/{len(mots_cles)} mots-clés identifiés dans votre production).</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='warning-box'>⚠️ <b>Axe d'amélioration requis :</b> Restitution incomplète ou trop imprécise ({len(mots_trouves)}/{len(mots_cles)} mots-clés présents).</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, reponse_str[:60]+"...", ", ".join(mots_cles), assembler_texte_html(q.get('explication')))
                    
                    st.markdown(f"<b>Mots-clés fondamentaux attendus :</b> <code>{', '.join(mots_cles)}</code>", unsafe_allow_html=True)
                    with st.expander("Consulter la grille analytique du Professeur"): 
                        st.success(f"**Modèle idéal de rédaction :** {nettoyer_question(q.get('reponse_attendue', ''))}")
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()
        
        # Gestionnaires de soumission globale
        if not st.session_state['examen_soumis']:
            if st.button("🏁 Clôturer la Session et Corriger ma Copie", type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            if st.button("🔄 Initialiser une Nouvelle Évaluation Active", use_container_width=True):
                st.session_state['examen_soumis'] = False
                st.rerun()

    # --- MODULE DU CAHIER D'ERREURS PERMANENT ---
    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: 
            st.info("Parfait ! Aucune anomalie n'est enregistrée dans votre carnet d'erreurs pour le moment.")
        else:
            for mat, errs in mem.items():
                with st.expander(f"Discipline : {mat} ({len(errs)} fautes capitalisées)", expanded=True):
                    for e in reversed(errs):
                        st.markdown(f"""
                        <div class='erreur-log'>
                            <strong>Énoncé de la Question :</strong> {e['question']}<br>
                            <span style='color:#ff4b4b'><b>Votre production :</b> {e['choix_user']}</span> | 
                            <span style='color:#28a745'><b>Donnée académique valide :</b> {e['bonnes_rep']}</span><br><br>
                            <strong>Fondement et justification :</strong><br>{e['explication']}
                        </div>
                        """, unsafe_allow_html=True)
