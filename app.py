from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import random
import os
import json

import markdown2

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a secure key in production
DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'mcq_database.db')

# Store question data in filesystem instead of session to reduce cookie size
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

@app.template_filter('markdown')
def markdown_filter(text):
    return markdown2.markdown(text or "")

# Make zip available in templates
@app.template_global()
def zip(*args):
    return __builtins__.zip(*args)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_quiz_data(quiz_id, data):
    """Save quiz data to filesystem instead of session"""
    filepath = os.path.join(TEMP_DIR, f"quiz_{quiz_id}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f)

def load_quiz_data(quiz_id):
    """Load quiz data from filesystem"""
    filepath = os.path.join(TEMP_DIR, f"quiz_{quiz_id}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

def delete_quiz_data(quiz_id):
    """Delete quiz data file when quiz is completed"""
    filepath = os.path.join(TEMP_DIR, f"quiz_{quiz_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)

@app.route('/', methods=['GET', 'POST'])
def home():
    conn = get_db_connection()
    
    # Get all chapters
    all_chapters = conn.execute('SELECT id, name, parent_id FROM chapters ORDER BY name').fetchall()
    
    # Get question count for each chapter
    chapter_question_counts = {}
    counts = conn.execute('''
        SELECT chapter_id, COUNT(DISTINCT question_id) as question_count 
        FROM question_chapters 
        GROUP BY chapter_id
    ''').fetchall()
    
    for count in counts:
        chapter_question_counts[count['chapter_id']] = count['question_count']
    
    # Organize chapters into a hierarchical structure
    parent_chapters = []
    subchapters_by_parent = {}
    
    # First, separate parent chapters and organize subchapters by parent_id
    for chapter in all_chapters:
        if chapter['parent_id'] is None:
            # This is a parent chapter
            parent_chapter = dict(chapter)
            parent_chapter['subchapters'] = []
            parent_chapter['own_question_count'] = chapter_question_counts.get(chapter['id'], 0)
            parent_chapters.append(parent_chapter)
        else:
            # This is a subchapter
            parent_id = chapter['parent_id']
            if parent_id not in subchapters_by_parent:
                subchapters_by_parent[parent_id] = []
            subchapter = dict(chapter)
            subchapter['question_count'] = chapter_question_counts.get(chapter['id'], 0)
            subchapters_by_parent[parent_id].append(subchapter)
    
    # Add subchapters to their parent chapters and calculate total question counts
    for parent in parent_chapters:
        total_questions = parent['own_question_count']
        if parent['id'] in subchapters_by_parent:
            parent['subchapters'] = subchapters_by_parent[parent['id']]
            # Add up all subchapter questions
            for subchapter in parent['subchapters']:
                total_questions += subchapter['question_count']
        
        parent['question_count'] = total_questions
    
    # Get tags and question counts for selected chapters
    tag_question_counts = {}
    if request.method == 'POST':
        selected_chapters = request.form.getlist('chapters')
        if selected_chapters:
            # Fetch tags and their question counts
            tag_counts = conn.execute('''
                SELECT t.id, t.name, COUNT(DISTINCT qt.question_id) as question_count
                FROM tags t
                JOIN question_tags qt ON t.id = qt.tag_id
                JOIN question_chapters qc ON qt.question_id = qc.question_id
                WHERE qc.chapter_id IN ({})
                GROUP BY t.id
            '''.format(','.join('?' for _ in selected_chapters)), selected_chapters).fetchall()
            
            for tag in tag_counts:
                tag_question_counts[tag['id']] = {
                    'name': tag['name'],
                    'question_count': tag['question_count']
                }

    # Debug: Print tag_question_counts to verify data
    # print('Tag Question Counts:', tag_question_counts)

    conn.close()
    
    if request.method == 'POST':
        selected_chapters = request.form.getlist('chapters')
        num_questions = int(request.form.get('num_questions', 1))
        if not selected_chapters:
            return render_template('home.html', parent_chapters=parent_chapters, error='Please select at least one chapter.', tag_question_counts=tag_question_counts)
        
        # Check if tags are being selected
        selected_tags = request.form.getlist('tags')
        if not selected_tags:
            # If no tags are selected, use all questions from selected chapters
            selected_tags = None
        
        # Generate a unique quiz ID
        quiz_id = str(random.randint(10000, 99999))
        session['quiz_id'] = quiz_id
        session['selected_chapters'] = selected_chapters
        session['selected_tags'] = selected_tags
        session['num_questions'] = num_questions
        return redirect(url_for('quiz'))
    
    return render_template('home.html', parent_chapters=parent_chapters, tag_question_counts=tag_question_counts)

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    # Check if a quiz is in progress
    if 'quiz_id' not in session or 'selected_chapters' not in session or 'num_questions' not in session:
        return redirect(url_for('home'))
    
    quiz_id = session['quiz_id']
    quiz_state = load_quiz_data(quiz_id)
    
    # Initialize quiz data if it doesn't exist
    if quiz_state is None:
        # Fetch random questions from selected chapters and tags
        conn = get_db_connection()
        chapter_ids = ','.join('?' for _ in session['selected_chapters'])
        tag_ids = ','.join('?' for _ in session['selected_tags']) if session['selected_tags'] else None
        
        if tag_ids:
            query = f"""
                SELECT DISTINCT q.id, q.question_text, q.correct_answer, q.rationale FROM questions q
                JOIN question_chapters qc ON q.id = qc.question_id
                JOIN question_tags qt ON q.id = qt.question_id
                WHERE qc.chapter_id IN ({chapter_ids}) AND qt.tag_id IN ({tag_ids})
            """
            params = session['selected_chapters'] + session['selected_tags']
        else:
            query = f"""
                SELECT DISTINCT q.id, q.question_text, q.correct_answer, q.rationale FROM questions q
                JOIN question_chapters qc ON q.id = qc.question_id
                WHERE qc.chapter_id IN ({chapter_ids})
            """
            params = session['selected_chapters']
        
        questions = conn.execute(query, params).fetchall()
        
        # If num_questions is -1, include all available questions
        if session['num_questions'] == -1:
            # Use all questions, just shuffle them
            questions = random.sample(list(questions), len(questions))
        else:
            # Use the specified number of questions
            questions = random.sample(list(questions), min(session['num_questions'], len(questions)))
        
        quiz_data = []
        for q in questions:
            options = conn.execute('SELECT option_letter, option_text FROM options WHERE question_id = ? ORDER BY option_letter', (q['id'],)).fetchall()
            quiz_data.append({
                'id': q['id'],
                'question_text': q['question_text'],
                'correct_answer': q['correct_answer'],
                'rationale': q['rationale'],
                'options': [dict(option) for option in options]
            })
        conn.close()
        
        quiz_state = {
            'quiz_data': quiz_data,
            'current_question': 0,
            'score': 0,
            'user_answers': [],
            'answer_submitted': False
        }
        save_quiz_data(quiz_id, quiz_state)
    
    # Get current quiz state
    quiz_data = quiz_state['quiz_data']
    current = quiz_state['current_question']
    
    # Check if we've reached the end of the quiz
    if current >= len(quiz_data):
        # Save final state for results
        session['score'] = quiz_state['score']
        session['total'] = len(quiz_data)
        session['quiz_data'] = quiz_data
        session['user_answers'] = quiz_state['user_answers']
        return redirect(url_for('results'))
    
    # Handle answer submission
    if request.method == 'POST' and request.form.get('option') and not quiz_state.get('answer_submitted', False):
        selected = request.form.get('option')
        correct = quiz_data[current]['correct_answer']
        is_correct = (selected == correct)
        
        # Update score if correct
        if is_correct:
            quiz_state['score'] += 1
            
        # Record user's answer for this question
        user_answers = quiz_state.get('user_answers', [])
        while len(user_answers) <= current:
            user_answers.append(None)  # Fill in any gaps
            
        user_answers[current] = {
            'selected': selected,
            'correct': correct,
            'is_correct': is_correct,
            'rationale': quiz_data[current]['rationale']
        }
        
        quiz_state['user_answers'] = user_answers
        quiz_state['answer_submitted'] = True  # Mark that this question has been answered
        save_quiz_data(quiz_id, quiz_state)
        
        # Return the same question but with rationale
        return render_template(
            'quiz.html',
            question=quiz_data[current],
            current=current+1,  # Display is 1-indexed
            total=len(quiz_data),
            show_rationale=True,
            current_answer=user_answers[current]  # Pass specific answer for this question
        )
    
    # Normal question display (GET or after moving to next question)
    quiz_state['answer_submitted'] = False  # Reset for new question
    save_quiz_data(quiz_id, quiz_state)
    return render_template(
        'quiz.html',
        question=quiz_data[current],
        current=current+1,  # Display is 1-indexed
        total=len(quiz_data),
        show_rationale=False
    )

@app.route('/next', methods=['POST'])
def next_question():
    if 'quiz_id' not in session:
        return redirect(url_for('home'))
    
    quiz_id = session['quiz_id']
    quiz_state = load_quiz_data(quiz_id)
    if quiz_state is None:
        return redirect(url_for('home'))

    # Move to next question only if answer was submitted
    if quiz_state.get('answer_submitted', False):
        quiz_state['current_question'] += 1
        save_quiz_data(quiz_id, quiz_state)
    
    # Check if the quiz is complete and redirect to results
    quiz_data = quiz_state['quiz_data']
    current = quiz_state['current_question']
    if current >= len(quiz_data):
        # Save final state for results
        session['score'] = quiz_state['score']
        session['total'] = len(quiz_data)
        session['quiz_data'] = quiz_data
        session['user_answers'] = quiz_state['user_answers']
        return redirect(url_for('results'))

    return redirect(url_for('quiz'))

@app.route('/results')
def results():
    score = session.get('score', 0)
    total = session.get('total', 0)
    quiz_data = session.get('quiz_data', [])
    user_answers = session.get('user_answers', [])
    
    # Clean up session and temp data
    if 'quiz_id' in session:
        delete_quiz_data(session['quiz_id'])
    session.clear()
    
    return render_template('results.html', score=score, total=total, user_answers=user_answers, quiz_data=quiz_data)

@app.route('/get_tags', methods=['POST'])
def get_tags():
    selected_chapters = request.json.get('chapters', [])
    conn = get_db_connection()
    tag_counts = conn.execute('''
        SELECT t.id, t.name, COUNT(DISTINCT qt.question_id) as question_count
        FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
        JOIN question_chapters qc ON qt.question_id = qc.question_id
        WHERE qc.chapter_id IN ({})
        GROUP BY t.id
    '''.format(','.join('?' for _ in selected_chapters)), selected_chapters).fetchall()
    conn.close()
    
    tag_question_counts = {tag['id']: {'name': tag['name'], 'question_count': tag['question_count']} for tag in tag_counts}
    return {'tags': tag_question_counts}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
