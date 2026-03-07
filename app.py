import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
import json
import pandas as pd
import io

# ==============================================================================
# 1. Configuration et Design de la page
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - IA Premium", page_icon="🎓", layout="wide")

# CSS personnalisé pour embellir l'interface (Fond NOIR et texte BLANC pour la synthèse)
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    .synth-box { 
        padding: 20px; 
        background-color: #000000; 
        color: #ffffff; 
        border-left: 5px solid #ff4b4b; 
        border-radius: 8px; 
        margin-bottom: 20px; 
    }
    .synth-box h3 { color: #ffffff; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Le Prompt Dynamique (Avec Mode Examen)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université intraitable, expert en rédaction de sujets de concours de santé (LAS 1 / PASS).
Matière : {matiere}
Niveau de difficulté : {difficulte}/10
Nombre de questions : {nombre_qcm}
Mode Examen activé : {mode_examen}

Directives selon le mode :
- Si Mode Examen = "OUI" : Pose UNIQUEMENT des questions "High Yield" (très probables au concours). Utilise des tournures ambiguës, piège sur des détails infimes, des unités, ou des inversions de schémas. Le niveau doit être maximal.
- Si Mode Examen = "NON" : Fais des questions d'entraînement classiques pour bien comprendre le cours.

Analyse les documents fournis (images de cours/schémas).

Tâche 1 : Rédige une FICHE DE SYNTHÈSE (3 à 5 points absolument cruciaux à retenir).
Tâche 2 : Génère {nombre_qcm} QCM/QCU à 5 options (A, B, C, D, E).

TU DOIS OBLIGATOIREMENT RÉPONDRE UNIQUEMENT SOUS FORME DE JSON VALIDE, avec cette structure exacte :
{{
  "fiche_synthese": "Le résumé clair et structuré du cours ici...",
  "qcm": [
    {{
      "question": "Énoncé de la question",
      "options": {{
        "A": "Proposition A", "B": "Proposition B", "C": "Proposition C", "D": "Proposition D", "E": "Proposition E"
      }},
      "reponses_correctes": ["A", "C"],
      "explication": "Explication détaillée de chaque option."
    }}
  ]
}}
"""

# ==============================================================================
# 3. Fonctions de Traitement
# ==============================================================================
def extraire_images_pdf(buffer_fichier, page_debut, page_fin, resolution_dpi=150):
    buffer_fichier.seek(0)
    document_pdf = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    images_extraites = []
    
    for index in range(page_debut - 1, page_fin):
        page = document_pdf[index]
        matrice = fitz.Matrix(resolution_dpi / 72.0, resolution_dpi / 72.0)
        rendu_pixmap = page.get_pixmap(matrix=matrice, alpha=False)
        img = Image.frombytes("RGB", [rendu_pixmap.width, rendu_pixmap.height], rendu_pixmap.samples)
        images_extraites.append(img)
        
    document_pdf.close()
    return images_extraites

def generer_qcm_gemini(images, matiere, difficulte, nombre_qcm, est_mode_examen):
    etat_examen = "OUI" if est_mode_examen else "NON"
    prompt_final = SYSTEM_PROMPT.format(
        matiere=matiere, 
        difficulte=difficulte, 
        nombre_qcm=nombre_qcm,
        mode_examen=etat_examen
    )
    
    contenu_requete = [prompt_final] + images
    
    # Utilisation du modèle valide
    model = genai.GenerativeModel('gemini-2.5-flash')
    reponse = model.generate_content(contenu_requete)
    
    texte_json = reponse.text.strip()
    if texte_json.startswith("```json"):
        texte_json = texte_json[7:-3]
    elif texte_json.startswith("```"):
        texte_json = texte_json[3:-3]
        
    return json.loads(texte_json)

# ==============================================================================
# 4. Interface Graphique & Sidebar
# ==============================================================================
st.title("🎓 Prépa LAS 1 : Le Générateur Ultime")

# --- BARRE LATÉRALE (Paramètres) ---
with st.sidebar:
    st.header("⚙️ Paramètres de l'IA")
    api_key = st.text_input("Clé API Google Gemini :", type="password")
    if api_key:
        genai.configure(api_key=api_key)
    
    st.divider()
    st.header("📚 Personnalisation")
    matiere = st.selectbox("Matière du cours :", ["Anatomie", "Biologie / Biochimie", "Droit Médical"])
    difficulte = st.slider("Niveau de difficulté (1 à 10) :", min_value=1, max_value=10, value=7)
    nombre_qcm = st.number_input("Nombre de questions :", min_value=1, max_value=20, value=5)
    
    st.divider()
    mode_examen = st.toggle("🚨 Activer le Mode Examen", help="Masque les corrections immédiates et augmente la difficulté des pièges.")

# --- ZONE PRINCIPALE (Upload) ---
st.subheader("1. Importation du document")
col1, col2 = st.columns([2, 1])

with col1:
    fichier_upload = st.file_uploader("Glisse ton PDF ici", type=['pdf'])

if fichier_upload is not None:
    doc_temp = fitz.open(stream=fichier_upload.read(), filetype="pdf")
    total_pages = len(doc_temp)
    doc_temp.close()
    
    with col2:
        st.write(" ") # Espace
        st.write(" ")
        page_debut, page_fin = st.slider("Plage de pages :", 1, total_pages, (1, min(3, total_pages)))
    
    texte_bouton = "🏁 Lancer l'Examen Blanc" if mode_examen else "🚀 Lancer l'analyse du cours"
    
    if st.button(texte_bouton, type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ N'oublie pas ta clé API dans le menu de gauche !")
        else:
            with st.spinner(f"L'IA prépare tes {nombre_qcm} QCM..."):
                try:
                    images_cours = extraire_images_pdf(fichier_upload, page_debut, page_fin)
                    donnees_generees = generer_qcm_gemini(images_cours, matiere, difficulte, nombre_qcm, mode_examen)
                    st.session_state['data'] = donnees_generees
                    st.session_state['examen_valide'] = False # Réinitialise l'état de l'examen
                    st.success("✅ Sujet prêt !")
                except Exception as e:
                    st.error(f"Erreur : {e}")

# ==============================================================================
# 5. Affichage des Résultats (Système d'onglets)
# ==============================================================================
if 'data' in st.session_state:
    st.divider()
    data = st.session_state['data']
    
    tab1, tab2, tab3 = st.tabs(["📖 Fiche de Synthèse", "📝 QCM", "🗂️ Export Flashcards"])
    
    # ONGLET 1 : La Synthèse (Fond Noir, Texte Blanc)
    with tab1:
        st.markdown(f"<div class='synth-box'><h3>📌 L'essentiel à retenir</h3><p>{data['fiche_synthese']}</p></div>", unsafe_allow_html=True)

    # ONGLET 2 : Les QCM (Logique conditionnelle selon le mode)
    with tab2:
        # ---------------------------------------------------------
        # MODE EXAMEN (Correction à la fin)
        # ---------------------------------------------------------
        if mode_examen:
            st.warning("⚠️ MODE EXAMEN ACTIF : Les réponses sont masquées. Réponds à toutes les questions avant de valider.")
            
            reponses_utilisateur = {}
            for i, qcm in enumerate(data['qcm']):
                st.markdown(f"**Question {i+1} : {qcm['question']}**")
                options_formattees = [f"{lettre}: {texte}" for lettre, texte in qcm['options'].items()]
                reponses_utilisateur[i] = st.multiselect(f"Tes choix :", options_formattees, key=f"exam_{i}")
                st.write("---")
            
            if st.button("Valider ma copie", type="primary"):
                st.session_state['examen_valide'] = True
                
            if st.session_state.get('examen_valide', False):
                st.subheader("📊 Résultats de l'examen")
                score = 0
                for i, qcm in enumerate(data['qcm']):
                    bonnes = sorted(qcm['reponses_correctes'])
                    choix = sorted([r.split(":")[0] for r in reponses_utilisateur[i]])
                    
                    if choix == bonnes:
                        score += 1
                        st.success(f"Question {i+1} : JUSTE ✅")
                    else:
                        st.error(f"Question {i+1} : FAUX ❌ (Il fallait répondre : {', '.join(bonnes)})")
                    
                    with st.expander("Voir l'explication du correcteur"):
                        st.write(qcm['explication'])
                
                note = (score / len(data['qcm'])) * 20
                st.metric(label="Note Finale", value=f"{note:.1f} / 20")

        # ---------------------------------------------------------
        # MODE ENTRAÎNEMENT CLASSIQUE (Correction immédiate)
        # ---------------------------------------------------------
        else:
            for i, qcm in enumerate(data['qcm']):
                with st.expander(f"Question {i+1} : {qcm['question']}", expanded=True):
                    options_formattees = [f"{lettre}: {texte}" for lettre, texte in qcm['options'].items()]
                    reponse_utilisateur = st.multiselect(f"Sélectionne tes réponses :", options_formattees, key=f"entrainement_{i}")
                    
                    if st.button(f"Vérifier", key=f"btn_{i}"):
                        lettres_choisies = [rep.split(":")[0] for rep in reponse_utilisateur]
                        lettres_correctes = qcm['reponses_correctes']
                        
                        if sorted(lettres_choisies) == sorted(lettres_correctes):
                            st.success(f"✅ Vrai ! Réponses : {', '.join(lettres_correctes)}")
                        else:
                            st.error(f"❌ Faux. Les bonnes réponses étaient : {', '.join(lettres_correctes)}")
                        
                        st.info(f"**Explication du professeur :** {qcm['explication']}")

    # ONGLET 3 : Export Anki
    with tab3:
        st.write("Télécharge tes questions pour les réviser plus tard sur Anki.")
        df_anki = pd.DataFrame({
            "Recto (Question)": [q["question"] + " " + str(q["options"]) for q in data['qcm']],
            "Verso (Réponse + Explication)": [f"Réponse(s): {q['reponses_correctes']} - Explication: {q['explication']}" for q in data['qcm']]
        })
        
        csv_anki = df_anki.to_csv(index=False, sep=";").encode('utf-8')
        st.download_button(
            label="📥 Télécharger le CSV",
            data=csv_anki,
            file_name="flashcards_concours.csv",
            mime="text/csv"
        )
