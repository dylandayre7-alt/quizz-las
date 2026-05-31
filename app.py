import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
import docx
from datetime import datetime
import re
import requests

# ==============================================================================
# 1. Configuration et Design Épuré Premium
# ==============================================================================
st.set_page_config(page_title="Prépa LAS 1 - Évaluation Intensive", page_icon="🎓", layout="wide")

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
    texte_propre = texte_ia.strip()
    texte_propre = re.sub(r'^```[a-zA-Z]*\n', '', texte_propre)
    texte_propre = re.sub(r'```$', '', texte_propre).strip()
    
    try:
        return json.loads(texte_propre, strict=False)
    except json.JSONDecodeError:
        if texte_propre.count('"') % 2 != 0:
            texte_propre += '"'
        tentatives = [']}', '}', ']}']
        for t in tentatives:
            try:
                donnees_sauvees = json.loads(texte_propre + t, strict=False)
                st.toast("🛡️ Le JSON a été automatiquement stabilisé par le système.", icon="🛡️")
                return donnees_sauvees
            except:
                pass
        raise Exception("Une erreur de structure est survenue. Relance simplement la génération.")

# ==============================================================================
# 3. Moteur IA (Focalisé 100% sur l'Évaluation)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1. Ton unique but est d'évaluer l'étudiant de manière impitoyable sur le cours fourni.
Matière : {matiere} | Difficulté : {difficulte}/10 
Tu dois générer EXACTEMENT {nb_qcu} QCU (Choix Unique) et EXACTEMENT {nb_ouverte} Questions Ouvertes.

RÈGLES DE FORMATAGE (CRITIQUE) :
1. Réponds EXCLUSIVEMENT avec l'objet JSON demandé. Aucune phrase d'introduction.
2. Échappe proprement les guillemets internes ou utilise des guillemets simples (').
3. N'UTILISE JAMAIS AUCUNE BALISE HTML DANS LES CHAMPS "question" ET "options". Que du texte brut.
4. Utilise le HTML (<strong>, <br>) uniquement dans le champ "explication".

MISSION :
Génère des questions de haute précision sur l'ensemble des notions de l'extrait du cours :
- QCU : 5 propositions (A à E), UNE SEULE bonne réponse possible. Évite les questions trop simples.
- OUVERTE : Question de réflexion rédactionnelle, donne la réponse attendue complète et 3 à 5 mots-clés de notation.

FORMAT JSON STRICT (NE GÉNÈRE RIEN D'AUTRE) :
{{
  "questions": [
    {{
      "type": "QCU",
      "question": "Texte de la question sans aucun HTML",
      "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D", "E": "Option E"}},
      "reponse_correcte": "A", 
      "explication": ["<strong>A) VRAI</strong> : ...", "<strong>B) FAUX</strong> : ..."], 
      "indice": "Indice de décodage...", "mnemotechnique": "Astuce mémo..."
    }},
    {{
      "type": "OUVERTE",
      "question": "Texte de la question ouverte",
      "reponse_attendue": "Réponse type attendue pour avoir tous les points",
      "mots_cles": ["mot1", "mot2", "mot3"],
      "explication": ["Rappel physiologique ou légal lié à la question..."],
      "indice": "Piste de réflexion...", "mnemotechnique": "Moyen mnémotechnique..."
    }}
  ]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    nb_qcu = max(1, round(nombre_qcm * 0.8))
    nb_ouverte = max(1, nombre_qcm - nb_qcu)
    
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt + "\nCOURS EXTENSÉ À TRAITER :\n" + texte_pdf}]}], 
        "generationConfig": {
            "temperature": 0.3, 
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    rep = requests.post(url, json=payload)
    if rep.status_code != 200: raise Exception(f"Erreur Google : {rep.text}")
    
    texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
    return sauvetage_json_coupe(texte_ia)

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions (80% QCU / 20% Rédaction) :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

# ==============================================================================
# 5. Application Principale
# ==============================================================================
st.title("🎓 Entraînement Concours Intensif (Format Allégé Haute Capacité)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours complet", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes complémentaires Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Sélectionner la plage de pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Générer l'évaluation du bloc complet", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner("Extraction globale et ciblage des pièges en cours..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: st.error(f"❌ {e}")

# ==============================================================================
# 6. Affichage des Questions & Corrections
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Entraînement", "📓 Mon Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        
        if not st.session_state.get('examen_soumis'):
            for i, q in enumerate(liste_questions):
                type_q = q.get('type', 'QCU')
                question_propre = nettoyer_question(q.get('question', ''))
                
                st.markdown(f"**Question {i+1}** 🔹 *{type_q}* : {question_propre}", unsafe_allow_html=True)
                
                if type_q == "QCU":
                    opts = q.get('options', {})
                    choix = st.radio(
                        "Coche l'unique proposition exacte :", 
                        options=list(opts.keys()), 
                        format_func=lambda x: f"{x}. {nettoyer_question(opts[x])}",
                        index=None,
                        key=f"qcu_{i}"
                    )
                    st.session_state[f"choix_{i}"] = choix
                
                elif type_q == "OUVERTE":
                    reponse_ouverte = st.text_area("✍️ Saisis ta démonstration / réponse rédigée :", key=f"ouv_{i}", height=120)
                    st.session_state[f"choix_{i}"] = reponse_ouverte
                
                if not mode_examen:
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        with st.expander("💡 Indice de réflexion"): st.info(nettoyer_question(q.get('indice', 'Pas d indice.')))
                    with col_h2:
                        with st.expander("🧠 Point d'ancrage mémo"): st.warning(f"{nettoyer_question(q.get('mnemotechnique', 'Aucune astuce spécifiée.'))}")
                
                st.divider()
            
            texte_btn = "🏁 Soumettre la copie" if mode_examen else "✅ Valider mes réponses"
            if st.button(texte_btn, type="primary", use_container_width=True): 
                st.session_state['examen_soumis'] = True
                st.rerun()
                
        else:
            score_qcu = 0
            total_qcu = 0
            
            for i, q in enumerate(liste_questions):
                type_q = q.get('type', 'QCU')
                mon_choix = st.session_state.get(f"choix_{i}")
                question_propre = nettoyer_question(q.get('question', ''))
                
                if type_q == "QCU":
                    total_qcu += 1
                    bonne_rep = q.get('reponse_correcte', '')
                    juste = (mon_choix == bonne_rep and mon_choix is not None)
                    
                    if juste: score_qcu += 1
                    else: ajouter_erreur_session(matiere, question_propre, str(mon_choix), bonne_rep, assembler_texte_html(q.get('explication')))
                    
                    st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'><strong>Q{i+1} (QCU) : {'✅ CORRECT' if juste else '❌ ERREUR'}</strong><br>{question_propre}</div>", unsafe_allow_html=True)
                    st.write(f"Ton choix : **{mon_choix if mon_choix else 'Blanc'}** | Réponse attendue : **{bonne_rep}**")
                    with st.expander("Analyse des propositions"): st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
                
                elif type_q == "OUVERTE":
                    mots_cles = q.get('mots_cles', [])
                    reponse_user = str(mon_choix) if mon_choix else ""
                    mots_trouves = [mot for mot in mots_cles if mot.lower() in reponse_user.lower()]
                    ratio_mots = len(mots_trouves) / max(1, len(mots_cles))
                    
                    if ratio_mots >= 0.5:
                        st.markdown(f"<div class='correct-box'><strong>Q{i+1} (Rédaction) : ✅ Cohérence sémantique validée</strong><br>{question_propre}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='warning-box'><strong>Q{i+1} (Rédaction) : ⚠️ Restitution incomplète ou imprécise</strong><br>{question_propre}</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, reponse_user[:50]+"...", ", ".join(mots_cles), assembler_texte_html(q.get('explication')))

                    st.write(f"**Ta production :** {reponse_user if reponse_user else '*Copie blanche*'}")
                    st.markdown(f"**Mots-clés requis au concours :** {', '.join(mots_cles)} *(Identifiés dans ta copie : {len(mots_trouves)}/{len(mots_cles)})*")
                    
                    with st.expander("Consulter la grille de correction officielle"): 
                        st.success(f"**Modèle de réponse attendu :**<br>{nettoyer_question(q.get('reponse_attendue'))}")
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)

            if total_qcu > 0: st.metric("Note QCU", f"{(score_qcu/total_qcu)*20:.1f} / 20")
            if st.button("Lancer une nouvelle évaluation"): st.session_state['examen_soumis'] = False; st.rerun()

    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: st.info("Excellent travail, aucune anomalie enregistrée dans le cahier d'erreurs.")
        for mat, errs in mem.items():
            with st.expander(f"Matière : {mat} ({len(errs)} fautes stockées)"):
                for e in reversed(errs):
                    st.markdown(f"""
                    <div class='erreur-log'>
                        <strong>{e['question']}</strong><br>
                        <span style='color:#ff4b4b'>Saisie étudiant : {e['choix_user']}</span> | 
                        <span style='color:#28a745'>Validé : {e['bonnes_rep']}</span><br>
                        <small>{e['explication']}</small>
                    </div>
                    """, unsafe_allow_html=True)
