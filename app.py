import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
import json
import pandas as pd
import io

# ==============================================================================
# 1. Configuration et Initialisation
# ==============================================================================
st.set_page_config(page_title="Générateur IA - Évaluations Médicales", page_icon="⚕️", layout="wide")

# ==============================================================================
# 2. Le Prompt Maître (Formaté pour JSON)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université expert en rédaction de sujets de concours de santé (LAS 1 / PASS).
Analyse les documents fournis (images de cours/schémas).

Génère 3 QCM de niveau concours, très difficiles, avec des pièges classiques (inversion, fausse précision, distracteurs proches).
Chaque question doit avoir 5 options (A, B, C, D, E).

TU DOIS OBLIGATOIREMENT RÉPONDRE UNIQUEMENT SOUS FORME DE TABLEAU JSON VALIDE, avec cette structure exacte :
[
  {
    "question": "Énoncé de la question",
    "options": {
      "A": "Proposition A", "B": "Proposition B", "C": "Proposition C", "D": "Proposition D", "E": "Proposition E"
    },
    "reponses_correctes": ["A", "C"],
    "explication": "Explication détaillée de chaque option (vraie et fausse) pour bien comprendre le cours."
  }
]
"""

# ==============================================================================
# 3. Fonctions de Traitement
# ==============================================================================
def extraire_images_pdf(buffer_fichier, page_debut, page_fin, resolution_dpi=150):
    """Extrait une plage de pages d'un PDF en images pour l'IA"""
    buffer_fichier.seek(0)
    document_pdf = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    images_extraites = []
    
    for index in range(page_debut - 1, page_fin):
        page = document_pdf[index]
        facteur_zoom = resolution_dpi / 72.0
        matrice = fitz.Matrix(facteur_zoom, facteur_zoom)
        rendu_pixmap = page.get_pixmap(matrix=matrice, alpha=False)
        
        # Conversion en image PIL (Format attendu par Gemini)
        img = Image.frombytes("RGB", [rendu_pixmap.width, rendu_pixmap.height], rendu_pixmap.samples)
        images_extraites.append(img)
        
    document_pdf.close()
    return images_extraites

def generer_qcm_gemini(images, notes_contexte):
    """Envoie les images et le prompt à Gemini"""
    prompt_final = SYSTEM_PROMPT
    if notes_contexte:
        prompt_final += f"\n\nDirectives spécifiques : {notes_contexte}"
    
    # On envoie le texte + toutes les images en une seule requête
    contenu_requete = [prompt_final] + images
    
    # Utilisation de Gemini 2.5 Flash (Rapide, excellent en vision et gratuit)
    model = genai.GenerativeModel('gemini-1.5-flash')
    reponse = model.generate_content(contenu_requete)
    
    # Nettoyage du JSON (parfois l'IA ajoute des balises ```json autour)
    texte_json = reponse.text.strip()
    if texte_json.startswith("```json"):
        texte_json = texte_json[7:-3]
    elif texte_json.startswith("```"):
        texte_json = texte_json[3:-3]
        
    return json.loads(texte_json)

# ==============================================================================
# 4. Interface Graphique
# ==============================================================================
st.title("⚕️ IA Docimologue : Générateur et Correcteur LAS 1")

with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Google Gemini :", type="password")
    if api_key:
        genai.configure(api_key=api_key)
    st.markdown("[Obtenir une clé API gratuite ici](https://aistudio.google.com/app/apikey)")

st.subheader("1. Ingestion du Cours")
fichier_upload = st.file_uploader("Importez votre PDF de cours", type=['pdf'])
contexte_additionnel = st.text_input("Précision (ex: Focus sur l'ostéologie du crâne) :")

if fichier_upload is not None:
    # Lecture du nombre de pages
    doc_temp = fitz.open(stream=fichier_upload.read(), filetype="pdf")
    total_pages = len(doc_temp)
    doc_temp.close()
    
    # Sélection des pages
    st.markdown("### 2. Sélection des pages à réviser")
    page_debut, page_fin = st.slider(
        "Choisissez la plage de pages à analyser :", 
        1, total_pages, (1, min(3, total_pages))
    )
    
    if st.button("🧠 Générer l'entraînement interactif", type="primary"):
        if not api_key:
            st.error("Veuillez entrer votre clé API Gemini dans le menu à gauche.")
        else:
            with st.spinner("L'IA lit tes schémas et prépare les pièges..."):
                try:
                    images_cours = extraire_images_pdf(fichier_upload, page_debut, page_fin)
                    qcm_data = generer_qcm_gemini(images_cours, contexte_additionnel)
                    
                    # Sauvegarde dans la session pour l'interactivité
                    st.session_state['qcm_data'] = qcm_data
                    st.success("Évaluation prête !")
                except Exception as e:
                    st.error(f"Erreur lors de la génération : {e}")

# ==============================================================================
# 5. Mode Interactif & Export Flashcards
# ==============================================================================
if 'qcm_data' in st.session_state:
    st.markdown("---")
    st.subheader("📝 Mode Entraînement en Direct")
    
    qcm_list = st.session_state['qcm_data']
    
    for i, qcm in enumerate(qcm_list):
        st.markdown(f"**Question {i+1} : {qcm['question']}**")
        
        # Création du formulaire interactif
        options_formattees = [f"{lettre}: {texte}" for lettre, texte in qcm['options'].items()]
        reponse_utilisateur = st.multiselect(f"Vos réponses pour la Q{i+1}:", options_formattees, key=f"rep_{i}")
        
        if st.button(f"Vérifier Q{i+1}", key=f"btn_{i}"):
            lettres_choisies = [rep.split(":")[0] for rep in reponse_utilisateur]
            lettres_correctes = qcm['reponses_correctes']
            
            if sorted(lettres_choisies) == sorted(lettres_correctes):
                st.success(f"✅ Parfait ! Réponses : {', '.join(lettres_correctes)}")
            else:
                st.error(f"❌ Faux. Les bonnes réponses étaient : {', '.join(lettres_correctes)}")
            
            st.info(f"**Explication du prof :** {qcm['explication']}")
        st.write("---")

    # Exportation pour Anki (Flashcards)
    st.subheader("🗂️ Exporter pour Anki")
    df_anki = pd.DataFrame({
        "Recto (Question)": [q["question"] + " " + str(q["options"]) for q in qcm_list],
        "Verso (Réponse + Explication)": [f"Réponse(s): {q['reponses_correctes']} - Explication: {q['explication']}" for q in qcm_list]
    })
    
    csv_anki = df_anki.to_csv(index=False, sep=";").encode('utf-8')
    st.download_button(
        label="📥 Télécharger les Flashcards (.csv pour Anki)",
        data=csv_anki,
        file_name="flashcards_las1.csv",
        mime="text/csv"
    )
