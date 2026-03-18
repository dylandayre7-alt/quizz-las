import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
import json
import pandas as pd
import docx
import os
from datetime import datetime

# ==============================================================================
# 1. Configuration et Design
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - IA Premium", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    .synth-box { padding: 25px; background-color: #000000; color: #ffffff; border-left: 8px solid #ff4b4b; border-radius: 10px; margin-bottom: 25px; }
    .synth-box h3, .synth-box h4, .synth-box p, .synth-box li { color: #ffffff !important; }
    .correct-box { background-color: #d4edda; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #155724; }
    .error-box { background-color: #f8d7da; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #721c24; }
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #f9f9f9; border-radius: 5px; border: 1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Gestion de la Mémoire Session
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur_session(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    
    for err in st.session_state['cahier_memoire'][matiere]:
        if err['question'] == question: return

    st.session_state['cahier_memoire'][matiere].append({
        "date": datetime.now().strftime("%d/%m/%Y"),
        "question": question,
        "choix_user": choix_user,
        "bonnes_rep": bonnes_rep,
        "explication": explication
    })

# ==============================================================================
# 3. Moteur IA (Nouveau : Indice et Mnémotechnique)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université expert en LAS 1. 
Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre : {nombre_qcm}

STYLE : {style_question}

MIXAGE : Base-toi 50% sur le texte du COURS OFFICIEL fourni et 50% sur les notes de l'étudiant : "{notes_etudiant}"

⚠️ RÈGLE DE SYNTAXE ABSOLUE : Tu ne dois JAMAIS utiliser de guillemets doubles (") à l'intérieur de tes phrases de texte. Utilise EXCLUSIVEMENT des guillemets simples (').

⚠️ RÈGLES PÉDAGOGIQUES POUR CHAQUE QUESTION :
1. "indice" : Fournis un petit indice subtil (une phrase) qui met l'étudiant sur la voie sans donner la réponse brute. Fais appel à sa mémoire active.
2. "mnemotechnique" : Invente une astuce (acronyme, phrase drôle/absurde, image mentale) pour retenir la réponse à cette question précise à vie.

FORMAT JSON STRICT :
{{
  "fiche_synthese": "### Titre 1\\n- **Concept clé** : explication...\\n### Titre 2\\n- ...",
  "qcm": [
    {{
      "type_question": "Conceptuelle" ou "Calcul",
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": "Justification lettre par lettre...",
      "source_cours": "Source (ex: Page 12)...",
      "indice": "Souviens-toi de la règle des 3C...",
      "mnemotechnique": "Pour retenir ça, dis-toi que le Chien Mange la Saucisse (CMS)..."
    }}
  ]
}}
"""

def extraire_texte_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    texte_complet = ""
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        texte_complet += f"\n\n--- PAGE {i+1} ---\n\n"
        texte_complet += doc[i].get_text("text")
    doc.close()
    return texte_complet

def lire_word(buffer_fichier):
    doc = docx.Document(buffer_fichier)
    return "\n".join([para.text for para in doc.paragraphs])

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen):
    notes = texte_word if texte_word else "Aucune note."
    style = "Style ANNALES (Très Difficile, QCM à choix multiples, proposition E 'Aucune n'est exacte')." if est_mode_examen else "Style APPRENTISSAGE (Direct, clair, questions à choix multiples)."
    
    prompt_final = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm, notes_etudiant=notes, style_question=style)
    contenu_requete = f"TEXTE DU COURS OFFICIEL À ANALYSER :\n{texte_pdf}"
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    reponse = model.generate_content(
        [prompt_final, contenu_requete], 
        generation_config={"response_mime_type": "application/json", "temperature": 0.2}
    )
    
    texte_brut = reponse.text.strip()
    if texte_brut.startswith("
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2

**Concrètement, qu'est-ce qui change quand tu vas tester le site ?**
Sous chaque question d'entraînement, tu vas voir deux nouveaux menus déroulants : `💡 Besoin d'un indice ?` et `🧠 Astuce Mnémotechnique`.
Si tu coinces, tu ouvres l'indice. Et quand tu vérifies ta réponse, la correction s'affiche, avec l'astuce mentale pour ne plus jamais faire l'erreur. C'est le combo ultime pour retenir des tonnes d'informations !
