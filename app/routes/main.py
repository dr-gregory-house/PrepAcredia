from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from app.utils.db import get_db_connection
from app.utils.decorators import login_required
import random

main_bp = Blueprint('main', __name__)

@main_bp.route('/', methods=['GET', 'POST'])
def home():
    # Redirect unauthenticated users to login page
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
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
        return redirect(url_for('quiz.start_quiz'))
    
    return render_template('home.html', parent_chapters=parent_chapters, tag_question_counts=tag_question_counts)

@main_bp.route('/get_tags', methods=['POST'])
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
    return jsonify({'tags': tag_question_counts}) 