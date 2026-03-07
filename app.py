import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
import json
import pandas as pd
import io

# ==============================================================================
# 1. Configuration et Design
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - IA Premium", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    .synth-box { padding: 20px; background-color: #000000; color: #ffffff; border-left: 5px solid #ff4b4b; border-radius: 8px; margin-bottom: 20px; }
    .synth-box h3 { color: #ffffff; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Le Prompt Dynamique
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université intraitable, expert en rédaction de sujets de concours de santé (LAS 1 / PASS).
Matière : {matiere}
Niveau de difficulté : {difficulte}/10
Nombre de questions : {nombre_qcm}

Directives :
- Si Mode Examen = "OUI" : Pose UNIQUEMENT des questions "High Yield" (probables au concours). Utilise des tournures ambiguës, piège sur des détails infimes, ou des inversions de schémas.
- Si Mode Examen = "NON" : Fais des questions d'entraînement classiques.

Analyse les documents fournis.
TU DOIS ABSOLUMENT UTILISER CES CLÉS JSON (Ne change aucune lettre) :
"fiche_synthese", "qcm", "question", "options", "reponses_correctes", "explication".

Format imposé :
{{
  "fiche_synthese": "Résumé...",
  "qcm": [
    {{
      "question": "Énoncé...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": "..."
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
        matiere=matiere, difficulte=difficulte, 
        nombre_qcm=nombre_qcm, mode_examen=etat_examen
    )
    
    contenu_requete = [prompt_final] + images
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    try:
        reponse = model.generate_content(
            contenu_requete,
            generation_config={"response_mime_type": "application/json", "temperature": 0.2}
        )
        return json.loads(reponse.text)
    except Exception as e:
        raise Exception(f"L'IA n'a pas pu formater la réponse.\nErreur : {str(e)}")

# ==============================================================================
# 4. Interface Graphique & Sidebar
# ==============================================================================
st.title("🎓 Prépa LAS 1 : Le Générateur Ultime")

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
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

st.subheader("1. Importation du document")
col1, col2 = st.columns([2, 1])

with col1:
    fichier_upload = st.file_uploader("Glisse ton PDF ici", type=['pdf'])

if fichier_upload is not None:
    doc_temp = fitz.open(stream=fichier_upload.read(), filetype="pdf")
    total_pages = len(doc_temp)
    doc_temp.close()
    
    with col2:
        st.write(" ") 
        st.write(" ")
        page_debut, page_fin = st.slider("Plage de pages :", 1, total_pages, (1, min(3, total_pages)))
    
    texte_bouton = "🏁 Lancer l'Examen Blanc" if mode_examen else "🚀 Lancer l'analyse du cours"
    
    if st.button(texte_bouton, type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ N'oublie pas ta clé API !")
        else:
            with st.spinner("L'IA prépare tes QCM... (Veuillez patienter quelques secondes)"):
                try:
                    images_cours = extraire_images_pdf(fichier_upload, page_debut, page_fin)
                    donnees_generees = generer_qcm_gemini(images_cours, matiere, difficulte, nombre_qcm, mode_examen)
                    st.session_state['data'] = donnees_generees
                    st.session_state['examen_valide'] = False
                    st.success("✅ Sujet prêt !")
                except Exception as e:
                    st.error(f"Erreur : {e}")

# ==============================================================================
# 5. Affichage des Résultats (Sécurisé)
# ==============================================================================
if 'data' in st.session_state:
    st.divider()
    data = st.session_state['data']
    
    tab1, tab2, tab3 = st.tabs(["📖 Fiche de Synthèse", "📝 QCM", "🗂️ Export Flashcards"])
    
    with tab1:
        synthese = data.get('fiche_synthese', 'Résumé non généré.')
        st.markdown(f"<div class='synth-box'><h3>📌 L'essentiel à retenir</h3><p>{synthese}</p></div>", unsafe_allow_html=True)

    with tab2:
        # Récupération sécurisée de la liste des QCM
        liste_qcm = data.get('qcm', [])
        
        if mode_examen:
            st.warning("⚠️ MODE EXAMEN ACTIF : Réponds à tout avant de valider.")
            reponses_utilisateur = {}
            
            for i, qcm in enumerate(liste_qcm):
                question = qcm.get('question', f'Question {i+1}')
                options = qcm.get('options', {})
                st.markdown(f"**Question {i+1} : {question}**")
                options_formattees = [f"{lettre}: {texte}" for lettre, texte in options.items()]
                reponses_utilisateur[i] = st.multiselect(f"Tes choix :", options_formattees, key=f"exam_{i}")
                st.write("---")
            
            if st.button("Valider ma copie", type="primary"):
                st.session_state['examen_valide'] = True
                
            if st.session_state.get('examen_valide', False):
                st.subheader("📊 Résultats")
                score = 0
                for i, qcm in enumerate(liste_qcm):
                    # Extraction ultra-sécurisée de la bonne réponse
                    bonnes_brut = qcm.get('reponses_correctes', qcm.get('reponse_correcte', []))
                    if not isinstance(bonnes_brut, list): bonnes_brut = [bonnes_brut]
                    bonnes = sorted([str(b).strip() for b in bonnes_brut])
                    
                    choix = sorted([r.split(":")[0] for r in reponses_utilisateur[i]])
                    
                    if choix == bonnes and len(bonnes) > 0:
                        score += 1
                        st.success(f"Question {i+1} : JUSTE ✅")
                    else:
                        st.error(f"Question {i+1} : FAUX ❌ (Réponse : {', '.join(bonnes)})")
                    
                    with st.expander("Voir l'explication"):
                        st.write(qcm.get('explication', 'Pas d\'explication.'))
                
                if len(liste_qcm) > 0:
                    note = (score / len(liste_qcm)) * 20
                    st.metric(label="Note Finale", value=f"{note:.1f} / 20")

        else:
            for i, qcm in enumerate(liste_qcm):
                question = qcm.get('question', f'Question {i+1}')
                options = qcm.get('options', {})
                
                with st.expander(f"Question {i+1} : {question}", expanded=True):
                    options_formattees = [f"{lettre}: {texte}" for lettre, texte in options.items()]
                    reponse_utilisateur = st.multiselect(f"Tes réponses :", options_formattees, key=f"entrainement_{i}")
                    
                    if st.button(f"Vérifier", key=f"btn_{i}"):
                        bonnes_brut = qcm.get('reponses_correctes', qcm.get('reponse_correcte', []))
                        if not isinstance(bonnes_brut, list): bonnes_brut = [bonnes_brut]
                        bonnes = sorted([str(b).strip() for b in bonnes_brut])
                        
                        choix = sorted([r.split(":")[0] for r in reponse_utilisateur])
                        
                        if choix == bonnes and len(bonnes) > 0:
                            st.success(f"✅ Vrai ! Réponses : {', '.join(bonnes)}")
                        else:
                            st.error(f"❌ Faux. Les bonnes réponses étaient : {', '.join(bonnes)}")
                        
                        st.info(f"**Explication :** {qcm.get('explication', 'Pas d\'explication.')}")

    with tab3:
        st.write("Télécharge tes questions pour Anki.")
        try:
            df_anki = pd.DataFrame({
                "Recto": [q.get("question", "") + " " + str(q.get("options", {})) for q in liste_qcm],
                "Verso": [f"Réponse: {q.get('reponses_correctes', '')} - {q.get('explication', '')}" for q in liste_qcm]
            })
            csv_anki = df_anki.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("📥 Télécharger le CSV", data=csv_anki, file_name="flashcards.csv", mime="text/csv")
        except Exception:
            st.error("Génération des flashcards impossible pour cette série.")
