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
    
    # Découpage en blocs de 15 pages : Assez grand pour être rapide, assez petit pour ne jamais saturer la mémoire de l'IA
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
    
    for idx, chunk in enumerate(chunks_texte):
        if len(all_questions) >= nombre_qcm:
            break
            
        barre_progression.progress(idx / len(chunks_texte))
        
        prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        # L'ARME ABSOLUE : "responseMimeType": "application/json" oblige l'IA à renvoyer un code JSON structuré valide.
        payload = {
            "contents": [{"parts": [{"text": prompt + "\nNOTES WORD EXTRA:\n" + (texte_word or "") + "\n\nEXTRAIT DU COURS :\n" + chunk}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json" 
            }
        }
        
        try:
            rep = requests.post(url, json=payload)
            if rep.status_code == 200:
                texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Sécurité : Si l'IA entoure quand même son JSON de balises markdown, on les nettoie
                if texte_ia.startswith('```'):
                    texte_ia = re.sub(r'^
http://googleusercontent.com/immersive_entry_chip/0
