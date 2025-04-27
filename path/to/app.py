@app.route('/', methods=['GET','POST'])
def home():
    conn = get_db_connection()
    # … existing code that builds parent_chapters …
    
    # ① load tag metadata
    tag_rows = conn.execute('''
      SELECT t.id, t.name, COUNT(DISTINCT qt.question_id) AS question_count
        FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
       GROUP BY t.id
       ORDER BY question_count DESC
    ''').fetchall()
    tag_chapter_rows = conn.execute('''
      SELECT qt.tag_id, qc.chapter_id, COUNT(DISTINCT qt.question_id) AS cnt
        FROM question_tags qt
        JOIN question_chapters qc ON qt.question_id = qc.question_id
       GROUP BY qt.tag_id, qc.chapter_id
    ''').fetchall()
    tags = [dict(r) for r in tag_rows]
    tag_chapter_counts = {}
    for row in tag_chapter_rows:
        tag_chapter_counts.setdefault(row['tag_id'], {})[row['chapter_id']] = row['cnt']
    conn.close()

    if request.method == 'POST':
        selected_chapters = request.form.getlist('chapters')
        selected_tags     = request.form.getlist('tags')
        num_questions     = int(request.form.get('num_questions', 1))

        # ⇨ now require at least one chapter OR one tag
        if not selected_chapters and not selected_tags:
            return render_template('home.html',
                                   parent_chapters=parent_chapters,
                                   tags=tags,
                                   tag_chapter_counts=tag_chapter_counts,
                                   error='Select at least one chapter or tag.')

        quiz_id = str(random.randint(10000,99999))
        session['quiz_id']           = quiz_id
        session['selected_chapters'] = selected_chapters
        session['selected_tags']     = selected_tags
        session['num_questions']     = num_questions
        return redirect(url_for('quiz'))

    # GET
    return render_template('home.html',
                           parent_chapters=parent_chapters,
                           tags=tags,
                           tag_chapter_counts=tag_chapter_counts)

# …existing code…

@app.route('/quiz', methods=['GET','POST'])
def quiz():
    # … guard + load_quiz_data …

    if quiz_state is None:
        conn = get_db_connection()

        # ⇨ build dynamic chapter/tag filters
        chapters = session.get('selected_chapters', [])
        tags_sel = session.get('selected_tags', [])
        joins = []
        wheres = []
        params = []

        if chapters:
            joins.append('JOIN question_chapters qc ON q.id = qc.question_id')
            ph = ','.join('?' for _ in chapters)
            wheres.append(f'qc.chapter_id IN ({ph})')
            params.extend(chapters)

        if tags_sel:
            joins.append('JOIN question_tags qt ON q.id = qt.question_id')
            pht = ','.join('?' for _ in tags_sel)
            wheres.append(f'qt.tag_id IN ({pht})')
            params.extend(tags_sel)

        # assemble & execute
        query = f"""
          SELECT q.id, q.question_text, q.correct_answer, q.rationale
            FROM questions q
           {' '.join(joins)}
           {'WHERE ' + ' AND '.join(wheres) if wheres else ''}
           GROUP BY q.id
        """
        questions = conn.execute(query, params).fetchall()

        # … rest of initialization (sampling, options, save_quiz_data) … 