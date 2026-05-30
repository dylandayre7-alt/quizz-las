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
    
    .synth-box { padding: 30px; background-color: #1e1e1e; color: #ffffff; border-left: 8px solid #ff4b4b; border-radius: 15px; margin-bottom: 30px; line-height: 1.8; }
    .synth-box h3 { color: #e74c3c !important; font-weight: bold; font-size: 1.4em; margin-top: 20px; border-bottom: 1px solid #444; padding-bottom: 5px; } 
    .synth-box p, .synth-box li { color: #ffffff !important; font-size: 1.1em; }
    
    .correct-box { background-color: #155724; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #d4edda; border: 1px solid #c3e6cb;}
    .error-box { background-color: #4a1317; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #f8d7da; border: 1px solid #f5c6cb;}
    .warning-box { background-color: #856404; padding: 15px; border-radius: 10px; margin-bottom: 10px; color: #ffeeba; border: 1px solid #ffeeba;}
    
    .erreur-log { border-left: 4px solid #ff4b4b; padding: 15px; margin-bottom: 15px; background-color: #2b2b2b; color: #ffffff; border-radius: 5px; border: 1px solid #444; }
    .concept-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid #007bff; margin-bottom: 10px; color: #333; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. Utilitaires & BOUCLIER ANTI-CRASH
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
    texte = re.sub(r'###\s*(.*?)(<br>|$)', r'<h3>\1</h3>\2', texte)
    texte = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', texte)
    return texte

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
    """ LE BOUCLIER ABSOLU : Si l'IA est coupée par manque de mémoire, cette fonction répare le code en direct """
    texte_propre = texte_ia.strip()
    texte_propre = re.sub(r'^```[a-zA-Z]*\n', '', texte_propre)
    texte_propre = re.sub(r'```$', '', texte_propre).strip()
    
    try:
        # Essai normal
        return json.loads(texte_propre, strict=False)
    except json.JSONDecodeError:
        # L'IA a été coupée ! On active le mode réparation.
        # On ajoute les guillemets et crochets manquants pour fermer la synthèse.
        if texte_propre.count('"') % 2 != 0:
            texte_propre += '"'
            
        tentatives = [']}', '"]}', '}', '}]}', '"]}]}']
        for t in tentatives:
            try:
                donnees_sauvees = json.loads(texte_propre + t, strict=False)
                st.toast("⚠️ Le cours était si massif que l'IA a été coupée à la fin de la synthèse. Le reste a été sauvé avec succès !", icon="🛡️")
                return donnees_sauvees
            except:
                pass
                
        # Si ça plante vraiment (très rare), on coupe à la hache au dernier paragraphe valide
        coupe = texte_propre.rfind('","')
        if coupe != -1:
            try:
                donnees_sauvees = json.loads(texte_propre[:coupe] + '"]}', strict=False)
                st.toast("🛡️ Sauvetage d'urgence activé : La fin de la synthèse a été coupée, mais tes QCM sont sauvés.", icon="🛡️")
                return donnees_sauvees
            except:
                pass
                
        raise Exception("Le document est beaucoup trop dense (plus de 8000 mots générés). Baisse légèrement le nombre de pages.")

# ==============================================================================
# 3. Moteur IA (Format Mixte + Structure Inversée Sécurisée)
# ==============================================================================
SYSTEM_PROMPT = """
Tu es un Professeur expert en LAS 1.
Matière : {matiere} | Difficulté : {difficulte}/10 
Tu dois générer EXACTEMENT {nb_qcu} QCU (Choix Unique) et EXACTEMENT {nb_ouverte} Questions Ouvertes.

RÈGLES DE FORMATAGE (CRITIQUE) :
1. Réponds UNIQUEMENT avec un objet JSON valide.
2. Échappe proprement les guillemets internes ou utilise des guillemets simples (').
3. Utilise le HTML (<h3>, <strong>, <br>). Ne mets pas de Markdown.

MISSION (DANS CET ORDRE PRÉCIS POUR SÉCURISER LA MÉMOIRE) :
1. QUESTIONS MIXTES : Fais-les en premier. 
   - QCU : 5 propositions, UNE SEULE bonne réponse possible.
   - OUVERTE : Question de réflexion, donne la réponse attendue et 3 à 5 mots-clés.
2. CONCEPTS CLÉS : 5 fiches réflexes indispensables.
3. COURS EXHAUSTIF (SYNTHÈSE) : Fais-le EN DERNIER. Retranscris tous les mécanismes. Privilégie les listes à puces pour gagner de la place. Structure avec <h3> et mots vitaux en rouge <span style='color:#ff4b4b'>...</span>.

FORMAT JSON STRICT (RESPECTE L'ORDRE) :
{{
  "questions": [
    {{
      "type": "QCU",
      "question": "...",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "reponse_correcte": "A", 
      "explication": ["<strong>A) VRAI</strong> : ...", "<strong>B) FAUX</strong> : ..."], 
      "indice": "...", "mnemotechnique": "..."
    }},
    {{
      "type": "OUVERTE",
      "question": "...",
      "reponse_attendue": "...",
      "mots_cles": ["mot1", "mot2", "mot3"],
      "explication": ["..."],
      "indice": "...", "mnemotechnique": "..."
    }}
  ],
  "concepts_cles": [{{"nom": "...", "role": "...", "objectif": "...", "avec_quoi": "...", "comment": "..."}}],
  "fiche_synthese": ["<h3>...</h3>", "Explication détaillée..."]
}}
"""

def generer_donnees(texte_pdf, texte_word, matiere, difficulte, nombre_qcm, est_mode_examen, api_key):
    # Calcul du ratio 80% QCU / 20% Ouvertes
    nb_qcu = max(1, round(nombre_qcm * 0.8))
    nb_ouverte = max(1, nombre_qcm - nb_qcu)
    
    prompt = SYSTEM_PROMPT.format(matiere=matiere, difficulte=difficulte, nb_qcu=nb_qcu, nb_ouverte=nb_ouverte)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt + "\nCOURS :\n" + texte_pdf}]}], 
        "generationConfig": {
            "temperature": 0.3, 
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    rep = requests.post(url, json=payload)
    if rep.status_code != 200: raise Exception(f"Erreur Google : {rep.text}")
    
    texte_ia = rep.json()['candidates'][0]['content']['parts'][0]['text']
    
    # On passe le texte brut dans notre bouclier anti-crash
    return sauvetage_json_coupe(texte_ia)

# ==============================================================================
# 4. Interface Sidebar
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Difficulté :", 1, 10, 8)
    nombre_qcm = st.number_input("Nombre de questions au total (80% QCU / 20% Rédaction) :", 1, 30, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Examen")

# ==============================================================================
# 5. Application
# ==============================================================================
st.title("🎓 Simulateur LAS 1 (Anti-Crash 🛡️)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. PDF du cours", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes Word (Opt.)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Générer la session incassable", type="primary", use_container_width=True):
        if not api_key: st.error("Clé API manquante !")
        else:
            with st.spinner("Analyse approfondie en cours (Protection Anti-Crash activée)..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: st.error(f"❌ {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2, t3, t4 = st.tabs(["📖 Fiche Magistrale", "🎯 Concepts Clés", "✍️ Entraînement", "📓 Cahier d'Erreurs"])

    with t1: st.markdown(f"<div class='synth-box'>{assembler_texte_html(data.get('fiche_synthese', ''))}</div>", unsafe_allow_html=True)

    with t2:
        for c in data.get('concepts_cles', []):
            with st.expander(f"🧩 {c.get('nom', 'Concept')}"):
                st.markdown(f"<div class='concept-card'><strong>Rôle:</strong> {c.get('role')}<br><strong>Objectif:</strong> {c.get('objectif')}<br><strong>Comment:</strong> {c.get('comment')}</div>", unsafe_allow_html=True)

    with t3:
        liste_questions = data.get('questions', [])
        
        # --- PHASE DE RÉPONSE ---
        if not st.session_state.get('examen_soumis'):
            for i, q in enumerate(liste_questions):
                type_q = q.get('type', 'QCU')
                st.markdown(f"**Question {i+1}** 🔹 *{type_q}* : {q.get('question')}")
                
                # Interface QCU (Boutons Radio)
                if type_q == "QCU":
                    opts = q.get('options', {})
                    choix = st.radio(
                        "Choisis la bonne proposition :", 
                        options=list(opts.keys()), 
                        format_func=lambda x: f"{x}. {opts[x]}",
                        index=None,
                        key=f"qcu_{i}"
                    )
                    st.session_state[f"choix_{i}"] = choix
                
                # Interface Question Ouverte (Champ de texte)
                elif type_q == "OUVERTE":
                    reponse_ouverte = st.text_area("✍️ Rédige ta réponse complète ici :", key=f"ouv_{i}", height=150)
                    st.session_state[f"choix_{i}"] = reponse_ouverte
                
                if not mode_examen:
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        with st.expander("💡 Aide (Indice)"): st.info(q.get('indice', 'Pas d indice.'))
                    with col_h2:
                        with st.expander("🧠 Mémorisation Active"): st.warning(f"**Point d'ancrage :** {q.get('mnemotechnique', '')}")
                
                st.divider()
            
            texte_btn = "🏁 Valider ma copie" if mode_examen else "✅ Tout corriger"
            if st.button(texte_btn, type="primary", use_container_width=True): 
                st.session_state['examen_soumis'] = True
                st.rerun()
                
        # --- PHASE DE CORRECTION ---
        else:
            score_qcu = 0
            total_qcu = 0
            
            for i, q in enumerate(liste_questions):
                type_q = q.get('type', 'QCU')
                mon_choix = st.session_state.get(f"choix_{i}")
                
                # Correction QCU
                if type_q == "QCU":
                    total_qcu += 1
                    bonne_rep = q.get('reponse_correcte', '')
                    juste = (mon_choix == bonne_rep and mon_choix is not None)
                    
                    if juste: score_qcu += 1
                    else: ajouter_erreur_session(matiere, q.get('question'), str(mon_choix), bonne_rep, assembler_texte_html(q.get('explication')))
                    
                    st.markdown(f"<div class='{'correct-box' if juste else 'error-box'}'><strong>Q{i+1} (QCU) : {'✅ VRAI' if juste else '❌ FAUX'}</strong><br>{q.get('question')}</div>", unsafe_allow_html=True)
                    st.write(f"Ton choix : **{mon_choix if mon_choix else 'Aucune réponse'}** | La bonne réponse était : **{bonne_rep}**")
                    with st.expander("Voir l'explication complète"): st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
                
                # Correction Question Ouverte
                elif type_q == "OUVERTE":
                    mots_cles = q.get('mots_cles', [])
                    reponse_user = str(mon_choix) if mon_choix else ""
                    
                    mots_trouves = [mot for mot in mots_cles if mot.lower() in reponse_user.lower()]
                    ratio_mots = len(mots_trouves) / max(1, len(mots_cles))
                    
                    if ratio_mots >= 0.5:
                        st.markdown(f"<div class='correct-box'><strong>Q{i+1} (Rédaction) : ✅ Bonne réflexion globale</strong><br>{q.get('question')}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='warning-box'><strong>Q{i+1} (Rédaction) : ⚠️ Incomplet ou imprécis</strong><br>{q.get('question')}</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, q.get('question'), reponse_user[:50]+"...", ", ".join(mots_cles), assembler_texte_html(q.get('explication')))

                    st.write(f"**Ta rédaction :** {reponse_user if reponse_user else '*Aucune réponse fournie*'}")
                    st.markdown(f"**Mots-clés attendus :** {', '.join(mots_cles)} *(Tu as trouvé : {len(mots_trouves)}/{len(mots_cles)})*")
                    
                    with st.expander("Voir la correction type du Professeur"): 
                        st.success(f"**Réponse attendue :**<br>{q.get('reponse_attendue')}")
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)

            if total_qcu > 0:
                st.metric("Score sur les QCU", f"{(score_qcu/total_qcu)*20:.1f} / 20")
            else:
                st.metric("Score", "Évaluation basée sur la rédaction")
                
            if st.button("Nouveau test"): st.session_state['examen_soumis'] = False; st.rerun()

    with t4:
        for mat, errs in st.session_state.get('cahier_memoire', {}).items():
            with st.expander(f"{mat} ({len(errs)} erreurs)"):
                for e in reversed(errs):
                    st.markdown(f"<div class='erreur-log'><strong>{e['question']}</strong><br>Toi : {e['choix_user']} | Attendu : {e['bonnes_rep']}<br><br><small>{e['explication']}</small></div>", unsafe_allow_html=True)
