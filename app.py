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
    
    .synth-box { padding: 25px; background-color: #1e1e1e; color: #ffffff; border-left: 8px solid #ff4b4b; border-radius: 10px; margin-bottom: 25px; }
    .synth-box h1, .synth-box h2, .synth-box h3, .synth-box h4, .synth-box p, .synth-box li { color: #ffffff !important; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    
    /* CORRECTION DU BUG BLANC SUR BLANC (Adapté au Dark Mode) */
    .erreur-log { 
        border-left: 4px solid #ff4b4b; 
        padding: 15px; 
        margin-bottom: 15px; 
        background-color: #2b2b2b;
        color: #ffffff;
        border-radius: 5px; 
        border: 1px solid #444; 
    }
    .erreur-log strong { color: #ffffff; }
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
# 3. Moteur IA 
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université expert en LAS 1. 
Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre : {nombre_qcm}

STYLE : {style_question}
MIXAGE : Base-toi 50% sur le texte du COURS OFFICIEL fourni et 50% sur les notes de l'étudiant : "{notes_etudiant}"

⚠️ RÈGLE DE SYNTAXE ABSOLUE : Tu ne dois JAMAIS utiliser de guillemets doubles (") à l'intérieur de tes phrases de texte. Utilise EXCLUSIVEMENT des guillemets simples (').

⚠️ RÈGLES PÉDAGOGIQUES (TRÈS IMPORTANT) :
1. SYNTHÈSE : Rédige une fiche de synthèse extrêmement détaillée, précise et exhaustive du cours. Ne la bâcle pas. Reprends les définitions, les mécanismes et les détails cruciaux. Utilise une belle mise en forme Markdown.
2. QCM : Génère EXACTEMENT {nombre_qcm} questions. Ce sont des QCM médicaux : prévois souvent PLUSIEURS réponses exactes par question (ex: A et C).
3. "indice" : Fournis un indice subtil.
4. "mnemotechnique" : Invente une astuce mentale pour retenir l'information.

FORMAT JSON STRICT :
{{
  "fiche_synthese": "Ton résumé de cours complet, détaillé et structuré ici...",
  "qcm": [
    {{
      "type_question": "Conceptuelle" ou "Calcul",
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": "Justification lettre par lettre...",
      "source_cours": "Source...",
      "indice": "Indice...",
      "mnemotechnique": "Astuce..."
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
