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
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
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
    .correct-box { background-color: #d4edda; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #c3e6cb; color: #155724; }
    .error-box { background-color: #f8d7da; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #f5c6cb; color: #721c24; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Le Prompt Maître (JSON, Index Image, Cases)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université expert en LAS 1. 

OBJECTIF : 
1. Rédiger une fiche de synthèse.
2. Générer un mélange de QCM conceptuels et VISUELS (sur les schémas).
3. Fournir une correction détaillée avec la source.

Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre : {nombre_qcm}

RÈGLE IMPORTANTE POUR LES IMAGES :
Les images fournies sont indexées de 0 à N. Si ta question porte sur un schéma précis, indique son index dans "index_image". Si la question est purement textuelle, mets -1.

TU DOIS OBLIGATOIREMENT RÉPONDRE EN JSON STRICT :
{{
  "fiche_synthese": "Résumé structuré.",
  "qcm": [
    {{
      "type_question": "Visuelle ou Conceptuelle",
      "index_image": 0,
      "question": "Énoncé",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": "Démonstration.",
      "source_cours": "Source exacte."
    }}
  ]
}}
"""

# ==============================================================================
# 3. Moteur de Traitement
# ==============================================================================
def extraire_images_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    images = []
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images

def generer_donnees(images, matiere, difficulte, nombre_qcm):
    prompt_final = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm)
    model = genai.GenerativeModel('gemini-2.5-flash')
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
    st.header("📚 Réglages")
    matiere = st.selectbox("Matière :", ["Anatomie", "Biologie / Biochimie", "Histologie", "Droit Médical"])
    difficulte = st.slider("Difficulté (1-10) :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 20, 5)
    
    st.divider()
    # LE RETOUR DU TOGGLE MODE EXAMEN
    mode_examen = st.toggle("🚨 Activer le Mode Examen", help="Masque les corrections immédiates pour valider à la fin.")

# ==============================================================================
# 5. Espace Principal (Upload)
# ==============================================================================
st.title("🎓 Simulateur de Concours LAS 1")

fichier_upload = st.file_uploader("Charge ton cours (PDF)", type=['pdf'])

if fichier_upload:
    doc_temp = fitz.open(stream=fichier_upload.read(), filetype="pdf")
    total_pages = len(doc_temp)
    doc_temp.close()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        page_deb, page_fin = st.slider("Pages à inclure :", 1, total_pages, (1, min(4, total_pages)))
    
    with col2:
        st.write("") 
        st.write("")
        if st.button("🧠 Générer le Sujet", type="primary", use_container_width=True):
            if not api_key: 
                st.error("⚠️ Clé API manquante.")
            else:
                with st.spinner("Analyse visuelle et textuelle en cours..."):
                    try:
                        imgs = extraire_images_pdf(fichier_upload, page_deb, page_fin)
                        # On sauvegarde les images dans la session pour pouvoir les réafficher dans les QCM
                        st.session_state['images_cours'] = imgs 
                        st.session_state['data'] = generer_donnees(imgs, matiere, difficulte, nombre_qcm)
                        st.session_state['examen_soumis'] = False
                    except Exception as e: 
                        st.error(f"Erreur : {e}")

# ==============================================================================
# 6. Zone d'Examen et Cases à cocher
# ==============================================================================
if 'data' in st.session_state:
    st.divider()
    data = st.session_state['data']
    liste_qcm = data.get('qcm', [])
    images_sauvegardees = st.session_state.get('images_cours', [])
    
    tab1, tab2, tab3 = st.tabs(["📖 Fiche de Révision", "✍️ QCM", "🗂️ Exporter"])

    with tab1:
        st.markdown(f"<div class='synth-box'><h3>📌 L'essentiel</h3><p>{data.get('fiche_synthese', '')}</p></div>", unsafe_allow_html=True)

    with tab2:
        if not st.session_state.get('examen_soumis', False):
            
            for i, q in enumerate(liste_qcm):
                # 1. AFFICHAGE DE LA QUESTION
                st.markdown(f"### Question {i+1} : {q.get('question', '')}")
                
                # 2. AFFICHAGE DE L'IMAGE SI VISUELLE
                index_img = q.get('index_image', -1)
                if index_img >= 0 and index_img < len(images_sauvegardees):
                    st.image(images_sauvegardees[index_img], caption=f"Document de référence (Page {page_deb + index_img})", use_container_width=True)
                elif q.get('type_question') == 'Visuelle':
                    st.info("ℹ️ Cette question se base sur un schéma du cours.")

                # 3. CASES À COCHER (Sur 2 colonnes comme sur ton image)
                st.write("**Cochez la ou les bonnes propositions :**")
                col_gauche, col_droite = st.columns(2)
                
                # Initialisation de la liste des choix de l'utilisateur
                if f"choix_{i}" not in st.session_state:
                    st.session_state[f"choix_{i}"] = []
                
                reponses_cochees = []
                options_list = list(q.get('options', {}).items())
                
                for idx_opt, (lettre, texte) in enumerate(options_list):
                    col = col_gauche if idx_opt % 2 == 0 else col_droite
                    if col.checkbox(f"{lettre}. {texte}", key=f"chk_{i}_{lettre}"):
                        reponses_cochees.append(lettre)
                
                st.session_state[f"choix_{i}"] = reponses_cochees

                # 4. LOGIQUE DES BOUTONS (Entraînement vs Examen)
                if not mode_examen:
                    if st.button(f"Vérifier la question {i+1}", key=f"btn_verif_{i}"):
                        bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                        mes_choix = sorted(reponses_cochees)
                        
                        if mes_choix == bonnes and len(bonnes) > 0:
                            st.success(f"✅ Vrai ! Les bonnes réponses étaient : {', '.join(bonnes)}")
                        else:
                            st.error(f"❌ Faux ! Les bonnes réponses étaient : {', '.join(bonnes)}")
                        
                        st.info(f"**Explication :** {q.get('explication', '')}\n\n**Source :** {q.get('source_cours', '')}")
                
                st.divider()
            
            # BOUTON GLOBAL SI MODE EXAMEN
            if mode_examen:
                if st.button("🏁 Valider ma copie et voir mon score", type="primary", use_container_width=True):
                    st.session_state['examen_soumis'] = True
                    st.rerun()
        
        # AFFICHAGE DU RÉSULTAT GLOBAL (Mode Examen uniquement)
        else:
            st.subheader("📊 Bilan de l'examen")
            score = 0
            
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                
                est_juste = (bonnes == mes_choix)
                if est_juste and len(bonnes) > 0:
                    score += 1
                
                div_class = "correct-box" if est_juste else "error-box"
                statut = "✅ JUSTE" if est_juste else "❌ FAUX"
                
                st.markdown(f"""
                <div class="{div_class}">
                    <strong>Question {i+1} : {statut}</strong><br>
                    <em>{q.get('question', '')}</em>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                c1.write(f"**Tes choix :** {', '.join(mes_choix) if mes_choix else 'Aucune'}")
                c2.write(f"**Corrigé :** {', '.join(bonnes)}")
                
                with st.expander("🔍 Voir l'explication"):
                    st.write(f"**Démonstration :** {q.get('explication', '')}")
                    st.success(f"📍 **Source :** {q.get('source_cours', '')}")
                st.write("<br>", unsafe_allow_html=True)
            
            if len(liste_qcm) > 0:
                st.metric("Ta Note Finale", f"{(score / len(liste_qcm)) * 20:.1f} / 20")
            
            if st.button("🔄 Refaire l'examen"):
                st.session_state['examen_soumis'] = False
                st.rerun()

    with tab3:
        try:
            df_anki = pd.DataFrame({
                "Recto": [q.get("question", "") + " | " + str(q.get("options", {})) for q in liste_qcm],
                "Verso": [f"{q.get('reponses_correctes', '')} | {q.get('explication', '')}" for q in liste_qcm]
            })
            st.download_button("📥 Télécharger CSV", df_anki.to_csv(index=False, sep=";").encode('utf-8'), "flashcards.csv", "text/csv")
        except:
            st.error("Export indisponible.")
