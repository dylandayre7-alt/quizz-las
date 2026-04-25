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
    
    /* Design Magistral pour la Fiche Synthèse */
    .synth-box { padding: 30px; background-color: #1e1e1e; color: #ffffff; border-left: 8px solid #ff4b4b; border-radius: 15px; margin-bottom: 30px; line-height: 1.8; }
    .synth-box h1, .synth-box h2 { color: #ff4b4b !important; margin-top: 25px; margin-bottom: 10px; }
    .synth-box h3 { color: #e74c3c !important; font-weight: bold; font-size: 1.3em; margin-top: 15px; } 
    .synth-box p, .synth-box li { color: #ffffff !important; font-size: 1.1em; }
    .synth-box ul { margin-left: 20px; }
    
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
        "date": datetime.now().strftime("%d/%m/%Y"),
        "question": question,
        "choix_user": choix_user,
        "bonnes_rep": bonnes_rep,
        "explication": explication
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
        return '<br><br>'.join([str(c) for c in champ])
    return str(champ)

def extraire_texte_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    texte_complet = ""
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        texte_complet += f" PAGE {i+1} " + doc[i].get_text("text")
    doc.close()
    return texte_complet

def lire_word(buffer_fichier):
    doc = docx.Document(buffer_fichier)
    return " ".join([para.text for para in doc.paragraphs])

# ==============================================================================
# 3. Moteur IA (Gemini 2.5 Flash DIRECT)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur d'Université expert en LAS 1. Ton but est de préparer l'étudiant au concours.
Matière : {matiere} | Difficulté : {difficulte}/10 | Nombre total de QCM : {nombre_qcm}

STYLE : {style_question}
NOTES DE L'ÉTUDIANT : "{notes_etudiant}"

⚠️ RÈGLES INFORMATIQUES CRITIQUES :
1. N'utilise JAMAIS de guillemets doubles (") dans tes textes. Utilise EXCLUSIVEMENT des guillemets simples (').
2. NE FAIS AUCUN RETOUR À LA LIGNE DANS TES VALEURS JSON. Écris tout ton JSON sur une seule ligne géante continue.
3. Pour sauter une ligne visuellement, utilise la balise <br>.

MISSION PÉDAGOGIQUE DE HAUT NIVEAU :
1. SYNTHÈSE MASTERCLASS ET COLORÉE (EXHAUSTIVE) : Rédige un cours complet et magistral. 
   - Utilise une structure hiérarchisée avec des titres (### I. , ### II.).
   - Ne survole aucun point : détaille les mécanismes, les classifications et les définitions précises.
   - Utilise la couleur rouge pour mettre en évidence les notions les plus importantes en utilisant la syntaxe HTML : <span style='color:red'>notion importante</span>.
   - Utilise le gras (**) pour les mots-clés essentiels.

2. CONCEPTS CLÉS (TOP EXAMEN) : Identifie les 5 à 10 concepts, molécules ou lois les plus importants du document. 

3. QCM TYPE CONCOURS : Génère EXACTEMENT {nombre_qcm} questions à choix multiples complexes.
   - Varie IMPÉRATIVEMENT le nombre de bonnes réponses ! Il peut y avoir 1, 2, 3, 4 ou 5 bonnes réponses. 

4. CORRECTION ANALYTIQUE : Sous forme de liste pour chaque proposition (A, B, C, D, E) avec VRAI ou FAUX en gras. N'utilise pas de couleur ici.

FORMAT JSON STRICT (SUR UNE SEULE LIGNE) À RESPECTER :
{{
  "fiche_synthese": [
    "### I. Titre Magistral<br>**Définition :** <span style='color:red'>notion importante</span>...",
    "**Mouvements de <span style='color:red'>Hémi-cytosol</span>** : ..."
  ],
  "concepts_cles": [
    {{
      "nom": "Nom...", "role": "...", "objectif": "...", "avec_quoi": "...", "comment": "..."
    }}
  ],
  "qcm": [
    {{
      "type_question": "Conceptuelle",
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponses_correctes": ["A", "C"],
      "explication": [
        "**A) VRAI** : explication...",
        "**B) FAUX** : explication du piège..."
      ],
      "source_cours": "Source...",
      "indice": "Indice...",
      "mnemotechnique": "Astuce..."
    }}
  ]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    notes = texte_word if texte_word else 'Aucune note.'
    style = 'Style ANNALES (Très Difficile, Piégeux, proposition E : aucune n est exacte).' if est_mode_examen else 'Style APPRENTISSAGE (Direct, clair).'
    
    prompt_final = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nombre_qcm=nombre_qcm, notes_etudiant=notes, style_question=style)
    
    # 🌟 LE MOTEUR 2.5 EST VERROUILLÉ ICI 🌟
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": prompt_final + "\n\nTEXTE DU COURS OFFICIEL À ANALYSER :\n" + texte_pdf}]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json"
        }
    }
    
    try:
        reponse = requests.post(url, headers=headers, json=payload)
    except Exception as e:
        raise Exception(f"Erreur de connexion internet. (Erreur brute: {e})")
    
    if reponse.status_code != 200:
        if reponse.status_code == 429:
            raise Exception(f"Erreur API Google (429) : Ton quota sur le 2.5 est dépassé. Patiente un peu.")
        raise Exception(f"Erreur API Google ({reponse.status_code}) : {reponse.text}")
        
    data_json = reponse.json()
    texte_brut = data_json['candidates'][0]['content']['parts'][0]['text']
    
    texte_nettoye = nettoyer_json(texte_brut)
    return json.loads(texte_nettoye, strict=False)

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    st.divider()
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

# ==============================================================================
# 5. Application Principale
# ==============================================================================
st.title("🎓 Simulateur LAS 1 (Moteur 2.5 Actif)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Tes fiches Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Pages à analyser :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Lancer la génération (Gemini 2.5)", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Clé API manquante !")
        else:
            with st.spinner(f"Analyse avec Gemini 2.5 Flash en cours..."):
                try:
                    texte_cours = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    t_word = lire_word(f_word) if f_word else ""
                    
                    st.session_state['data'] = generer_donnees(texte_cours, t_word, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: 
                    st.error(f"❌ {e}")

# ==============================================================================
# 6. Affichage Sécurisé
# ==============================================================================
if 'data' in st.session_state:
    data = st.session_state['data']
    liste_qcm = data.get('qcm', [])
    liste_concepts = data.get('concepts_cles', [])
    
    t1, t2, t3, t4, t5 = st.tabs(["📖 Fiche Magistrale", "🎯 Concepts Clés", "✍️ QCM", "🗂️ Anki", "📓 Cahier d'Erreurs"])

    with t1: 
        texte_synthese_propre = assembler_texte(data.get('fiche_synthese', 'Synthèse indisponible.'))
        st.markdown(f"<div class='synth-box'>{texte_synthese_propre}</div>", unsafe_allow_html=True)

    with t2:
        st.subheader("🎯 Les Concepts Clés Essentiels")
        if not liste_concepts:
            st.info("Aucun concept clé n'a été détecté dans ce passage.")
        else:
            for concept in liste_concepts:
                with st.expander(f"🧩 {concept.get('nom', 'Concept inconnu')}", expanded=False):
                    st.markdown(f"""
                    <div class='concept-card'>
                        <strong>🛠️ Rôle :</strong> {concept.get('role', '')}<br><br>
                        <strong>🎯 Objectif :</strong> {concept.get('objectif', '')}<br><br>
                        <strong>⚙️ Comment :</strong> {concept.get('comment', '')}
                    </div>
                    """, unsafe_allow_html=True)

    with t3:
        if not liste_qcm or len(liste_qcm) == 0:
            st.warning("Aucun QCM n'a pu être généré. Essaye avec un autre passage de ton cours.")
        
        elif not st.session_state.get('examen_soumis'):
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
                st.divider()
            
            if st.button("Valider ma copie", type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            score = 0
            for i, q in enumerate(liste_qcm):
                bonnes = sorted([str(b).strip() for b in q.get('reponses_correctes', [])])
                mes_choix = sorted(st.session_state.get(f"choix_{i}", []))
                explication_propre = assembler_texte(q.get('explication', ''))
                juste = (mes_choix == bonnes and len(bonnes) > 0)
                
                if juste: score += 1
                else: ajouter_erreur_session(matiere, q.get('question', ''), ", ".join(mes_choix) if mes_choix else "Aucune", ", ".join(bonnes), explication_propre)
                
                st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'><strong>Q{i+1} : {'✅' if juste else '❌'}</strong><br>{q.get('question', '')}</div>", unsafe_allow_html=True)
                st.write(f"Ton choix: {', '.join(mes_choix) if mes_choix else 'Aucune'} | Correction: {', '.join(bonnes)}")
                with st.expander("Détails"): 
                    st.markdown(explication_propre, unsafe_allow_html=True)

            st.metric("Note", f"{(score/len(liste_qcm))*20:.1f} / 20")
            if st.button("Recommencer un nouveau test"): st.session_state['examen_soumis'] = False; st.rerun()

    with t4:
        try:
            anki_df = pd.DataFrame({"Q": [q.get('question', '') for q in liste_qcm], "R": [f"{q.get('reponses_correctes', '')} | {assembler_texte(q.get('explication', '')).replace(chr(10), ' ')}" for q in liste_qcm]})
            st.download_button("📥 Anki CSV", anki_df.to_csv(index=False, sep=";").encode('utf-8'), "anki.csv")
        except: st.error("Export indisponible")

    with t5:
        mem = st.session_state.get('cahier_memoire', {})
        for mat, errs in mem.items():
            with st.expander(f"Matière : {mat} ({len(errs)} erreurs)"):
                for e in reversed(errs):
                    st.markdown(f"""
                    <div class='erreur-log'>
                        <strong>{e['question']}</strong><br>
                        <span style='color:#ff4b4b'>Choix: {e['choix_user']}</span> | 
                        <span style='color:#28a745'>Rep: {e['bonnes_rep']}</span><br>
                        <small>{e['explication']}</small>
                    </div>
                    """, unsafe_allow_html=True)
