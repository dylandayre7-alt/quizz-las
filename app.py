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
    
    # Nettoyage sécurisé du JSON (réparé pour éviter les erreurs de syntaxe)
    texte_brut = reponse.text.strip()
    
    if texte_brut.startswith("```json"):
        texte_brut = texte_brut[7:]
        
    if texte_brut.startswith("```"):
        texte_brut = texte_brut[3:]
        
    if texte_brut.endswith("```"):
        texte_brut = texte_brut[:-3]
        
    texte_brut = texte_brut.strip()
    
    return json.loads(texte_brut)

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    if api_key: genai.configure(api_key=api_key)
    st.divider()
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 5)
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

# ==============================================================================
# 5. Application Principale
# ==============================================================================
st.title("🎓 Simulateur LAS 1")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Tes fiches (Word) - Optionnel", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Pages à analyser :", 1, p_tot, (1, p_tot))
    
    if st.button("🧠 Lancer la génération", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner(f"Lecture et rédaction de la synthèse des {p_fin - p_deb + 1} pages..."):
                try:
                    texte_cours = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    t_word = lire_word(f_word) if f_word else ""
                    
                    st.session_state['data'] = generer_donnees(texte_cours, t_word, matiere, difficulte, nombre_qcm, mode_examen)
                    st.session_state['examen_soumis'] = False
                except json.JSONDecodeError as e:
                    st.error("⚠️ L'IA a fait une erreur de mise en forme. Clique à nouveau sur 'Lancer la génération' !")
                except Exception as e: 
                    st.error(f"Erreur technique : {e}")

# ==============================================================================
# 6. Affichage Sécurisé
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    liste_qcm = data.get('qcm', [])
    
    t1, t2, t3, t4 = st.tabs(["📖 Fiche", "✍️ QCM", "🗂️ Anki", "📓 Cahier d'Erreurs"])

    with t1: st.markdown(f"<div class='synth-box'><h3>📌 Synthèse</h3>{data.get('fiche_synthese', '')}</div>", unsafe_allow_html=True)

    with t2:
        if not liste_qcm or len(liste_qcm) == 0:
            st.error("⚠️ Oups, une erreur s'est produite lors de la génération. Clique sur 'Lancer la génération' à nouveau.")
        
        elif not st.session_state.get('examen_soumis'):
            if mode_examen: st.warning("🚨 **MODE EXAMEN ACTIF** : Coche tes réponses, puis valide ta copie tout en bas.")
            
            for i, q in enumerate(liste_qcm):
                st.markdown(f"**Question {i+1}** : {q.get('question', '')}")
                opts = list(q.get('options', {}).items())
                cols = st.columns(2)
                if f"choix_{i}" not in st.session_state: st.session_state[f"choix_{i}"] = []
                cochees = []
                for idx, (l, t) in enumerate(opts):
                    target = cols[0] if idx % 2 == 0 else cols[1]
                    if target.checkbox(f"{l}. {t}", key=f"chk_{i}_{l}"): cochees.append(l)
                st.session_state[f"choix_{i}"] = cochees
                
                if not mode_examen:
                    col_aide1, col_aide2 = st.columns(2)
                    with col_aide1:
                        with st.expander("💡 Besoin d'un indice ?"):
                            st.write(f"*{q.get('indice', 'Pas d\'indice disponible.')}*")
                    with col_aide2:
                        with st.expander("🧠 Astuce Mnémotechnique"):
                            st.info(q.get('mnemotechnique', 'Pas d\'astuce disponible.'))

                    if st.button(f"Vérifier Q{i+1}", key=f"v_{i}"):
                        bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                        mes_choix = sorted(cochees)
                        if mes_choix == bonnes and len(bonnes) > 0: st.success("Vrai !")
                        else:
                            st.error(f"Faux ! Rep: {', '.join(bonnes)}")
                            ajouter_erreur_session(matiere, q.get('question', ''), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), q.get('explication', ''))
                        st.success(f"**Correction détaillée :**\n{q.get('explication', '')}")
                st.divider()
            
            texte_bouton_final = "🏁 Valider ma copie et enregistrer mes erreurs" if mode_examen else "✅ Tout corriger et enregistrer mes erreurs"
            if st.button(texte_bouton_final, type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            score = 0
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                juste = (mes_choix == bonnes and len(bonnes) > 0)
                if juste: score += 1
                else: ajouter_erreur_session(matiere, q.get('question', ''), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), q.get('explication', ''))
                
                st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'><strong>Q{i+1} : {'✅' if juste else '❌'}</strong><br>{q.get('question', '')}</div>", unsafe_allow_html=True)
                st.write(f"Ton choix: {', '.join(mes_choix) if mes_choix else 'Aucune'} | Correction: {', '.join(bonnes)}")
                with st.expander("Détails"): 
                    st.write(q.get('explication', ''))
                    st.info(f"**💡 Astuce pour la prochaine fois :** {q.get('mnemotechnique', '')}")

            st.metric("Note", f"{(score/len(liste_qcm))*20:.1f} / 20")
            if st.button("Recommencer un nouveau test"): st.session_state['examen_soumis'] = False; st.rerun()

    with t3:
        try:
            anki_df = pd.DataFrame({"Q": [q.get('question', '') for q in liste_qcm], "R": [f"{q.get('reponses_correctes', '')} | {q.get('explication', '')}" for q in liste_qcm]})
            st.download_button("📥 Anki CSV", anki_df.to_csv(index=False, sep=";").encode('utf-8'), "anki.csv")
        except: st.error("Export indisponible")

    with t4:
        st.subheader("📓 Mon Cahier d'Erreurs de la Session")
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: st.info("Aucune erreur enregistrée pour le moment.")
        else:
            texte_word = ""
            for mat, errs in mem.items():
                texte_word += f"--- MATIÈRE : {mat} ---\n"
                for e in errs:
                    texte_word += f"Date: {e['date']}\nQ: {e['question']}\nMon erreur: {e['choix_user']}\nBonne rep: {e['bonnes_rep']}\nExplication: {e['explication']}\n\n"
            
            st.download_button("📝 Télécharger pour coller dans Word", texte_word, "mes_erreurs.txt")
            
            for mat, errs in mem.items():
                with st.expander(f"Matière : {mat} ({len(errs)} erreurs)"):
                    for e in reversed(errs):
                        st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br><span style='color:red'>Choix: {e['choix_user']}</span> | <span style='color:green'>Rep: {e['bonnes_rep']}</span><br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
