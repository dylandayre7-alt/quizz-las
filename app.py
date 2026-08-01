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
st.set_page_config(page_title="Révisions Vétérinaires", page_icon="🐾", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #2e7b32; color: white; font-weight: bold; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .warning-box { background-color: #856404; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #ffeeba; border: 1px solid #ffeeba;}
    
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & Bouclier de Sauvetage Amélioré
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

def sauvetage_json_coupe(texte_ia):
    # CORRECTION BUG : Nettoyage des balises Markdown de l'IA (ex: ```json ... ```)
    match = re.search(r'```(?:json)?(.*?)```', texte_ia, re.DOTALL)
    if match:
        texte_brut = match.group(1).strip()
    else:
        debut = texte_ia.find('{')
        fin = texte_ia.rfind('}')
        if debut == -1 or fin == -1:
            raise Exception("L'IA n'a pas renvoyé de format lisible. Baisse le nombre de questions.")
        texte_brut = texte_ia[debut:fin+1]

    try:
        return json.loads(texte_brut, strict=False)
    except json.JSONDecodeError:
        tentatives_fermeture = ['}', ']}', '"]}', '}]}', '"]}]}']
        for t in tentatives_fermeture:
            try:
                donnees = json.loads(texte_brut + t, strict=False)
                return donnees
            except:
                pass
        raise Exception("Le document a généré un code trop complexe.")

# ==============================================================================
# 3. Moteur IA (QRM Ciblés : Étiologie, Pathogénie, Clinique...)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en biologie vétérinaire, parasitologie, pathologie et nutrition animale. 
Matière : {matiere} | Difficulté : {difficulte}/10 

Génère EXACTEMENT {nb_qcm} questions à choix multiples (QRM) basées STRICTEMENT sur le cours fourni.
ATTENTION : Il peut y avoir UNE OU PLUSIEURS bonnes réponses par question.

OBLIGATION ABSOLUE : Tes questions DOIVENT cibler de manière extrêmement précise ces domaines (selon ce qui est présent dans le texte) :
1. Étiologie : Famille, Règne, Phylum, Classe, Ordre, Genre, Espèce, et Localisation (ex: "Quelle est la classe de Sarcoptes scabiei ?").
2. Épidémiologie (ex: "Quels sont les facteurs favorisants de X ?").
3. Signes cliniques (ex: "Quels sont les signes cliniques associés à Y ?").
4. Diagnostic (ex: "Quelles méthodes permettent le diagnostic de Z ?").
5. Traitement et Prévention.
6. Cycle parasitaire / Cycle de vie.
7. Pathologie / Pathogénie.

RÈGLES DE RÉDACTION :
1. Propose toujours 4 ou 5 choix de réponses.
2. Crée des pièges intelligents (ex: confondre l'Ordre et la Famille, ou un stade larvaire).
3. La clé "bonnes_reponses" doit être une LISTE contenant le ou les textes EXACTS des choix corrects.

RÈGLES INFORMATIQUES CRITIQUES :
1. Réponds UNIQUEMENT via un objet JSON valide.
2. N'utilise JAMAIS de guillemets doubles (") dans tes phrases. Remplace-les par des apostrophes (').
3. Écris tout sur une seule ligne continue par champ.

FORMAT JSON REQUIS :
{{
  "questions": [
    {{
      "type": "QRM",
      "question": "Concernant Sarcoptes scabiei, quelles propositions sur son étiologie sont exactes ?",
      "choix": ["Il appartient au phylum des Nematoda", "Il appartient à la classe des Arachnidia", "Il cause la gale sarcoptique", "Il se localise dans le caecum"],
      "bonnes_reponses": ["Il appartient à la classe des Arachnidia", "Il cause la gale sarcoptique"],
      "explication": ["Rappel du cours et justification technique..."],
      "indice": "Piste de réflexion...",
      "mnemotechnique": "Astuce..."
    }}
  ]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcm=nombre_qcm)
    
    cle_propre = re.sub(r'[^a-zA-Z0-9_-]', '', api_key)
    
    # CORRECTION BUG URL : Utilisation de .strip() pour enlever les espaces invisibles
    url_base = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent".strip()
    
    payload = {
        "contents": [{"parts": [{"text": prompt + "\nCOURS :\n" + texte_pdf + "\nNOTES :\n" + texte_word}]}], 
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}
    }
    
    rep = requests.post(url_base, params={"key": cle_propre}, json=payload)
    if rep.status_code != 200: raise Exception(f"Erreur API ({rep.status_code}) : {rep.text}")
    
    texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
    return sauvetage_json_coupe(texte_ia)

# ==============================================================================
# 4. Interface Graphique (Avec Formulaire de Génération pour éviter le Bug)
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Parasitologie / Pathologie", "Nutrition animale", "Biologie vétérinaire", "Gestion de clinique"])
    difficulte = st.slider("Niveau de pièges :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de Questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Mode Examen (Masquer les indices)")

st.title("🐾 Simulateur d'Entraînement Vétérinaire (Choix Multiples)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    # CORRECTION BUG : Utilisation d'un formulaire pour forcer l'exécution propre
    with st.form("formulaire_generation"):
        st.warning("⚠️ Astuce : Analyse des petits blocs de cours (3 à 6 pages maximum).")
        p_deb, p_fin = st.slider("Pages à analyser :", 1, p_tot, (1, min(5, p_tot)))
        bouton_generer = st.form_submit_button("🚀 Générer le Test", type="primary", use_container_width=True)
        
        if bouton_generer:
            if not api_key: 
                st.error("Clé API manquante ! Renseigne-la dans la barre latérale.")
            else:
                with st.spinner("Création des questions à choix multiples en cours..."):
                    try:
                        txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                        txt_w = lire_word(f_word) if f_word else ""
                        st.session_state['data'] = generer_donnees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                        st.session_state['examen_soumis'] = False
                        st.session_state['reponses_utilisateur'] = {} # Réinitialise les réponses
                        st.rerun()
                    except Exception as e: 
                        st.error(f"❌ {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Entraînement", "📓 Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)
        
        if 'reponses_utilisateur' not in st.session_state:
            st.session_state['reponses_utilisateur'] = {}
        
        for i, q in enumerate(liste_questions):
            question_propre = nettoyer_question(q.get('question', ''))
            st.markdown(f"**Question {i+1}** 🔹 {question_propre}")
            st.caption("*Il peut y avoir plusieurs bonnes réponses.*")
            
            choix = q.get('choix', [])
            
            # Stockage des sélections pour cette question
            if f"q_{i}" not in st.session_state['reponses_utilisateur']:
                st.session_state['reponses_utilisateur'][f"q_{i}"] = []
                
            reponses_cochees = []
            for j, choix_texte in enumerate(choix):
                coche = st.checkbox(choix_texte, key=f"chk_{i}_{j}", disabled=is_disabled)
                if coche:
                    reponses_cochees.append(choix_texte)
            
            # Mise à jour dans la session
            st.session_state['reponses_utilisateur'][f"q_{i}"] = reponses_cochees
            
            if not is_disabled and not mode_examen:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    with st.expander("💡 Aide de réflexion"): st.info(nettoyer_question(q.get('indice', 'Pas d indice.')))
                with col_h2:
                    with st.expander("🧠 Mnémotechnique"): st.warning(nettoyer_question(q.get('mnemotechnique', 'Rien.')))
            
            # Phase de correction
            if is_disabled:
                reponse_soumise = set(st.session_state['reponses_utilisateur'].get(f"q_{i}", []))
                bonnes_reps = set(q.get('bonnes_reponses', []))
                
                # Vérification stricte : il faut avoir coché TOUTES les bonnes réponses et AUCUNE mauvaise
                if reponse_soumise == bonnes_reps and len(bonnes_reps) > 0:
                    st.markdown(f"<div class='correct-box'>✅ <b>Parfait !</b></div>", unsafe_allow_html=True)
                else:
                    rep_str = "Aucune" if not reponse_soumise else " | ".join(reponse_soumise)
                    bonnes_str = " | ".join(bonnes_reps)
                    st.markdown(f"<div class='error-box'>❌ <b>Incomplet ou faux.</b><br>Tes choix : {rep_str}<br><b>Réponses attendues : {bonnes_str}</b></div>", unsafe_allow_html=True)
                    ajouter_erreur_session(matiere, question_propre, rep_str, bonnes_str, assembler_texte_html(q.get('explication')))
                
                with st.expander("Correction détaillée et Explications"): 
                    st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()
            
        if is_disabled:
            st.info("🎓 **Évaluation terminée.** Tes erreurs ont été enregistrées dans le cahier.")
            if st.button("🔄 Lancer un nouveau test", use_container_width=True): 
                st.session_state['examen_soumis'] = False
                st.session_state['reponses_utilisateur'] = {}
                st.rerun()
        else:
            if st.button("🏁 Corriger le test", type="primary", use_container_width=True): 
                st.session_state['examen_soumis'] = True
                st.rerun()

    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: 
            st.info("Aucune erreur enregistrée.")
        else:
            for mat, errs in mem.items():
                with st.expander(f"{mat} ({len(errs)} erreurs)"):
                    for e in reversed(errs):
                        st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Ta sélection : {e['choix_user']} <br> <b>Attendu : {e['bonnes_rep']}</b><br><br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
