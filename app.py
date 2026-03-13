import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
import json
import pandas as pd
import docx

# ==============================================================================
# 1. Configuration de la page et Design
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - IA Premium", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    .synth-box { 
        padding: 25px; background-color: #000000; color: #ffffff; 
        border-left: 8px solid #ff4b4b; border-radius: 10px; margin-bottom: 25px; line-height: 1.6;
    }
    .synth-box h3, .synth-box h4, .synth-box p, .synth-box li { color: #ffffff !important; }
    .correct-box { background-color: #d4edda; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #c3e6cb; color: #155724; }
    .error-box { background-color: #f8d7da; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #f5c6cb; color: #721c24; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Le Prompt Maître (Adaptation dynamique du style de question)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université intraitable, expert en rédaction de sujets LAS 1 / PASS. 

OBJECTIF : 
1. Rédiger une fiche de synthèse.
2. Générer des QCM.
3. Fournir une correction ultra-détaillée.

Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre : {nombre_qcm}

STYLE DES QUESTIONS À UTILISER :
{style_question}

RÈGLES COMMUNES :
- Les QCM doivent comporter 5 propositions (A, B, C, D, E).
- Il peut y avoir UNE ou PLUSIEURS réponses correctes.
- Dans l'explication, tu DOIS justifier chaque réponse.

MIXAGE DES SOURCES :
Tu disposes du cours officiel (PDF) et des fiches de l'étudiant : "{notes_etudiant}". Fais un mix équilibré entre les deux.

TU DOIS OBLIGATOIREMENT RÉPONDRE EN JSON STRICT :
{{
  "fiche_synthese": "Résumé structuré.",
  "qcm": [
    {{
      "type_question": "Conceptuelle" ou "Calcul",
      "question": "Énoncé de la question adapté au style demandé.",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": "Détail : A (VRAI) : justification. B (FAUX) : justification...",
      "source_cours": "Préciser la source."
    }}
  ]
}}
"""

# ==============================================================================
# 3. Fonctions de Traitement
# ==============================================================================
def extraire_images_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    images = []
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images

def lire_word(buffer_fichier):
    doc = docx.Document(buffer_fichier)
    return "\n".join([para.text for para in doc.paragraphs])

def generer_donnees(images_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen):
    notes = texte_word if texte_word else "Aucune note personnelle fournie."
    
    # L'IA adapte son comportement selon que le bouton Examen est coché ou non
    if est_mode_examen:
        style = "Style ANNALES DE CONCOURS : Utilise obligatoirement la formulation 'Parmi les propositions suivantes, laquelle (lesquelles) est (sont) exacte(s) ?'. Les propositions doivent être longues, complexes, et la proposition E doit souvent être 'Aucune des propositions ci-dessus n'est exacte'. Piège l'étudiant sur des détails."
    else:
        style = "Style ENTRAÎNEMENT CLASSIQUE : Pose des questions d'apprentissage directes, claires et précises (ex: 'Quel est le rôle de...', 'Où se situe...', 'Calculez...'). Évite absolument la formulation 'Parmi les propositions suivantes...'. L'objectif est d'assimiler le cours simplement."

    prompt_final = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm, notes_etudiant=notes, style_question=style)
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    reponse = model.generate_content(
        [prompt_final] + images_pdf, 
        generation_config={"response_mime_type": "application/json", "temperature": 0.2}
    )
    return json.loads(reponse.text)

# ==============================================================================
# 4. Interface Latérale
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration API")
    api_key = st.text_input("Clé Google Gemini :", type="password")
    if api_key: 
        genai.configure(api_key=api_key)
    
    st.divider()
    st.header("📚 Réglages")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie (Théorie)", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté (1-10) :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 5)
    
    st.divider()
    mode_examen = st.toggle("🚨 Activer le Mode Examen", help="Active le style de questions type 'Annales' et masque les corrections intermédiaires.")

# ==============================================================================
# 5. Espace Principal (Upload)
# ==============================================================================
st.title("🎓 Simulateur de Concours LAS 1")

col_upload1, col_upload2 = st.columns(2)
with col_upload1:
    fichier_pdf = st.file_uploader("1. Cours complet (PDF)", type=['pdf'])
with col_upload2:
    fichier_word = st.file_uploader("2. Tes fiches (Word .docx) - Optionnel", type=['docx'])

if fichier_pdf:
    doc_temp = fitz.open(stream=fichier_pdf.read(), filetype="pdf")
    total_pages = len(doc_temp)
    doc_temp.close()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        page_deb, page_fin = st.slider("Pages du PDF à analyser :", 1, total_pages, (1, min(5, total_pages)))
    
    with col2:
        st.write("") 
        st.write("")
        texte_bouton = "🧠 Générer les Annales (Mode Examen)" if mode_examen else "🧠 Générer l'Entraînement"
        
        if st.button(texte_bouton, type="primary", use_container_width=True):
            if not api_key: 
                st.error("⚠️ Clé API manquante.")
            else:
                with st.spinner("L'IA prépare tes questions..."):
                    try:
                        imgs_pdf = extraire_images_pdf(fichier_pdf, page_deb, page_fin)
                        texte_fiches = lire_word(fichier_word) if fichier_word else ""
                        
                        # On envoie l'état du bouton "mode_examen" à la fonction
                        st.session_state['data'] = generer_donnees(imgs_pdf, texte_fiches, matiere, difficulte, nombre_qcm, mode_examen)
                        st.session_state['examen_soumis'] = False
                    except Exception as e: 
                        st.error(f"Erreur : {e}")

# ==============================================================================
# 6. Zone de QCM
# ==============================================================================
if 'data' in st.session_state:
    st.divider()
    data = st.session_state['data']
    liste_qcm = data.get('qcm', [])
    
    tab1, tab2, tab3 = st.tabs(["📖 Fiche de Révision", "✍️ QCM", "🗂️ Exporter"])

    with tab1:
        st.markdown(f"<div class='synth-box'><h3>📌 L'essentiel</h3><p>{data.get('fiche_synthese', '')}</p></div>", unsafe_allow_html=True)

    with tab2:
        if not st.session_state.get('examen_soumis', False):
            if mode_examen:
                st.warning("🚨 **MODE EXAMEN ACTIF** : Questions type concours. Coche tes réponses, puis valide ta copie tout en bas.")
            else:
                st.info("💡 **MODE ENTRAÎNEMENT ACTIF** : Questions d'apprentissage. Tu peux vérifier la correction sous chaque question, ou tout corriger d'un coup à la fin.")
                
            for i, q in enumerate(liste_qcm):
                st.markdown(f"### Question {i+1} :")
                st.write(f"*{q.get('question', '')}*")

                col_gauche, col_droite = st.columns(2)
                
                if f"choix_{i}" not in st.session_state:
                    st.session_state[f"choix_{i}"] = []
                
                reponses_cochees = []
                options_list = list(q.get('options', {}).items())
                
                for idx_opt, (lettre, texte) in enumerate(options_list):
                    col = col_gauche if idx_opt % 2 == 0 else col_droite
                    if col.checkbox(f"{lettre}. {texte}", key=f"chk_{i}_{lettre}"):
                        reponses_cochees.append(lettre)
                
                st.session_state[f"choix_{i}"] = reponses_cochees

                if not mode_examen:
                    if st.button(f"Vérifier la question {i+1}", key=f"btn_verif_{i}"):
                        bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                        mes_choix = sorted(reponses_cochees)
                        
                        if mes_choix == bonnes and len(bonnes) > 0:
                            st.success(f"✅ Vrai ! Les bonnes réponses : {', '.join(bonnes)}")
                        else:
                            st.error(f"❌ Faux ! Les bonnes réponses : {', '.join(bonnes)}")
                        
                        st.info(f"**Correction détaillée :**\n{q.get('explication', '')}\n\n**Source :** {q.get('source_cours', '')}")
                
                st.divider()
            
            texte_bouton_final = "🏁 Valider ma copie et voir mon score" if mode_examen else "✅ Tout corriger d'un coup et voir mon score"
            if st.button(texte_bouton_final, type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        
        else:
            st.subheader("📊 Bilan")
            score = 0
            
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                
                est_juste = (mes_choix == bonnes)
                if est_juste and len(bonnes) > 0: score += 1
                
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
                
                with st.expander("🔍 Voir la correction détaillée"):
                    st.write(q.get('explication', ''))
                    st.success(f"📍 **Source :** {q.get('source_cours', '')}")
                st.write("<br>", unsafe_allow_html=True)
            
            if len(liste_qcm) > 0:
                st.metric("Ta Note Finale", f"{(score / len(liste_qcm)) * 20:.1f} / 20")
            
            if st.button("🔄 Refaire un nouveau test"):
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
