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
st.set_page_config(page_title="Masterclass Veterinaire", page_icon="🐾", layout="wide")

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
# 2. Paliers de difficulte (n'affectent JAMAIS le nombre de bonnes reponses,
#    uniquement la finesse du detail exige et la proximite des distracteurs)
# ==============================================================================
PALIERS_DIFFICULTE = {
    1: "Tres facile : rappel de definition pure, distracteurs grossierement faux et faciles a ecarter.",
    2: "Facile : vocabulaire de base du document, distracteurs peu proches semantiquement.",
    3: "Facile+ : rappel de cours direct, distracteurs plausibles mais clairement ecartables a la lecture.",
    4: "Intermediaire- : necessite de connaitre une nuance du cours, distracteurs proches thematiquement.",
    5: "Intermediaire : melange de rappel et de deduction courte, distracteurs credibles.",
    6: "Intermediaire+ : deduction clinique courte necessaire, distracteurs tres proches (meme famille de pathogenes/symptomes).",
    7: "Difficile- : cas clinique avec plusieurs indices a croiser, distracteurs quasi identiques semantiquement.",
    8: "Difficile : necessite de croiser plusieurs notions du document, distracteurs pieges (confusions classiques).",
    9: "Tres difficile : details precis et chiffres du document (durees, doses, prevalences), distracteurs quasi indiscernables sans une lecture fine.",
    10: "Expert : niveau examen final, exige la memorisation exacte de details secondaires du document, distracteurs concus pour pieger une confusion classique entre pathologies proches.",
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

            # On rejette uniquement si aucune bonne reponse n'est identifiable.
            # Le nombre de bonnes reponses (1 a 5) est libre et aleatoire, on ne
            # force plus de minimum ni de maximum ici.
            if not bonnes_reponses_list:
                blocs_rejetes += 1
                continue

            questions.append({
                "type": "QRM",
                "question": amorce,
                "choix": choix_list,
                "bonnes_reponses": bonnes_reponses_list,
                "explication": [exp if exp else "Explication non generee."],
                "indice": "Relis attentivement les mots-cles de chaque proposition.",
                "mnemotechnique": "Concentre-toi sur les termes specifiques du cours."
            })

        except Exception:
            blocs_rejetes += 1
            continue

    return {"questions": questions, "rejets": blocs_rejetes}

# ==============================================================================
# 4. Moteur IA
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur de medecine veterinaire, specialise EXCLUSIVEMENT en pathologie et biologie infectieuse.
Matiere : {matiere} | Difficulte demandee : {difficulte}/10.

CONSIGNE DE DIFFICULTE (A RESPECTER STRICTEMENT, N'AFFECTE JAMAIS LE NOMBRE DE BONNES REPONSES) :
{description_difficulte}

REGLE SUR LE NOMBRE DE BONNES REPONSES (ALEATOIRE, INDEPENDANT DE LA DIFFICULTE) :
Pour CHAQUE question, le nombre de bonnes reponses parmi les 5 propositions doit etre choisi de maniere
ALEATOIRE et VARIEE, strictement compris entre 1 et 5 (donc 1, 2, 3 ou 4 bonnes reponses possibles).
Ne repete pas systematiquement le meme nombre de bonnes reponses d'une question a l'autre : varie-le
reellement au fil du questionnaire. Ce nombre ne doit JAMAIS etre determine ou influence par le niveau
de difficulte : la difficulte ne joue que sur la proximite semantique des distracteurs et la finesse du
detail exige dans le document.

MISSION (COMPTAGE OBLIGATOIRE) :
Tu dois generer EXACTEMENT {nb_qcm} questions a reponses multiples (QRM). Pas une de moins.
Tu DOIS numeroter chaque balise de debut de question (ex: @DEBUT_QUESTION 1/{nb_qcm}, @DEBUT_QUESTION 2/{nb_qcm}...).
C'EST UN ORDRE STRICT : Tu ne dois pas t'arreter avant d'avoir atteint la question {nb_qcm}/{nb_qcm}.

REGLE D'OR (ANTI-HALLUCINATION) :
INTERDICTION ABSOLUE d'utiliser tes propres connaissances generales pour inventer des faits absents du document.
Base-toi EXCLUSIVEMENT sur le contenu des images/notes fournies.

REGLE ECRITURE MANUSCRITE (PRUDENCE OBLIGATOIRE) :
Les images peuvent contenir de l'ecriture manuscrite partiellement illisible. Si un mot, un chiffre ou un terme
cle est ambigu ou illisible sur l'image, NE DEVINE PAS et N'INVENTE PAS une lecture plausible.
Dans ce cas, ignore ce passage et base ta question sur une autre partie du document que tu peux lire avec certitude.
Ne produis JAMAIS une question ou une reponse basee sur une lecture incertaine d'un mot manuscrit.

STYLE OBLIGATOIRE (QUESTIONS COURTES ET DIRECTES) :
- Les questions doivent etre courtes et directes (ex: "Temps d'incubation de la pneumonie progressive ovine ?", "Quel parasite provoque de la diarrhee chez le porcelet de 1 a 3 semaines ?").
- LES CHOIX : EXACTEMENT 5 propositions par question. Propositions TRES COURTES (1 a 5 mots maximum : nom de maladie, type de cellule, duree, organe, etc.).
- RAPPEL : varie librement le nombre de bonnes reponses (entre 1 et 4) d'une question a l'autre, sans lien avec la difficulte.

REPARTITION DES QUESTIONS (50/50 OBLIGATOIRE) :
Genere environ 50% de questions de TYPE 1 et 50% de questions de TYPE 2.

TYPE 1 : CAS CLINIQUE DE DEDUCTION RAPIDE (SANS DIAGNOSTIC)
- L'AMORCE : Decris une situation clinique tres brievement (espece, symptomes majeurs) SANS DONNER LE DIAGNOSTIC.
- LES CHOIX : Des noms de maladies, d'agents pathogenes ou d'examens (tres courts).

TYPE 2 : PATHOLOGIE/BIOLOGIE DIRECTE (AVEC DIAGNOSTIC CONNU)
- L'AMORCE : Pose une question theorique directe ou cite directement le pathogene/la maladie.
- LES CHOIX : Des mots-cles, durees, vecteurs, modes de transmission ou termes biologiques tres courts.

REGLE INFORMATIQUE (BALISES STRICTES, NE JAMAIS EN OMETTRE UNE) :
@DEBUT_QUESTION 1/{nb_qcm}
@AMORCE
[Ton texte d'introduction court]
@CHOIX_1
[Choix tres court 1]
@CHOIX_2
[Choix tres court 2]
@CHOIX_3
[Choix tres court 3]
@CHOIX_4
[Choix tres court 4]
@CHOIX_5
[Choix tres court 5]
@REPONSES_CORRECTES
[Numeros des bonnes reponses, ex: 1, 4]
@EXPLICATION
[Ton explication concise]
@FIN_QUESTION
"""

MODELE_PRINCIPAL = "gemini-2.5-flash-lite"
MODELE_FALLBACK = "gemini-2.5-flash"

def construire_url(nom_modele):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{nom_modele}:generateContent"

def appeler_gemini(session, url_base, cle_propre, prompt_text, images_pdf, texte_word):
    parts = [{"text": prompt_text + "\nVoici les pages du cours a analyser :\n"}]
    parts.extend(images_pdf)
    if texte_word:
        parts.append({"text": "\nNOTES SUPPLEMENTAIRES :\n" + texte_word})

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

    rep = session.post(url_base, params={"key": cle_propre}, json=payload, timeout=90)

    if rep.status_code == 429:
        raise RuntimeError("QUOTA_DEPASSE")
    if rep.status_code == 400:
        detail = ""
        try:
            detail = rep.json().get("error", {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError(f"REQUETE_INVALIDE: {detail}")
    if rep.status_code != 200:
        raise RuntimeError(f"ERREUR_HTTP_{rep.status_code}: {rep.text[:200]}")

    data = rep.json()
    candidats = data.get("candidates", [])
    if not candidats:
        raise RuntimeError("REPONSE_VIDE (probablement bloquee par les filtres de securite)")

    return candidats[0]["content"]["parts"][0]["text"]


def generer_donnees(images_pdf, texte_word, matiere, difficulte, nombre_qcm_cible, api_key, st_progress):
    cle_propre = api_key.strip()
    if not cle_propre:
        raise Exception("Cle API vide.")

    session = requests.Session()
    session.trust_env = False

    description_difficulte = PALIERS_DIFFICULTE.get(int(difficulte), PALIERS_DIFFICULTE[5])

    questions_accumulees = []
    total_rejets = 0
    tentative = 0
    max_tentatives = 8
    quota_atteint = False
    modele_courant = MODELE_PRINCIPAL
    bascule_effectuee = False

    while len(questions_accumulees) < nombre_qcm_cible and tentative < max_tentatives:
        qcm_manquants = nombre_qcm_cible - len(questions_accumulees)
        nb_a_demander = min(qcm_manquants, 5)

        st_progress.info(
            f"⏳ Generation via {modele_courant}... ({len(questions_accumulees)}/{nombre_qcm_cible} questions pretes, "
            f"tentative {tentative + 1}/{max_tentatives})"
        )

        prompt = SYSTEM_PROMPT.format(
            matiere=matiere,
            difficulte=difficulte,
            description_difficulte=description_difficulte,
            nb_qcm=nb_a_demander
        )

        url_base = construire_url(modele_courant)

        try:
            texte_ia = appeler_gemini(session, url_base, cle_propre, prompt, images_pdf, texte_word)
            resultat = parser_texte_naturel(texte_ia)
            questions_accumulees.extend(resultat["questions"])
            total_rejets += resultat["rejets"]

        except RuntimeError as e:
            msg = str(e)
            if msg == "QUOTA_DEPASSE":
                quota_atteint = True
                if modele_courant == MODELE_PRINCIPAL and not bascule_effectuee:
                    modele_courant = MODELE_FALLBACK
                    bascule_effectuee = True
                    st_progress.warning(
                        f"⚠️ Quota {MODELE_PRINCIPAL} atteint (429). Bascule automatique sur {MODELE_FALLBACK}..."
                    )
                else:
                    st_progress.warning("⚠️ Quota API atteint (429) sur les deux modeles. Nouvelle tentative dans 20s...")
                    time.sleep(20)
            elif msg.startswith("REQUETE_INVALIDE"):
                if modele_courant == MODELE_PRINCIPAL and not bascule_effectuee:
                    modele_courant = MODELE_FALLBACK
                    bascule_effectuee = True
                    st_progress.warning(f"⚠️ {MODELE_PRINCIPAL} a refuse la requete. Bascule sur {MODELE_FALLBACK}...")
                else:
                    raise Exception(
                        f"Requete refusee par l'API ({msg}). Verifie que ta cle est valide "
                        f"et que le nombre de pages selectionnees n'est pas trop eleve."
                    )
            else:
                time.sleep(3)

        except Exception:
            time.sleep(3)

        tentative += 1

    if not questions_accumulees:
        if quota_atteint:
            raise Exception(
                "Quota API depasse (429) sur flash-lite et flash apres plusieurs tentatives. "
                "Attends quelques minutes ou reduis le nombre de questions/pages demandees."
            )
        raise Exception(
            f"Impossible de generer des questions valides ({total_rejets} blocs rejetes par le parseur). "
            f"Verifie tes pages PDF (texte manuscrit trop illisible ?) ou reessaie."
        )

    if len(questions_accumulees) < nombre_qcm_cible:
        st_progress.warning(
            f"⚠️ Seulement {len(questions_accumulees)}/{nombre_qcm_cible} questions valides generees "
            f"apres {tentative} tentative(s) ({total_rejets} blocs rejetes par le parseur)."
        )
        time.sleep(2)

    return {"questions": questions_accumulees[:nombre_qcm_cible]}

# ==============================================================================
# 5. Interface Graphique
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Cle API Gemini :", type="password")
    matiere = st.selectbox("Matiere :", ["Bacteriologie / Virologie", "Parasitologie / Pathologie", "Gestion de clinique"])
    difficulte = st.slider("Niveau de difficulte :", 1, 10, 5)
    st.caption(f"📋 {PALIERS_DIFFICULTE[difficulte]}")
    st.caption("ℹ️ Le nombre de bonnes reponses (1 a 4 sur 5) est aleatoire pour chaque question, independamment de la difficulte.")
    nombre_qcm = st.number_input("Nombre de Questions :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Mode Examen (Masquer les indices)")
    st.divider()
    st.caption(
        f"💡 Modele principal : **{MODELE_PRINCIPAL}** (quotas gratuits plus larges). "
        f"Bascule automatique sur **{MODELE_FALLBACK}** en cas de quota depasse ou d'erreur. "
        f"Chaque page envoyee (surtout manuscrite) coute ~1100 tokens d'image."
    )

st.title("🐾 Simulateur d'Entrainement Veterinaire (Infectiologie)")
st.caption("📝 Compatible cours manuscrits scannes : les pages sont envoyees en image pour une lecture fidele par l'IA.")

c1, c2 = st.columns(2)
with c1:
    f_pdf = st.file_uploader("1. PDF du cours (Scans/Notes, manuscrit ou imprime)", type=['pdf'])
with c2:
    f_word = st.file_uploader("2. Notes Word (Opt.)", type=['docx'])

if f_pdf:
    pdf_bytes = f_pdf.getvalue()
    doc_t = fitz.open(stream=pdf_bytes, filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()

    with st.form("formulaire_generation"):
        p_deb, p_fin = st.slider("Pages a analyser :", 1, p_tot, (1, min(5, p_tot)))
        nb_pages_selectionnees = p_fin - p_deb + 1
        if nb_pages_selectionnees > 15:
            st.warning(
                f"⚠️ {nb_pages_selectionnees} pages selectionnees : cela consomme beaucoup de tokens "
                f"(surtout si ecriture manuscrite) et peut declencher le quota plus vite. "
                f"5 a 10 pages est un bon compromis."
            )
        bouton_generer = st.form_submit_button("🚀 Generer le Test", type="primary", use_container_width=True)

        if bouton_generer:
            if not api_key:
                st.error("Cle API manquante ! Renseigne-la dans la barre laterale.")
            else:
                st_progress = st.empty()
                try:
                    images = extraire_images_pdf(pdf_bytes, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""

                    donnees = generer_donnees(images, txt_w, matiere, difficulte, nombre_qcm, api_key, st_progress)

                    st_progress.success(f"✅ Generation terminee : {len(donnees['questions'])} questions pretes !")
                    st.session_state['data'] = donnees
                    st.session_state['examen_soumis'] = False
                    st.session_state['reponses_utilisateur'] = {}
                    time.sleep(1.2)
                    st_progress.empty()
                    st.rerun()
                except Exception as e:
                    st_progress.empty()
                    st.error(f"❌ {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Entrainement", "📓 Cahier d'Erreurs"])

    with t1:
        liste_questions = data.get('questions', [])
        is_disabled = st.session_state.get('examen_soumis', False)

        if 'reponses_utilisateur' not in st.session_state:
            st.session_state['reponses_utilisateur'] = {}

        for i, q in enumerate(liste_questions):
            question_propre = q.get('question', '')
            st.markdown(f"**Question {i+1}** 🔹 {question_propre}")
            st.caption("*Le nombre de bonnes reponses varie a chaque question.*")

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
                    with st.expander("💡 Aide de reflexion"):
                        st.info(q.get('indice', "Pas d'indice."))
                with col_h2:
                    with st.expander("🧠 Mnemotechnique"):
                        st.warning(q.get('mnemotechnique', 'Rien.'))

            if is_disabled:
                reponse_soumise = set(st.session_state['reponses_utilisateur'].get(f"q_{i}", []))
                bonnes_reps = set(q.get('bonnes_reponses', []))

                if reponse_soumise == bonnes_reps and len(bonnes_reps) > 0:
                    st.markdown("<div class='correct-box'>✅ <b>Parfait !</b></div>", unsafe_allow_html=True)
                else:
                    rep_str = "Aucune" if not reponse_soumise else " | ".join(reponse_soumise)
                    bonnes_str = " | ".join(bonnes_reps)
                    st.markdown(
                        f"<div class='error-box'>❌ <b>Incomplet ou faux.</b><br>Tes choix : {rep_str}<br>"
                        f"<b>Reponses attendues : {bonnes_str}</b></div>",
                        unsafe_allow_html=True
                    )
                    ajouter_erreur_session(matiere, question_propre, rep_str, bonnes_str, assembler_texte_html(q.get('explication')))

                with st.expander("Correction detaillee et Explications"):
                    st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()

        if is_disabled:
            st.info("🎓 **Evaluation terminee.** Tes erreurs ont ete enregistrees dans le cahier.")
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
            st.info("Aucune erreur enregistree.")
        else:
            for mat, errs in mem.items():
                with st.expander(f"{mat} ({len(errs)} erreurs)"):
                    for e in reversed(errs):
                        st.markdown(
                            f"<div class='erreur-log'><strong>{e['question']}</strong><br>"
                            f"Ta selection : {e['choix_user']} <br> <b>Attendu : {e['bonnes_rep']}</b>"
                            f"<br><br><small>{e['explication']}</small></div>",
                            unsafe_allow_html=True
                        )
