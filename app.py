import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
import json
import pandas as pd
import io

# ==============================================================================
# 1. Configuration de la page et Design
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - IA Multimodale", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    /* Style des onglets */
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    
    /* Fiche de synthèse (Fond noir, texte blanc) */
    .synth-box { 
        padding: 25px; 
        background-color: #000000; 
        color: #ffffff; 
        border-left: 8px solid #ff4b4b; 
        border-radius: 10px; 
        margin-bottom: 25px; 
        line-height: 1.6;
    }
    .synth-box h3, .synth-box h4, .synth-box p, .synth-box li { color: #ffffff !important; }
    
    /* Boîtes de correction */
    .correct-box { background-color: #d4edda; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #c3e6cb; color: #155724; }
    .error-box { background-color: #f8d7da; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #f5c6cb; color: #721c24; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Le Prompt Maître (JSON, Source, Mix Visuel/Texte)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université expert en LAS 1. Analyse les images/PDF fournis.

OBJECTIF : 
1. Rédiger une fiche de synthèse.
2. Générer un mélange ALÉATOIRE de QCM conceptuels (texte) et visuels (identification sur les schémas fournis).
3. Fournir une correction ultra-détaillée avec la localisation exacte de la réponse dans le cours fourni.

Paramètres :
- Matière : {matiere}
- Difficulté : {difficulte}/10 (10 = niveau concours très sélectif, pièges vicieux)
- Nombre de questions : {nombre_qcm}

TU DOIS OBLIGATOIREMENT RÉPONDRE EN JSON STRICT avec ces clés exactes :
{{
  "fiche_synthese": "Résumé structuré des points clés du document.",
  "qcm": [
    {{
      "type_question": "Visuelle ou Conceptuelle",
      "question": "Énoncé de la question",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": "Pourquoi les bonnes réponses sont justes et pourquoi les autres sont fausses.",
      "source_cours": "Où trouver l'info exacte (ex: 'Schéma de la scapula, page 2' ou 'Paragraphe sur la glycolyse, page 5')"
    }}
  ]
}}
"""

# ==============================================================================
# 3. Moteur de Traitement (Extraction & IA)
# ==============================================================================
def extraire_images_pdf(buffer_fichier, page_debut, page_fin):
    """Extrait les pages du PDF en images Haute Définition pour l'IA"""
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    images = []
    # PyMuPDF utilise un index à partir de 0
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        page = doc[i]
        # Zoom x2 pour bien lire les petits textes sur les schémas d'anatomie
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images

def generer_donnees(images, matiere, difficulte, nombre_qcm):
    """Envoie les images et les instructions à Gemini 2.5"""
    prompt_final = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Configuration stricte pour forcer le JSON et éviter les plantages
    reponse = model.generate_content(
        [prompt_final] + images, 
        generation_config={"response_mime_type": "application/json", "temperature": 0.3}
    )
    return json.loads(reponse.text)

# ==============================================================================
# 4. Interface Latérale (Configuration)
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration API")
    api_key = st.text_input("Clé Google Gemini :", type="password")
    if api_key: 
        genai.configure(api_key=api_key)
    
    st.divider()
    st.header("📚 Réglages de l'Examen")
    matiere = st.selectbox("Matière ciblée :", ["Anatomie", "Biologie / Biochimie", "Histologie / Embryologie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté (1 à 10) :", min_value=1, max_value=10, value=8)
    nombre_qcm = st.number_input("Nombre de questions :", min_value=1, max_value=20, value=5)
    
    st.divider()
    st.info("💡 L'examen générera un mix de questions sur le texte et sur l'identification de vos schémas.")

# ==============================================================================
# 5. Espace Principal (Upload & Génération)
# ==============================================================================
st.title("🎓 Simulateur de Concours LAS 1")

fichier_upload = st.file_uploader("Charge ton document de cours (PDF)", type=['pdf'])

if fichier_upload:
    doc_temp = fitz.open(stream=fichier_upload.read(), filetype="pdf")
    total_pages = len(doc_temp)
    doc_temp.close()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        page_deb, page_fin = st.slider("Pages à inclure :", 1, total_pages, (1, min(4, total_pages)))
    
    with col2:
        st.write("") # Espace vertical
        st.write("")
        if st.button("🧠 Compiler mon Sujet d'Examen", type="primary", use_container_width=True):
            if not api_key: 
                st.error("⚠️ Veuillez renseigner votre clé API à gauche.")
            else:
                with st.spinner(f"Analyse des schémas et du texte en cours... (Cela prend environ 15 secondes)"):
                    try:
                        imgs = extraire_images_pdf(fichier_upload, page_deb, page_fin)
                        st.session_state['data'] = generer_donnees(imgs, matiere, difficulte, nombre_qcm)
                        st.session_state['examen_soumis'] = False
                    except Exception as e: 
                        st.error(f"Une erreur est survenue lors de la génération : {e}")

# ==============================================================================
# 6. Zone d'Examen et Correction Interactive
# ==============================================================================
if 'data' in st.session_state:
    st.divider()
    data = st.session_state['data']
    liste_qcm = data.get('qcm', [])
    
    tab1, tab2, tab3 = st.tabs(["📖 Fiche de Révision", "✍️ Passer l'Examen", "🗂️ Exporter (Anki)"])

    # --- ONGLET 1 : SYNTHÈSE (Fond Noir) ---
    with tab1:
        synthese = data.get('fiche_synthese', 'Synthèse non disponible.')
        st.markdown(f"<div class='synth-box'><h3>📌 Ce qu'il faut absolument retenir</h3><p>{synthese}</p></div>", unsafe_allow_html=True)

    # --- ONGLET 2 : MODE EXAMEN GLOBAL ---
    with tab2:
        # Phase 1 : L'étudiant répond aux questions
        if not st.session_state.get('examen_soumis', False):
            st.info("Sélectionnez vos réponses pour toutes les questions, puis validez votre copie en bas de page.")
            
            for i, q in enumerate(liste_qcm):
                st.markdown(f"**Question {i+1}** *({q.get('type_question', 'Mixte')})* : {q.get('question', 'Erreur énoncé')}")
                options_dict = q.get('options', {})
                options_list = [f"{k}: {v}" for k, v in options_dict.items()]
                
                # Le widget sauvegarde automatiquement la réponse dans st.session_state sous la clé 'rep_i'
                st.multiselect("Cochez la ou les bonnes propositions :", options_list, key=f"rep_{i}")
                st.write("---")
            
            if st.button("🏁 Valider ma copie et voir mon score", type="primary"):
                st.session_state['examen_soumis'] = True
                st.rerun() # Recharge la page pour afficher la correction
        
        # Phase 2 : Affichage de la correction globale
        else:
            st.subheader("📊 Bilan de l'examen")
            score = 0
            
            for i, q in enumerate(liste_qcm):
                # Récupération sécurisée des bonnes réponses
                bonnes_brut = q.get('reponses_correctes', [])
                if not isinstance(bonnes_brut, list): bonnes_brut = [bonnes_brut]
                bonnes = sorted([str(b).strip() for b in bonnes_brut])
                
                # Récupération des choix de l'utilisateur depuis le session_state
                choix_utilisateur = st.session_state.get(f"rep_{i}", [])
                mes_choix = sorted([r.split(":")[0] for r in choix_utilisateur])
                
                # Vérification
                est_juste = (bonnes == mes_choix)
                if est_juste and len(bonnes) > 0:
                    score += 1
                
                # Affichage visuel du statut (Vert/Rouge)
                div_class = "correct-box" if est_juste else "error-box"
                statut_texte = "✅ JUSTE" if est_juste else "❌ FAUX"
                
                st.markdown(f"""
                <div class="{div_class}">
                    <strong>Question {i+1} : {statut_texte}</strong><br>
                    <em>{q.get('question', '')}</em>
                </div>
                """, unsafe_allow_html=True)
                
                col_a, col_b = st.columns(2)
                col_a.write(f"**Tes choix :** {', '.join(mes_choix) if mes_choix else 'Aucune réponse'}")
                col_b.write(f"**Corrigé officiel :** {', '.join(bonnes)}")
                
                # Explications et Source
                with st.expander("🔍 Voir l'explication et la source du cours"):
                    st.write(f"**Démonstration :** {q.get('explication', 'Non fournie.')}")
                    st.success(f"📍 **Source du cours :** {q.get('source_cours', 'Non précisée.')}")
                
                st.write("<br>", unsafe_allow_html=True)
            
            # Calcul et affichage de la note finale
            if len(liste_qcm) > 0:
                note_sur_20 = (score / len(liste_qcm)) * 20
                st.metric(label="Ta Note Finale", value=f"{note_sur_20:.1f} / 20")
            
            if st.button("🔄 Refaire l'examen (Réinitialiser)", type="secondary"):
                st.session_state['examen_soumis'] = False
                st.rerun()

    # --- ONGLET 3 : EXPORT ANKI ---
    with tab3:
        st.write("Télécharge ces questions pour les injecter dans ton application Anki.")
        try:
            df_anki = pd.DataFrame({
                "Recto (Question)": [q.get("question", "") + " | " + str(q.get("options", {})) for q in liste_qcm],
                "Verso (Réponse)": [f"Réponses : {q.get('reponses_correctes', '')} | Explication : {q.get('explication', '')} | Source : {q.get('source_cours', '')}" for q in liste_qcm]
            })
            csv_anki = df_anki.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button(
                label="📥 Télécharger le fichier CSV", 
                data=csv_anki, 
                file_name=f"flashcards_las1.csv", 
                mime="text/csv"
            )
        except Exception as e:
            st.error("Génération des flashcards momentanément indisponible.")
