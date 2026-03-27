import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
import json
import pandas as pd
import docx
import os
from datetime import datetime
import re

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
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
    .erreur-log strong { color: #ffffff; }
    .concept-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #007bff; margin-bottom: 10px; color: #333; }
    .concept-card strong { color: #007bff; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & Mémoire
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur_session(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    for err in st.session_state['cahier_memoire'][matiere]:
        if err['question'] == question: return
    st.session_state['cahier_memoire'][matiere].append({
        "date": datetime.now().strftime("%d/%m/%Y"), "question": question,
        "choix_user": choix_user, "bonnes_rep": bonnes_rep, "explication": explication
    })

def nettoyer_json(texte):
    t = texte.strip()
    t = re.sub(r'^```[a-zA-Z]*\n', '', t)
    t = re.sub(r'^```', '', t)
    t = re.sub(r'\n```$', '', t)
    t = re.sub(r'```$', '', t)
    return t.strip()

def assembler_texte(champ):
    if isinstance(champ, list): 
        return '\n\n'.join([str(c) for c in champ])
    return str(champ)

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

# ==============================================================================
# 3. Moteur IA (Système Auto-Pilote)
# ==============================================================================

# Le Radar : Cherche le modèle qui marche sur ton compte
def trouver_bon_moteur():
    try:
        # Liste tous les modèles autorisés par ta clé API
        modeles_dispos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Ordre de préférence (du plus généreux au plus vieux)
        preferences = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-8b', 'models/gemini-1.5-pro', 'models/gemini-pro']
        
        for pref in preferences:
            if pref in modeles_dispos:
                return pref.replace('models/', '')
        
        # Secours absolu : prend le premier modèle texte disponible
        for m in modeles_dispos:
            if 'vision' not in m and 'embedding' not in m:
                return m.replace('models/', '')
                
        return 'gemini-1.5-flash' # Fallback par défaut
    except:
        return 'gemini-1.5-flash'

PROMPT_COURS = """
Tu es un Professeur expert en LAS 1. Matière : {matiere}. NOTES DE L'ÉTUDIANT : "{notes_etudiant}"
⚠️ RÈGLE INFORMATIQUE CRITIQUE : N'utilise JAMAIS de guillemets doubles (") (utilise '). NE FAIS JAMAIS DE RETOURS À LA LIGNE DANS LE JSON. Pour "fiche_synthese", tu DOIS fournir une LISTE (Array).
MISSION 1 :
1. SYNTHÈSE : Fais un résumé global (liste de paragraphes).
2. CONCEPTS CLÉS : Vise entre 10 et 15 concepts max. (1 phrase par clé).
FORMAT JSON STRICT :
{{
  "fiche_synthese": ["### Titre", "Paragraphe 1..."],
  "concepts_cles": [{{"nom": "Nom...", "role": "Rôle...", "objectif": "But...", "avec_quoi": "Interactions...", "comment": "Fonctionnement..."}}]
}}
"""

PROMPT_QCM = """
Tu es un Professeur expert en LAS 1. Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre QCM : {nombre_qcm} | STYLE : {style_question}
⚠️ RÈGLE INFORMATIQUE CRITIQUE : N'utilise JAMAIS de guillemets doubles (") (utilise '). NE FAIS JAMAIS DE RETOURS À LA LIGNE. L'explication DOIT être une LISTE (Array).
MISSION 2 : Génère EXACTEMENT {nombre_qcm} questions complexes. Pour l'explication, liste chaque proposition avec VRAI ou FAUX.
FORMAT JSON STRICT :
{{
  "qcm": [
    {{
      "type_question": "Conceptuelle", "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": ["**A) VRAI** : explication...", "**B) FAUX** : explication..."],
      "source_cours": "Source...", "indice": "Indice...", "mnemotechnique": "Astuce..."
    }}
  ]
}}
"""

def generer_cours_complet(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen):
    notes = texte_word if texte_word else 'Aucune note.'
    style = 'Style ANNALES (Très Difficile, prop E).' if est_mode_examen else 'Style APPRENTISSAGE.'
    contenu_requete = f'TEXTE À ANALYSER :\n{texte_pdf}'
    
    # Appel de la fonction Radar pour trouver le modèle qui ne fera pas d'erreur 404
    nom_moteur = trouver_bon_moteur()
    model = genai.GenerativeModel(nom_moteur)
    config = {'response_mime_type': 'application/json', 'temperature': 0.4}

    # APPEL 1
    prompt_c = PROMPT_COURS.format(matiere=matiere, notes_etudiant=notes)
    rep_cours = model.generate_content([prompt_c, contenu_requete], generation_config=config)
    json_cours = json.loads(nettoyer_json(rep_cours.text), strict=False)

    # APPEL 2
    prompt_q = PROMPT_QCM.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm, style_question=style)
    rep_qcm = model.generate_content([prompt_q, contenu_requete], generation_config=config)
    json_qcm = json.loads(nettoyer_json(rep_qcm.text), strict=False)

    donnees_finales = {
        "fiche_synthese": json_cours.get("fiche_synthese", []),
        "concepts_cles": json_cours.get("concepts_cles", []),
        "qcm": json_qcm.get("qcm", []),
        "moteur_utilise": nom_moteur # On sauvegarde le nom pour te l'afficher si besoin
    }
    return donnees_finales

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
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 10)
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
    
    if st.button("🚀 Lancer la génération", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Clé API manquante !")
        else:
            texte_cours = extraire_texte_pdf(f_pdf, p_deb, p_fin)
            t_word = lire_word(f_word) if f_word else ""
            
            bar = st.progress(0, text="Connexion aux serveurs de Google et choix du meilleur moteur...")
            
            try:
                donnees_fusionnees = generer_cours_complet(texte_cours, t_word, matiere, difficulte, nombre_qcm, mode_examen)
                bar.progress(100, text=f"Terminé ! (Moteur utilisé : {donnees_fusionnees.get('moteur_utilise')}) ✅")
                
                st.session_state['data'] = donnees_fusionnees
                st.session_state['examen_soumis'] = False
                st.rerun()

            except json.JSONDecodeError as json_err:
                st.error("⚠️ Format corrompu par l'IA. Essaye de relancer.")
            except Exception as e: 
                st.error(f"Erreur d'API : {e}")

# ==============================================================================
# 6. Affichage Normal
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    liste_qcm = data.get('qcm', [])
    liste_concepts = data.get('concepts_cles', [])
    
    t1, t2, t3, t4, t5 = st.tabs(["📖 Fiche", "🎯 Concepts Clés", "✍️ QCM", "🗂️ Anki", "📓 Cahier d'Erreurs"])

    with t1: 
        texte_synthese_propre = assembler_texte(data.get('fiche_synthese', ''))
        st.markdown(f"<div class='synth-box'><h3>📌 Synthèse</h3>{texte_synthese_propre}</div>", unsafe_allow_html=True)

    with t2:
        st.subheader(f"🎯 Les {len(liste_concepts)} Concepts Clés de ce cours")
        if not liste_concepts:
            st.info("Aucun concept clé n'a été détecté.")
        else:
            for concept in liste_concepts:
                with st.expander(f"🧩 {concept.get('nom', 'Concept inconnu')}", expanded=False):
                    st.markdown(f"""
                    <div class='concept-card'>
                        <strong>🛠️ Rôle :</strong> {concept.get('role', '')}<br><br>
                        <strong>🎯 Objectif :</strong> {concept.get('objectif', '')}<br><br>
                        <strong>🤝 Avec quoi :</strong> {concept.get('avec_quoi', '')}<br><br>
                        <strong>⚙️ Comment :</strong> {concept.get('comment', '')}
                    </div>
                    """, unsafe_allow_html=True)

    with t3:
        if not liste_qcm or len(liste_qcm) == 0:
            st.warning("Aucun QCM n'a pu être généré.")
        
        elif not st.session_state.get('examen_soumis'):
            if mode_examen: st.warning("🚨 **MODE EXAMEN ACTIF**")
            
            for i, q in enumerate(liste_qcm):
                st.markdown(f"**Question {i+1}** : {q.get('question', '')}", unsafe_allow_html=True)
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
                            st.write(f"*{q.get('indice', 'Pas d indice')}*", unsafe_allow_html=True)
                    with col_aide2:
                        with st.expander("🧠 Astuce Mnémotechnique"):
                            st.info(q.get('mnemotechnique', 'Pas d astuce'))

                    if st.button(f"Vérifier Q{i+1}", key=f"v_{i}"):
                        bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                        mes_choix = sorted(cochees)
                        texte_explication = assembler_texte(q.get('explication', ''))
                        
                        if mes_choix == bonnes and len(bonnes) > 0: st.success("Vrai !")
                        else:
                            st.error(f"Faux ! Rep: {', '.join(bonnes)}")
                            ajouter_erreur_session(matiere, q.get('question', ''), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), texte_explication)
                        st.success("**Correction :**")
                        st.markdown(texte_explication, unsafe_allow_html=True)
                st.divider()
            
            if st.button("Valider ma copie", type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            score = 0
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                texte_explication = assembler_texte(q.get('explication', ''))
                juste = (mes_choix == bonnes and len(bonnes) > 0)
                
                if juste: score += 1
                else: ajouter_erreur_session(matiere, q.get('question', ''), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), texte_explication)
                
                st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'><strong>Q{i+1} : {'✅' if juste else '❌'}</strong><br>{q.get('question', '')}</div>", unsafe_allow_html=True)
                st.write(f"Ton choix: {', '.join(mes_choix) if mes_choix else 'Aucune'} | Correction: {', '.join(bonnes)}")
                with st.expander("Détails"): 
                    st.markdown(texte_explication, unsafe_allow_html=True)

            st.metric("Note Finale", f"{(score/len(liste_qcm))*20:.1f} / 20")
            if st.button("Recommencer"): st.session_state['examen_soumis'] = False; st.rerun()

    with t4:
        try:
            anki_df = pd.DataFrame({"Q": [q.get('question', '') for q in liste_qcm], "R": [f"{q.get('reponses_correctes', '')} | {assembler_texte(q.get('explication', '')).replace(chr(10), ' ')}" for q in liste_qcm]})
            st.download_button("📥 Anki CSV", anki_df.to_csv(index=False, sep=";").encode('utf-8'), "anki.csv")
        except: st.error("Export indisponible")

    with t5:
        st.subheader("📓 Mon Cahier d'Erreurs de la Session")
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: st.info("Aucune erreur enregistrée pour le moment.")
        else:
            texte_word = ""
            for mat, errs in mem.items():
                texte_word += f"--- MATIÈRE : {mat} ---\n"
                for e in errs:
                    explication_propre = str(e['explication']).replace('\n', ' ')
                    texte_word += f"Date: {e['date']}\nQ: {e['question']}\nMon erreur: {e['choix_user']}\nBonne rep: {e['bonnes_rep']}\nExplication:\n{explication_propre}\n\n"
            
            st.download_button("📝 Télécharger pour coller dans Word", texte_word, "mes_erreurs.txt")
