from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import os
import fitz
from sentence_transformers import SentenceTransformer, util
from utils import extract_entities
import re
import logging

# ---------- Config ----------
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------- Helper functions ----------
def extract_text_pymupdf(pdf_path):
    text = ""
    doc = fitz.open(pdf_path)
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- Model loading (from env var) ----------
MODEL_NAME = os.environ.get("MODEL_NAME", "all-MiniLM-L6-v2")
logging.info(f"Loading sentence-transformer model: {MODEL_NAME}")
try:
    model = SentenceTransformer(MODEL_NAME)
    logging.info(f"Model '{MODEL_NAME}' loaded successfully.")
except Exception as e:
    logging.exception(f"Failed to load model '{MODEL_NAME}': {e}")
    # re-raise so the app doesn't run with missing model
    raise

# ---------- Routes ----------
@app.route('/')
def index():
    # optionally pass dynamic values if your templates expect them
    return render_template('index.html', github_username="abhiram849", year=2025)

@app.route('/analyze', methods=['POST'])
def analyze():
    resume_file = request.files.get('resume')
    job_desc = request.form.get('job_description', "").strip()

    if not resume_file or resume_file.filename == "" or not job_desc:
        return "Resume file or job description missing.", 400

    if not allowed_file(resume_file.filename):
        return "Only PDF uploads are allowed.", 400

    filename = secure_filename(resume_file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    resume_file.save(save_path)

    # Extract text
    resume_text = extract_text_pymupdf(save_path)

    # encode and compute similarity
    embeddings = model.encode([resume_text, job_desc], convert_to_tensor=True)
    similarity_score = util.pytorch_cos_sim(embeddings[0], embeddings[1]).item()
    match_score = round(similarity_score * 100, 2)

    # NER skill extraction
    resume_entities = extract_entities(resume_text)
    resume_skills = set(w.lower() for w in resume_entities.get('SKILL', []))

    # basic JD word extraction (words length >=4)
    jd_words = set(re.findall(r'\b\w{4,}\b', job_desc.lower()))
    matched_skills = sorted(jd_words & resume_skills)
    missing_skills = sorted(jd_words - resume_skills)[:10]

    # Rule-based suggestions
    suggestions = []
    if "flask" in jd_words and "flask" not in resume_text.lower():
        suggestions.append("Mention your experience working with Flask or similar web frameworks.")
    if "sql" in jd_words and "sql" not in resume_text.lower():
        suggestions.append("Include your experience with SQL databases.")
    if "api" in jd_words and "api" not in resume_text.lower():
        suggestions.append("Describe any projects where you built or worked with APIs.")
    if len(resume_text.split()) < 150:
        suggestions.append("Your resume seems short. Add more details about your experience, skills, or projects.")
    if not any(heading in resume_text.lower() for heading in ["experience", "work", "project"]):
        suggestions.append("Consider adding an 'Experience' or 'Projects' section to highlight your background.")

    return render_template(
        'result.html',
        match_score=match_score,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        suggestions=suggestions
    )

# ---------- Run (local or hosting) ----------
if __name__ == '__main__':
    # Use PORT env var if provided (hosts like Render provide $PORT)
    port = int(os.environ.get("PORT", 5000))
    # Enable debug locally by setting FLASK_DEBUG=1 in env if you want
    debug_mode = bool(os.environ.get("FLASK_DEBUG", False))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
