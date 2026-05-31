import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
import docx
from datetime import datetime
import re
import requests

# ==============================================================================
# 1. Configuration et Design Premium
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - Masterclass", page_icon="🎓", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; font-weight: bold; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .warning-box { background-color: #856404; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #ffeeba; border: 1px solid #ffeeba;}
    
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & Bouclier de Sauvetage
# ==============================================================================
if 'cahier_memoire' not in st.session_state:
    st.session_state['cahier_memoire'] = {}

def ajouter_erreur_session(matiere, question, choix_user, bonnes_rep, explication):
    if matiere not in st.session_state['cahier_memoire']:
        st.session_state['cahier_memoire'][matiere] = []
    if not any(err['question'] == question for err in st.session_state['cahier_memoire'][matiere]):
        st.session_state['cahier_memoire'][matiere].append({
            "date": datetime.now().strftime("%d/%m/%Y"), "question": question,
            "choix_user": choix_user, "bonnes_rep": bonnes_rep, "explication": explication
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

def sauvetage_json_coupe(texte_ia):
    debut = texte_ia.find('{')
    if debut == -1:
        raise Exception("Google n'a généré aucune donnée. Relance avec moins de pages.")
        
    texte_brut = texte_ia[debut:]
    texte_brut = re.sub(r'```[a-zA-Z]*$', '', texte_brut)
    texte_brut = re.sub(r'```$', '', texte_brut).strip()

    try:
        return json.loads(texte_brut, strict=False)
    except json.JSONDecodeError:
        tentatives_fermeture = ['}', ']}', '"]}', '}]}', '"]}]}']
        for t in tentatives_fermeture:
            try:
                donnees = json.loads(texte_brut + t, strict=False)
                st.toast("🛡️ Le code a été automatiquement réparé (Coupure de fin).", icon="🛡️")
                return donnees
            except:
                pass
        
        derniere_accolade = texte_brut.rfind('}')
        if derniere_accolade != -1:
            try:
                donnees = json.loads(texte_brut[:derniere_accolade+1] + ']}', strict=False)
                st.toast("🛡️ La fin a été coupée (trop long), mais le début est sauvé.", icon="🛡️")
                return donnees
            except:
                pass
                
        raise Exception("Le document a saturé la mémoire de l'IA. Baisse le nombre de pages.")

# ==============================================================================
# 3. Moteur IA (Une seule passe, stable)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1.
Matière : {matiere} | Difficulté : {difficulte}/10 
Tu dois générer EXACTEMENT {nb_qcu} QCU (Choix Unique) et EXACTEMENT {nb_ouverte} Questions Ouvertes.

RÈGLES DE FORMATAGE :
1. Réponds UNIQUEMENT avec un objet JSON valide.
2. Utilise UNIQUEMENT des apostrophes simples ('), AUCUN guillemet double (") dans les phrases.
3. Aucun HTML dans les champs "question" et "options".

FORMAT JSON STRICT :
{{
  "questions": [
    {{
      "type": "QCU",
      "question": "Texte brut de la question",
      "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D", "E": "Option E"}},
      "reponse_correcte": "A", 
      "explication": ["<strong>A) VRAI</strong> : ...", "<strong>B) FAUX</strong> : ..."], 
      "indice": "Indice...", "mnemotechnique": "Astuce mémo..."
    }},
    {{
      "type": "OUVERTE",
      "question": "Texte de la question ouverte",
      "reponse_attendue": "Réponse type attendue",
      "mots_cles": ["mot1", "mot2", "mot3"],
      "explication": ["Rappel physiologique..."],
      "indice": "Piste de réflexion...", "mnemotechnique": "Moyen mnémotechnique..."
    }}
  ]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    nb_qcu = max(1, round(nombre_qcm * 0.8))
    nb_ouverte = max(1, nombre_qcm - nb_qcu)
    
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte)
    
    # Sécurité anti-espace pour la clé API
    cle_propre = api_key.strip()
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){cle_propre}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt + "\\nCOURS :\\n" + texte_pdf + "\\nNOTES :\\n" + texte_word}]}], 
        "generationConfig": {
            "temperature": 0.2, 
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    rep = requests.post(url, json=payload)
    if rep.status_code != 200: 
        raise Exception(f"Erreur API Google ({rep.status_code}) : Vérifiez votre clé ou votre connexion.")
    
    texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
    return sauvetage_json_coupe(texte_ia)

# ==============================================================================
# 4. Interface Graphique
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions (80% QCU / 20% Rédaction) :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

st.title("🎓 Simulateur LAS 1 (Version Stable Classique)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    st.info("💡 Méthode Classique : Analyse par tranches (5 à 10 pages maximum) recommandée.")
    p_deb, p_fin = st.slider("Pages :", 1, p_tot, (1, min(10, p_tot)))
    
    if st.button("🚀 Générer l'évaluation", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner("Analyse approfondie en cours..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: st.error(f"❌ {e}")

# ==============================================================================
# 5. Affichage des Questions & Corrections Inline
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Entraînement", "📓 Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)
        
        for i, q in enumerate(liste_questions):
            type_q = q.get('type', 'QCU')
            question_propre = nettoyer_question(q.get('question', ''))
            
            st.markdown(f"**Question {i+1}** 🔹 *{type_q}* : {question_propre}")
            
            if type_q == "QCU":
                opts = q.get('options', {})
                choix = st.radio(
                    "Choisis la bonne proposition :", 
                    options=list(opts.keys()), 
                    format_func=lambda x: f"{x}. {nettoyer_question(opts.get(x, ''))}",
                    index=None,
                    key=f"qcu_{i}",
                    disabled=is_disabled
                )
            
            elif type_q == "OUVERTE":
                reponse_ouverte = st.text_area("✍️ Rédige ta réponse complète :", key=f"ouv_{i}", height=120, disabled=is_disabled)
            
            if not is_disabled and not mode_examen:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    with st.expander("💡 Aide"): st.info(nettoyer_question(q.get('indice', 'Pas d indice.')))
                with col_h2:
                    with st.expander("🧠 Mnémotechnique"): st.warning(nettoyer_question(q.get('mnemotechnique', 'Rien.')))
            
            if is_disabled:
                if type_q == "QCU":
                    bonne_rep = q.get('reponse_correcte', '')
                    choix_str = choix if choix else "Blanc"
                    juste = (choix == bonne_rep and choix is not None)
                    
                    if juste:
                        st.markdown(f"<div class='correct-box'>✅ <b>VRAI !</b> La réponse est bien {bonne_rep}.</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='error-box'>❌ <b>FAUX !</b> Tu as mis {choix_str}. La bonne réponse est {bonne_rep}.</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, str(choix_str), bonne_rep, assembler_texte_html(q.get('explication')))
                    
                    with st.expander("Explication complète"): st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
                
                elif type_q == "OUVERTE":
                    mots_cles = q.get('mots_cles', [])
                    rep_str = str(reponse_ouverte) if reponse_ouverte else ""
                    mots_trouves = [mot for mot in mots_cles if mot.lower() in rep_str.lower()]
                    ratio = len(mots_trouves) / max(1, len(mots_cles))
                    
                    if ratio >= 0.5:
                        st.markdown(f"<div class='correct-box'>✅ <b>Réflexion globale bonne</b> ({len(mots_trouves)}/{len(mots_cles)} mots clés).</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='warning-box'>⚠️ <b>Incomplet</b> ({len(mots_trouves)}/{len(mots_cles)} mots clés).</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, rep_str[:50]+"...", ", ".join(mots_cles), assembler_texte_html(q.get('explication')))

                    st.markdown(f"**Mots-clés attendus :** {', '.join(mots_cles)}")
                    with st.expander("Correction Type"): 
                        st.success(f"**Attendu :**<br>{nettoyer_question(q.get('reponse_attendue'))}")
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()
            
        if not is_disabled:
            if st.button("🏁 Valider ma copie", type="primary", use_container_width=True): 
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            if st.button("Nouveau test", use_container_width=True): 
                st.session_state['examen_soumis'] = False
                st.rerun()

    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: st.info("Aucune erreur.")
        for mat, errs in mem.items():
            with st.expander(f"{mat} ({len(errs)} erreurs)"):
                for e in reversed(errs):
                    st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Toi : {e['choix_user']} | Attendu : {e['bonnes_rep']}<br><br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
