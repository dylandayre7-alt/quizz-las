import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import docx
from datetime import datetime
import re
import requests
import base64

# ==============================================================================
# 1. Configuration et Design Premium
# ==============================================================================
st.set_page_config(page_title="Masterclass Vétérinaire", page_icon="🐾", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 10px 10px 0 0; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #2e7b32; color: white; font-weight: bold; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .warning-box { background-color: #856404; padding: 15px; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; color: #ffeeba; border: 1px solid #ffeeba;}
    
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & Bouclier INCASSABLE (Fin du JSON)
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

def extraire_images_pdf(buffer_fichier, page_debut, page_fin):
    buffer_fichier.seek(0)
    doc = fitz.open(stream=buffer_fichier.read(), filetype="pdf")
    images_parts = []
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)) 
        img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode("utf-8")
        images_parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": img_b64
            }
        })
    doc.close()
    return images_parts

def lire_word(buffer_fichier):
    doc = docx.Document(buffer_fichier)
    return " ".join([para.text for para in doc.paragraphs])

# NOUVEAU PARSER BLINDÉ CONTRE LES COUPURES
def parser_texte_incassable(texte_ia):
    questions = []
    # On découpe le texte brut à chaque balise @QUESTION
    blocs = texte_ia.split('@QUESTION')
    
    for bloc in blocs[1:]: # On ignore le blabla du début
        try:
            q_dict = {'type': 'QRM', 'indice': 'Aucun indice.', 'mnemotechnique': 'Aucune astuce.'}
            
            # Découpage chirurgical par balise
            q_part = bloc.split('@CHOIX')[0].strip()
            c_part = bloc.split('@CHOIX')[1].split('@REPONSES')[0].strip()
            r_part = bloc.split('@REPONSES')[1].split('@EXPLICATION')[0].strip()
            e_part = bloc.split('@EXPLICATION')[1].strip()
            
            q_dict['question'] = q_part
            
            # Nettoyage des tirets pour les listes
            choix_lignes = c_part.split('\n')
            q_dict['choix'] = [re.sub(r'^[-*]\s*', '', ligne).strip() for ligne in choix_lignes if ligne.strip()]
            
            rep_lignes = r_part.split('\n')
            q_dict['bonnes_reponses'] = [re.sub(r'^[-*]\s*', '', ligne).strip() for ligne in rep_lignes if ligne.strip()]
            
            q_dict['explication'] = [e_part]
            
            # On ajoute la question seulement si elle est bien complète
            if q_dict['question'] and len(q_dict['choix']) >= 2 and len(q_dict['bonnes_reponses']) >= 1:
                questions.append(q_dict)
                
        except Exception:
            # SI L'IA COUPE LE TEXTE ICI, ON L'IGNORE SANS FAIRE PLANTER L'APPLICATION
            continue 
            
    if len(questions) == 0:
        raise Exception("L'IA n'a pas pu lire le document. Vérifie la qualité de l'image ou du PDF.")
        
    return {"questions": questions}

# ==============================================================================
# 3. Moteur IA (Format Texte Brut - Plus aucun JSON)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur de médecine vétérinaire, spécialisé EXCLUSIVEMENT en pathologie et biologie infectieuse.
Matière : {matiere} | Difficulté : {difficulte}/10 (Niveau Concours très exigeant).

MISSION :
Tu dois générer {nb_qcm} questions à réponses multiples (QRM).

RÈGLE D'OR (ANTI-HALLUCINATION) : 
INTERDICTION ABSOLUE d'utiliser tes propres connaissances. Base-toi EXCLUSIVEMENT sur les images du cours manuscrit ou tapé fourni. Si une information n'est pas sur le document, ne pose pas de question dessus.

STYLE DE QUESTION (CALQUÉ SUR LES EXAMENS VÉTÉRINAIRES OFFICIELS) :
1. L'AMORCE : Une phrase introductive directe ou une mise en situation clinique complexe.
2. LES CHOIX : EXACTEMENT 5 propositions de réponses par question.
3. LA DENSITÉ : Des phrases longues, détaillées et très techniques.
4. LES PIÈGES : Il peut y avoir UNE ou PLUSIEURS bonnes réponses exactes.

RÈGLE INFORMATIQUE ABSOLUE (FORMAT TEXTE STRICT) :
TU NE DOIS JAMAIS UTILISER LE FORMAT JSON.
Tu dois formater CHAQUE question EXACTEMENT comme le modèle ci-dessous. N'utilise pas d'accolades. Utilise uniquement ces balises avec l'arobase.

@QUESTION
[Écris ici l'amorce ou la situation clinique]
@CHOIX
- [Choix 1]
- [Choix 2]
- [Choix 3]
- [Choix 4]
- [Choix 5]
@REPONSES
- [Copie ici le texte exact du choix correct]
- [Copie ici le texte exact d'un autre choix correct s'il y en a un]
@EXPLICATION
[Explication détaillée issue du cours]
"""

def generer_donnees(images_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcm=nombre_qcm)
    cle_propre = re.sub(r'[^a-zA-Z0-9_-]', '', api_key)
    
    url_b64 = "aHR0cHM6Ly9nZW5lcmF0aXZlbGFuZ3VhZ2UuZ29vZ2xlYXBpcy5jb20vdjFiZXRhL21vZGVscy9nZW1pbmktMi41LWZsYXNoOmdlbmVyYXRlQ29udGVudA=="
    url_base = base64.b64decode(url_b64).decode("utf-8")
    
    parts = [{"text": prompt + "\nVoici les pages du cours à analyser :\n"}]
    parts.extend(images_pdf)
    if texte_word:
        parts.append({"text": "\nNOTES SUPPLÉMENTAIRES :\n" + texte_word})
        
    payload = {
        "contents": [{"parts": parts}], 
        "generationConfig": {
            "temperature": 0.1, 
            "maxOutputTokens": 8192
            # Fin du mode JSON forcé. L'IA a la liberté d'écrire en texte brut.
        }
    }
    
    session = requests.Session()
    session.trust_env = False
    
    rep = session.post(url_base, params={"key": cle_propre}, json=payload)
    if rep.status_code != 200: raise Exception(f"Erreur API ({rep.status_code}) : {rep.text}")
    
    texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
    return parser_texte_incassable(texte_ia)

# ==============================================================================
# 4. Interface Graphique
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Bactériologie / Virologie", "Parasitologie / Pathologie", "Gestion de clinique"])
    difficulte = st.slider("Niveau de difficulté :", 1, 10, 9)
    nombre_qcm = st.number_input("Nombre de Questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Mode Examen (Masquer les indices)")

st.title("🐾 Simulateur d'Entraînement Vétérinaire (Infectiologie)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours (Scans/Notes)", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    with st.form("formulaire_generation"):
        st.warning("⚠️ Astuce : Analyse des blocs de 3 à 6 pages maximum. Le système est désormais immunisé contre les coupures.")
        p_deb, p_fin = st.slider("Pages à analyser :", 1, p_tot, (1, min(5, p_tot)))
        bouton_generer = st.form_submit_button("🚀 Générer le Test", type="primary", use_container_width=True)
        
        if bouton_generer:
            if not api_key: 
                st.error("Clé API manquante ! Renseigne-la dans la barre latérale.")
            else:
                with st.spinner(f"Génération de tes questions sur fiches d'infectiologie (Anti-Crash Activé)..."):
                    try:
                        images = extraire_images_pdf(f_pdf, p_deb, p_fin)
                        txt_w = lire_word(f_word) if f_word else ""
                        st.session_state['data'] = generer_donnees(images, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                        st.session_state['examen_soumis'] = False
                        st.session_state['reponses_utilisateur'] = {} 
                        st.rerun()
                    except Exception as e: 
                        st.error(f"❌ {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Entraînement", "📓 Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)
        
        if 'reponses_utilisateur' not in st.session_state:
            st.session_state['reponses_utilisateur'] = {}
        
        for i, q in enumerate(liste_questions):
            question_propre = nettoyer_question(q.get('question', ''))
            st.markdown(f"**Question {i+1}** 🔹 {question_propre}")
            st.caption("*Il peut y avoir plusieurs bonnes réponses.*")
            
            choix = q.get('choix', [])
            
            if f"q_{i}" not in st.session_state['reponses_utilisateur']:
                st.session_state['reponses_utilisateur'][f"q_{i}"] = []
                
            reponses_cochees = []
            for j, choix_texte in enumerate(choix):
                coche = st.checkbox(choix_texte, key=f"chk_{i}_{j}", disabled=is_disabled)
                if coche:
                    reponses_cochees.append(choix_texte)
            
            st.session_state['reponses_utilisateur'][f"q_{i}"] = reponses_cochees
            
            if not is_disabled and not mode_examen:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    with st.expander("💡 Aide de réflexion"): st.info(nettoyer_question(q.get('indice', 'Pas d indice.')))
                with col_h2:
                    with st.expander("🧠 Mnémotechnique"): st.warning(nettoyer_question(q.get('mnemotechnique', 'Rien.')))
            
            if is_disabled:
                reponse_soumise = set(st.session_state['reponses_utilisateur'].get(f"q_{i}", []))
                bonnes_reps = set(q.get('bonnes_reponses', []))
                
                if reponse_soumise == bonnes_reps and len(bonnes_reps) > 0:
                    st.markdown(f"<div class='correct-box'>✅ <b>Parfait !</b></div>", unsafe_allow_html=True)
                else:
                    rep_str = "Aucune" if not reponse_soumise else " | ".join(reponse_soumise)
                    bonnes_str = " | ".join(bonnes_reps)
                    st.markdown(f"<div class='error-box'>❌ <b>Incomplet ou faux.</b><br>Tes choix : {rep_str}<br><b>Réponses attendues : {bonnes_str}</b></div>", unsafe_allow_html=True)
                    ajouter_erreur_session(matiere, question_propre, rep_str, bonnes_str, assembler_texte_html(q.get('explication')))
                
                with st.expander("Correction détaillée et Explications"): 
                    st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()
            
        if is_disabled:
            st.info("🎓 **Évaluation terminée.** Tes erreurs ont été enregistrées dans le cahier.")
            if st.button("🔄 Lancer un nouveau test", use_container_width=True): 
                st.session_state['examen_soumis'] = False
                st.session_state['reponses_utilisateur'] = {}
                st.rerun()
        else:
            if st.button("🏁 Corriger le test", type="primary", use_container_width=True): 
                st.session_state['examen_soumis'] = True
                st.rerun()

    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: 
            st.info("Aucune erreur enregistrée.")
        else:
            for mat, errs in mem.items():
                with st.expander(f"{mat} ({len(errs)} erreurs)"):
                    for e in reversed(errs):
                        st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Ta sélection : {e['choix_user']} <br> <b>Attendu : {e['bonnes_rep']}</b><br><br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
