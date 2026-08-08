import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import docx
from datetime import datetime
import re
import requests
import base64
import time

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
# 2. Utilitaires & Bouclier INCASSABLE
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

# PARSER BLINDÉ
def parser_texte_naturel(texte_ia):
    texte_ia = texte_ia.replace('**', '').replace('__', '')
    questions = []
    blocs = re.split(r'(?i)@DEBUT_QUESTION', texte_ia)
    
    for bloc in blocs[1:]:
        if not bloc.strip(): continue
        try:
            def get_tag_content(pattern, text):
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                return match.group(1).strip() if match else ""

            amorce = get_tag_content(r'@AMORCE\s*:?\s*(.*?)(?=@CHOIX_?\s*1)', bloc)
            c1 = get_tag_content(r'@CHOIX_?\s*1\s*:?\s*(.*?)(?=@CHOIX_?\s*2)', bloc)
            c2 = get_tag_content(r'@CHOIX_?\s*2\s*:?\s*(.*?)(?=@CHOIX_?\s*3)', bloc)
            c3 = get_tag_content(r'@CHOIX_?\s*3\s*:?\s*(.*?)(?=@CHOIX_?\s*4)', bloc)
            c4 = get_tag_content(r'@CHOIX_?\s*4\s*:?\s*(.*?)(?=@CHOIX_?\s*5)', bloc)
            c5 = get_tag_content(r'@CHOIX_?\s*5\s*:?\s*(.*?)(?=@REPONSES?_?CORRECTES?)', bloc)
            
            rep_text = get_tag_content(r'@REPONSES?_?CORRECTES?\s*:?\s*(.*?)(?=@EXPLICATIONS?)', bloc)
            exp = get_tag_content(r'@EXPLICATIONS?\s*:?\s*(.*?)(?=@FIN_QUESTION|$)', bloc)

            def clean_choice(text):
                return re.sub(r'^[-*•\d\.\)]+\s*', '', text).strip()

            amorce = amorce.strip()
            c1, c2, c3, c4, c5 = map(clean_choice, [c1, c2, c3, c4, c5])
            choix_list = [c1, c2, c3, c4, c5]
            
            if not amorce or not c1 or not c5 or not rep_text:
                continue 
                
            bonnes_reponses_list = []
            for i in range(1, 6):
                if str(i) in rep_text:
                    bonnes_reponses_list.append(choix_list[i-1])
                    
            if not bonnes_reponses_list:
                for c in choix_list:
                    if c and c.lower()[:20] in rep_text.lower():
                        bonnes_reponses_list.append(c)
                        
            if not bonnes_reponses_list:
                bonnes_reponses_list = [c1] 
                
            questions.append({
                "type": "QRM",
                "question": amorce,
                "choix": choix_list,
                "bonnes_reponses": bonnes_reponses_list,
                "explication": [exp if exp else "Explication non générée."],
                "indice": "Relis attentivement les détails cliniques ou biologiques de chaque proposition.",
                "mnemotechnique": "Concentre-toi sur les mots-clés majeurs du cours."
            })
            
        except Exception:
            continue
            
    return {"questions": questions}

# ==============================================================================
# 3. Moteur IA (LE SYSTÈME EN BOUCLE AUTOMATIQUE)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur de médecine vétérinaire, spécialisé EXCLUSIVEMENT en pathologie et biologie infectieuse.
Matière : {matiere} | Difficulté : {difficulte}/10.

MISSION :
Tu dois générer EXACTEMENT {nb_qcm} questions à réponses multiples (QRM). 

RÈGLE D'OR (ANTI-HALLUCINATION) : 
INTERDICTION ABSOLUE d'utiliser tes propres connaissances. Base-toi EXCLUSIVEMENT sur les images du document. 

RÉPARTITION 50/50 OBLIGATOIRE :
Génère un mélange de TYPE 1 et TYPE 2. Il y a TOUJOURS 5 choix longs par question.

TYPE 1 : CAS CLINIQUE DE DÉDUCTION (SANS DIAGNOSTIC)
- L'AMORCE : Décris une situation clinique (espèce, symptômes, contexte) SANS DONNER LE DIAGNOSTIC.
- CHOIX : Déductions diagnostiques, théories, examens ou thérapeutiques logiques.

TYPE 2 : PATHOLOGIE/BIOLOGIE (AVEC DIAGNOSTIC CONNU)
- L'AMORCE : Donne directement le diagnostic.
- CHOIX : Phrases très longues, denses et techniques sur la biologie et le cycle de l'agent.

RÈGLE INFORMATIQUE (BALISES STRICTES) :
@DEBUT_QUESTION
@AMORCE
[Ton texte d'introduction]
@CHOIX_1
[Texte détaillé du choix 1]
@CHOIX_2
[Texte détaillé du choix 2]
@CHOIX_3
[Texte détaillé du choix 3]
@CHOIX_4
[Texte détaillé du choix 4]
@CHOIX_5
[Texte détaillé du choix 5]
@REPONSES_CORRECTES
[Numéros des bonnes réponses, ex: 1, 4]
@EXPLICATION
[Ton explication détaillée]
@FIN_QUESTION
"""

def generer_donnees(images_pdf, texte_word, matiere, difficulte, nombre_qcm_cible, api_key, st_progress):
    cle_propre = re.sub(r'[^a-zA-Z0-9_-]', '', api_key)
    url_b64 = "aHR0cHM6Ly9nZW5lcmF0aXZlbGFuZ3VhZ2UuZ29vZ2xlYXBpcy5jb20vdjFiZXRhL21vZGVscy9nZW1pbmktMi41LWZsYXNoOmdlbmVyYXRlQ29udGVudA=="
    url_base = base64.b64decode(url_b64).decode("utf-8")
    
    session = requests.Session()
    session.trust_env = False
    
    questions_accumulees = []
    tentative = 0
    max_tentatives = 10 # Autorise jusqu'à 10 petits allers-retours avec l'IA
    
    # LA BOUCLE MAGIQUE : On force l'IA à travailler jusqu'à atteindre le quota exact
    while len(questions_accumulees) < nombre_qcm_cible and tentative < max_tentatives:
        qcm_manquants = nombre_qcm_cible - len(questions_accumulees)
        
        # On ne lui demande que 3 questions MAXIMUM par requête pour qu'elle ne coupe JAMAIS son texte
        nb_a_demander = min(qcm_manquants, 3) 
        
        st_progress.info(f"⏳ L'IA rédige minutieusement tes questions... ({len(questions_accumulees)} / {nombre_qcm_cible} prêtes)")
        
        prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcm=nb_a_demander)
        
        parts = [{"text": prompt + "\nVoici les pages du cours à analyser :\n"}]
        parts.extend(images_pdf)
        if texte_word:
            parts.append({"text": "\nNOTES SUPPLÉMENTAIRES :\n" + texte_word})
            
        payload = {
            "contents": [{"parts": parts}], 
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]
        }
        
        try:
            rep = session.post(url_base, params={"key": cle_propre}, json=payload)
            if rep.status_code == 200:
                texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
                resultat = parser_texte_naturel(texte_ia)
                
                # On ajoute les nouvelles questions validées à notre panier
                questions_accumulees.extend(resultat["questions"])
        except Exception as e:
            time.sleep(1) # Petite pause en cas de saturation réseau
            pass
            
        tentative += 1
        
    if not questions_accumulees:
        raise Exception("Impossible de générer les questions. Vérifie tes PDF ou réessaie avec une autre page.")
        
    # On renvoie EXACTEMENT le nombre de questions demandées
    return {"questions": questions_accumulees[:nombre_qcm_cible]}

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
        st.warning("⚠️ Astuce : La nouvelle IA travaille par 'petits lots' en arrière-plan pour garantir le quota et la qualité.")
        p_deb, p_fin = st.slider("Pages à analyser :", 1, p_tot, (1, min(5, p_tot)))
        bouton_generer = st.form_submit_button("🚀 Générer le Test", type="primary", use_container_width=True)
        
        if bouton_generer:
            if not api_key: 
                st.error("Clé API manquante ! Renseigne-la dans la barre latérale.")
            else:
                st_progress = st.empty()
                try:
                    images = extraire_images_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    
                    donnees = generer_donnees(images, txt_w, matiere, difficulte, nombre_qcm, api_key, st_progress)
                    
                    st_progress.success("✅ Génération terminée avec succès !")
                    st.session_state['data'] = donnees
                    st.session_state['examen_soumis'] = False
                    st.session_state['reponses_utilisateur'] = {} 
                    time.sleep(1) # Laisse le temps de voir le message de succès
                    st_progress.empty() # Efface le message
                    st.rerun()
                except Exception as e: 
                    st_progress.empty()
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
            question_propre = q.get('question', '')
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
                    with st.expander("💡 Aide de réflexion"): st.info(q.get('indice', 'Pas d indice.'))
                with col_h2:
                    with st.expander("🧠 Mnémotechnique"): st.warning(q.get('mnemotechnique', 'Rien.'))
            
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
