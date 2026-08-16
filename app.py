import streamlit as st
import fitz  # PyMuPDF
import docx
from datetime import datetime
import re
import requests
import base64
import time

# ==============================================================================
# 1. Configuration et Design
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
# 2. Paliers de difficulté (utilisés RÉELLEMENT dans le prompt)
# ==============================================================================
PALIERS_DIFFICULTE = {
    1: "Très facile : questions de définition pure, une seule bonne réponse évidente, distracteurs grossièrement faux.",
    2: "Facile : vocabulaire de base, une seule bonne réponse, distracteurs peu proches sémantiquement.",
    3: "Facile+ : rappel de cours direct, une seule bonne réponse, distracteurs plausibles mais clairement écartables.",
    4: "Intermédiaire- : nécessite de connaître une nuance du cours, 1 bonne réponse, distracteurs proches thématiquement.",
    5: "Intermédiaire : mélange de rappel et de déduction courte, 1 à 2 bonnes réponses possibles, distracteurs crédibles.",
    6: "Intermédiaire+ : déduction clinique courte nécessaire, 1 à 2 bonnes réponses, distracteurs très proches (même famille de pathogènes/symptômes).",
    7: "Difficile- : cas clinique avec plusieurs indices à croiser, souvent 2 bonnes réponses, distracteurs quasi identiques sémantiquement.",
    8: "Difficile : nécessite de croiser plusieurs notions du document, 2 bonnes réponses fréquentes, distracteurs pièges (confusions classiques).",
    9: "Très difficile : détails précis et chiffrés du document (durées, doses, prévalences), 2 à 3 bonnes réponses possibles, distracteurs quasi indiscernables sans une lecture fine.",
    10: "Expert : niveau examen final, exige la mémorisation exacte de détails secondaires du document, jusqu'à 3 bonnes réponses, distracteurs conçus pour piéger une confusion classique entre pathologies proches.",
}

# ==============================================================================
# 3. Utilitaires
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

def extraire_images_pdf(fichier_bytes, page_debut, page_fin):
    doc = fitz.open(stream=fichier_bytes, filetype="pdf")
    images_parts = []
    for i in range(page_debut - 1, min(page_fin, len(doc))):
        # Résolution 1.5x : bon compromis lisibilité manuscrite / poids du payload.
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

# PARSER
def parser_texte_naturel(texte_ia):
    texte_ia = texte_ia.replace('**', '').replace('__', '')
    questions = []
    blocs_rejetes = 0
    blocs = re.split(r'(?i)@DEBUT_QUESTION', texte_ia)

    for bloc in blocs[1:]:
        if not bloc.strip():
            continue
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
                blocs_rejetes += 1
                continue

            bonnes_reponses_list = []
            for i in range(1, 6):
                if re.search(rf'\b{i}\b', rep_text):
                    bonnes_reponses_list.append(choix_list[i - 1])

            if not bonnes_reponses_list:
                for c in choix_list:
                    if c and c.lower()[:20] in rep_text.lower():
                        bonnes_reponses_list.append(c)

            # Si on ne peut vraiment pas identifier la bonne réponse, on rejette
            # la question plutôt que de deviner.
            if not bonnes_reponses_list:
                blocs_rejetes += 1
                continue

            questions.append({
                "type": "QRM",
                "question": amorce,
                "choix": choix_list,
                "bonnes_reponses": bonnes_reponses_list,
                "explication": [exp if exp else "Explication non générée."],
                "indice": "Relis attentivement les mots-clés de chaque proposition.",
                "mnemotechnique": "Concentre-toi sur les termes spécifiques du cours."
            })

        except Exception:
            blocs_rejetes += 1
            continue

    return {"questions": questions, "rejets": blocs_rejetes}

# ==============================================================================
# 4. Moteur IA
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur de médecine vétérinaire, spécialisé EXCLUSIVEMENT en pathologie et biologie infectieuse.
Matière : {matiere} | Difficulté demandée : {difficulte}/10.

CONSIGNE DE DIFFICULTÉ (À RESPECTER STRICTEMENT) :
{description_difficulte}

MISSION (COMPTAGE OBLIGATOIRE) :
Tu dois générer EXACTEMENT {nb_qcm} questions à réponses multiples (QRM). Pas une de moins.
Tu DOIS numéroter chaque balise de début de question (ex: @DEBUT_QUESTION 1/{nb_qcm}, @DEBUT_QUESTION 2/{nb_qcm}...).
C'EST UN ORDRE STRICT : Tu ne dois pas t'arrêter avant d'avoir atteint la question {nb_qcm}/{nb_qcm}.

RÈGLE D'OR (ANTI-HALLUCINATION) :
INTERDICTION ABSOLUE d'utiliser tes propres connaissances générales pour inventer des faits absents du document.
Base-toi EXCLUSIVEMENT sur le contenu des images/notes fournies.

RÈGLE ÉCRITURE MANUSCRITE (PRUDENCE OBLIGATOIRE) :
Les images peuvent contenir de l'écriture manuscrite partiellement illisible. Si un mot, un chiffre ou un terme
clé est ambigu ou illisible sur l'image, NE DEVINE PAS et N'INVENTE PAS une lecture plausible.
Dans ce cas, ignore ce passage et base ta question sur une autre partie du document que tu peux lire avec certitude.
Ne produis JAMAIS une question ou une réponse basée sur une lecture incertaine d'un mot manuscrit.

STYLE OBLIGATOIRE (QUESTIONS COURTES ET DIRECTES) :
- Les questions doivent être courtes et directes (ex: "Temps d'incubation de la pneumonie progressive ovine ?", "Quel parasite provoque de la diarrhée chez le porcelet de 1 à 3 semaines ?").
- LES CHOIX : EXACTEMENT 5 propositions par question. Propositions TRÈS COURTES (1 à 5 mots maximum : nom de maladie, type de cellule, durée, organe, etc.).
- Le nombre de bonnes réponses doit respecter la consigne de difficulté ci-dessus.

RÉPARTITION DES QUESTIONS (50/50 OBLIGATOIRE) :
Génère environ 50% de questions de TYPE 1 et 50% de questions de TYPE 2.

TYPE 1 : CAS CLINIQUE DE DÉDUCTION RAPIDE (SANS DIAGNOSTIC)
- L'AMORCE : Décris une situation clinique très brièvement (espèce, symptômes majeurs) SANS DONNER LE DIAGNOSTIC.
- LES CHOIX : Des noms de maladies, d'agents pathogènes ou d'examens (très courts).

TYPE 2 : PATHOLOGIE/BIOLOGIE DIRECTE (AVEC DIAGNOSTIC CONNU)
- L'AMORCE : Pose une question théorique directe ou cite directement le pathogène/la maladie.
- LES CHOIX : Des mots-clés,
