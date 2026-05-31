texte_ia = re.sub(r'\n```$', '', texte_ia).strip()
                
                donnees_chunk = json.loads(texte_ia, strict=False)
                all_questions.extend(donnees_chunk.get('questions', []))
            
            elif rep.status_code == 429:
                time.sleep(4) # Pause si Google sature
        except Exception as e:
            st.toast(f"Un bloc de pages a été ignoré suite à une erreur mineure de l'IA.", icon="⚠️")
            pass
            
    barre_progression.empty()
    
    if not all_questions:
        raise Exception("Aucune donnée n'a pu être générée. Vérifie que le PDF n'est pas uniquement composé d'images scannées.")
        
    return {"questions": all_questions[:nombre_qcm]}

# ==============================================================================
# 4. Interface Graphique Streamlit
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API Gemini :", type="password")
    matiere = st.selectbox("Matière :", ["Biologie / Biochimie", "Épidémiologie / Biostats", "Anatomie", "Pharmacologie", "Droit Médical"])
    difficulte = st.slider("Niveau de pièges :", 1, 10, 8)
    nombre_qcm = st.number_input("Volume total de questions désiré :", 1, 50, 10)
    mode_examen = st.toggle("🚨 Activer le Mode Concours (Masquer indices)")

st.title("🎓 Simulateur d'Évaluation Hybride (Ultra-Stable)")

c1, c2 = st.columns(2)
with c1: f_pdf = st.file_uploader("1. Support de cours (PDF volumineux accepté)", type=['pdf'])
with c2: f_word = st.file_uploader("2. Notes personnelles (Word)", type=['docx'])

if f_pdf:
    doc_t = fitz.open(stream=f_pdf.read(), filetype="pdf")
    p_tot = len(doc_t)
    doc_t.close()
    
    p_deb, p_fin = st.slider("Sélectionner la plage de pages :", 1, p_tot, (1, p_tot))
    
    if st.button("🚀 Lancer l'Évaluation", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Clé API absente.")
        else:
            with st.spinner("Analyse du document et construction des QCU / Rédaction en cours..."):
                try:
                    txt = extraire_texte_pdf(f_pdf, p_deb, p_fin)
                    txt_w = lire_word(f_word) if f_word else ""
                    st.session_state['data'] = generer_donnees_hybrides(txt, txt_w, matiere, difficulte, nombre_qcm, mode_examen, api_key)
                    st.session_state['examen_soumis'] = False
                    st.rerun()
                except Exception as e: 
                    st.error(f"Incident technique : {e}")

if 'data' in st.session_state:
    data = st.session_state['data']
    t1, t2 = st.tabs(["✍️ Grille d'Entraînement", "📓 Mon Cahier d'Erreurs"])

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
                    "Sélectionner l'affirmation correcte :", options=list(opts.keys()), 
                    format_func=lambda x: f"{x}. {nettoyer_question(opts.get(x, ''))}",
                    index=None, key=f"widget_qcu_{i}", disabled=is_disabled
                )
            elif type_q == "OUVERTE":
                reponse_user = st.text_area("✍️ Saisis ta réponse rédigée :", key=f"widget_ouv_{i}", height=120, disabled=is_disabled)
            
            if not is_disabled and not mode_examen:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    with st.expander("💡 Indice de réflexion"): st.info(nettoyer_question(q.get('indice', 'Aucun indice.')))
                with col_h2:
                    with st.expander("🧠 Point d'ancrage mnémotechnique"): st.warning(f"{nettoyer_question(q.get('mnemotechnique', 'Aucune astuce.'))}")
            
            if is_disabled:
                if type_q == "QCU":
                    bonne_rep = q.get('reponse_correcte', '')
                    choix_propre = choix if choix else "Aucune réponse"
                    juste = (choix == bonne_rep and choix is not None)
                    
                    if juste:
                        st.markdown(f"<div class='correct-box'>✅ <b>Proposition Exacte !</b> La réponse attendue était {bonne_rep}.</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='error-box'>❌ <b>Erreur !</b> Tu as coché la lettre {choix_propre}. L'affirmation vraie était la {bonne_rep}.</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, str(choix_propre), bonne_rep, assembler_texte_html(q.get('explication')))
                    
                    with st.expander("Analyse détaillée"): st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
                
                elif type_q == "OUVERTE":
                    mots_cles = q.get('mots_cles', [])
                    reponse_str = str(reponse_user) if reponse_user else ""
                    mots_trouves = [m for m in mots_cles if str(m).lower() in reponse_str.lower()]
                    ratio = len(mots_trouves) / max(1, len(mots_cles))
                    
                    if ratio >= 0.5:
                        st.markdown(f"<div class='correct-box'>✅ <b>Validation réussie !</b> ({len(mots_trouves)}/{len(mots_cles)} mots-clés présents).</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='warning-box'>⚠️ <b>Incomplet :</b> Restitution trop imprécise ({len(mots_trouves)}/{len(mots_cles)} mots-clés présents).</div>", unsafe_allow_html=True)
                        ajouter_erreur_session(matiere, question_propre, reponse_str[:60]+"...", ", ".join(mots_cles), assembler_texte_html(q.get('explication')))
                    
                    st.markdown(f"<b>Mots-clés requis :</b> <code>{', '.join(mots_cles)}</code>", unsafe_allow_html=True)
                    with st.expander("Grille analytique de correction"): 
                        st.success(f"**Modèle idéal :** {nettoyer_question(q.get('reponse_attendue', ''))}")
                        st.markdown(assembler_texte_html(q.get('explication')), unsafe_allow_html=True)
            st.divider()
        
        if not st.session_state['examen_soumis']:
            if st.button("🏁 Clôturer la Session et Corriger ma Copie", type="primary", use_container_width=True):
                st.session_state['examen_soumis'] = True
                st.rerun()
        else:
            if st.button("🔄 Initialiser une Nouvelle Évaluation Active", use_container_width=True):
                st.session_state['examen_soumis'] = False
                st.rerun()

    with t2:
        mem = st.session_state.get('cahier_memoire', {})
        if not mem: 
            st.info("Aucune erreur enregistrée pour le moment.")
        else:
            for mat, errs in mem.items():
                with st.expander(f"Discipline : {mat} ({len(errs)} fautes stockées)", expanded=True):
                    for e in reversed(errs):
                        st.markdown(f"""
                        <div class='erreur-log'>
                            <strong>Question :</strong> {e['question']}<br>
                            <span style='color:#ff4b4b'><b>Ta réponse :</b> {e['choix_user']}</span> | 
                            <span style='color:#28a745'><b>Donnée attendue :</b> {e['bonnes_rep']}</span><br><br>
                            <strong>Justification :</strong><br>{e['explication']}
                        </div>
                        """, unsafe_allow_html=True)
