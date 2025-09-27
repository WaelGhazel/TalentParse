# app.py
import os
import glob
import json
import hashlib
import re
import csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename

# PDF and DOCX parsing
import fitz  # PyMuPDF
from docx import Document

# OCR fallback for scanned PDFs
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

# Ollama
import ollama

# --------------------------
# CONFIG
# --------------------------
today_date = date.today().isoformat()
latest_results = []
CV_FOLDER = "cvs"
CACHE_DIR = "cache"
RESULTS_CSV = "results.csv"
os.makedirs(CV_FOLDER, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

LLM_MODEL = "gemma3:4b"         # Candidate & Job parsing
MAX_WORKERS = min(8, os.cpu_count() or 4)

# --------------------------
# HELPERS
# --------------------------
def _cache_path(p: Path) -> Path:
    key = f"{p.resolve()}:{p.stat().st_mtime}"
    h = hashlib.md5(key.encode()).hexdigest()
    return Path(CACHE_DIR) / f"{h}.txt"

def extract_text_pdf(pdf_path: Path) -> str:
    text_parts = []
    pages_without_text = []
    try:
        with fitz.open(str(pdf_path)) as doc:
            for i, page in enumerate(doc):
                t = page.get_text("text")
                if t and t.strip():
                    text_parts.append(t)
                else:
                    pages_without_text.append(i)

        if pages_without_text:
            images = convert_from_path(
                str(pdf_path),
                dpi=250,
                fmt="png",
                first_page=min(pages_without_text)+1,
                last_page=max(pages_without_text)+1
            )
            for pil_img in images:
                try:
                    text_parts.append(pytesseract.image_to_string(pil_img))
                except:
                    pass
    except:
        try:
            images = convert_from_path(str(pdf_path), dpi=250, fmt="png")
            for pil_img in images:
                text_parts.append(pytesseract.image_to_string(pil_img))
        except:
            pass
    return "\n".join(text_parts).strip()

def extract_text_docx(path: Path) -> str:
    try:
        d = Document(str(path))
        return "\n".join(p.text for p in d.paragraphs).strip()
    except:
        return ""

def extract_text_plain(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except:
        return path.read_text(encoding="latin-1", errors="ignore")

def extract_text(file_path: Path) -> str:
    cp = _cache_path(file_path)
    if cp.exists():
        return cp.read_text(encoding="utf-8", errors="ignore")

    ext = file_path.suffix.lower()
    if ext == ".pdf":
        text = extract_text_pdf(file_path)
    elif ext == ".docx":
        text = extract_text_docx(file_path)
    elif ext == ".txt":
        text = extract_text_plain(file_path)
    else:
        text = ""

    try:
        cp.write_text(text, encoding="utf-8")
    except:
        pass
    return text

def extract_contacts(cv_text: str):
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", cv_text)
    phones = re.findall(r"(\+?\d[\d\s\-]{6,}\d)", cv_text)
    return {"emails": emails, "phones": phones}

def extract_name(cv_text: str):
    for line in cv_text.splitlines():
        words = line.strip().split()
        if 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
            return words[0], " ".join(words[1:])
    return "", ""

# --------------------------
# LLM functions
# --------------------------
def parse_cv(cv_text: str) -> dict:
    contacts = extract_contacts(cv_text)
    first_name, last_name = extract_name(cv_text)

    prompt = f""" You are a strict HR assistant. Extract structured JSON from this CV text **exactly as written**. Do NOT assume, infer, or exaggerate any information. 
    Only extract what is explicitly present in the CV. Use the emails {contacts['emails']} and phones {contacts['phones']} as hints, but do NOT add new ones. 
    **Important:** If a job, education, certification, or project has "present" as the end date, use today's date ({today_date}) to calculate durations (years_experience, ongoing education, etc.). 
    Return JSON with the following fields: {{ "first_name": string, "last_name": string, "email": string or null, "phone": string or null, "skills": [string, ...], "years_experience": float or null, "companies": [string, ...], "languages": [string, ...], "certifications": [string, ...], "education": [{{"institution": string, "degree": string, "start_date": string, "end_date": string or null}}] }} 
    If a field is not present in the CV, leave it as null or empty array. **Do NOT guess.** 
    Return ONLY JSON, no explanation. 
    CV TEXT: \"\"\"{cv_text[:8000]}\"\"\" """

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": "You are an expert HR parser."},
                      {"role": "user", "content": prompt}]
        )
        txt = response["message"]["content"]
        s, e = txt.find("{"), txt.rfind("}")
        if s != -1 and e != -1 and e > s:
            data = json.loads(txt[s:e+1])
            if not data.get("first_name"): data["first_name"] = first_name
            if not data.get("last_name"): data["last_name"] = last_name
            if not data.get("email") and contacts['emails']: data["email"] = contacts['emails'][0]
            if not data.get("phone") and contacts['phones']: data["phone"] = contacts['phones'][0]
            return data
    except Exception as e:
        print(f"[CV parse error]: {e}")
    return {"first_name": first_name, "last_name": last_name,
            "email": contacts['emails'][0] if contacts['emails'] else "",
            "phone": contacts['phones'][0] if contacts['phones'] else "",
            "skills": [], "years_experience": 0, "companies": [], "languages": [],
            "certifications": [], "education": []}

def parse_job(job_text: str) -> dict:
    prompt = f""" You are a strict HR assistant. Extract structured JSON from this job description **exactly as written**. 
    Do NOT assume, infer, or add any requirements that are not explicitly mentioned in the text. 
    Use today's date ({today_date}) wherever "present" or ongoing durations appear. 
    Return JSON with the following fields: {{ "skills_required": [string, ...], "years_required": float or null, "languages_required": [string, ...], "certifications_required": [string, ...] }} 
    If a field is not present in the job description, leave it as null or empty array. 
    **Do NOT guess.** Return ONLY JSON, no explanation. 
    Job Description: \"\"\"{job_text[:4000]}\"\"\" """
    
    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": "You are an expert HR parser."},
                      {"role": "user", "content": prompt}]
        )
        txt = response["message"]["content"]
        s, e = txt.find("{"), txt.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(txt[s:e+1])
    except:
        pass
    return {"skills_required": [], "years_required": 0, "languages_required": [], "certifications_required": []}

def score_candidate(cv_json: dict, job_json: dict) -> dict:
    prompt = f""" You are a strict HR AI assistant. 
    Given a candidate and a job description, compute a **relevance score** from 0 to 100. 
    Do NOT invent or exaggerate any information. Base your score only on the data explicitly present in the Candidate JSON and Job JSON. 
    Consider partial matches, synonyms, and overall relevance — NOT exact string matches. 
    Use today's date ({today_date}) wherever "present" or ongoing durations appear. 
    Candidate JSON: {json.dumps(cv_json)} 
    Job JSON: {json.dumps(job_json)} 
    Return JSON with the following fields: {{ "score": float, "matching_points": [string, ...] }} 
    Guidelines: 
    1. Skills matching is the most important factor; partial matches count. 
    2. Education should influence the score after skills; consider degree, institution, and ongoing studies. 
    3. Years of experience should influence the score proportionally, only if explicitly stated. 
    4. Consider languages, certifications, companies, and other relevant fields only if present. 
    5. Include the **strongest reasons why this candidate is a good fit** in 'matching_points', but do NOT add extra achievements or experience. 
    6. Return ONLY JSON, no explanation, no extra text. 
    Remember: honesty first. Only use the data provided, do not assume or guess. """    
    
    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": "You are an expert HR scorer."},
                      {"role": "user", "content": prompt}]
        )
        txt = response["message"]["content"]
        s, e = txt.find("{"), txt.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(txt[s:e+1])
    except:
        pass
    return {"score": 0.0, "matching_points": []}

# --------------------------
# Process one CV
# --------------------------
def process_one(file_path: Path, job_json: dict) -> dict:
    text = extract_text(file_path)
    if not text.strip():
        return {"error": "Empty text"}
    cv_data = parse_cv(text)
    score_data = score_candidate(cv_data, job_json)
    # Delete the CV after processing
    try:
        file_path.unlink()
    except:
        pass
    return {**cv_data, **score_data}

# --------------------------
# FLASK
# --------------------------
app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    global latest_results
    results = []
    job_desc_text = ""

    if request.method == "POST":
        job_desc_text = request.form.get("job_description", "")
        uploaded_files = request.files.getlist("cv_files")
        for f in uploaded_files:
            if f and f.filename:
                filename = secure_filename(f.filename)
                save_path = Path(CV_FOLDER) / filename
                f.save(save_path)

        job_json = parse_job(job_desc_text)

        files = [Path(p) for p in glob.glob(f"{CV_FOLDER}/*") if Path(p).suffix.lower() in {".pdf", ".docx", ".txt"}]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(process_one, f, job_json): f for f in files}
            for fut in as_completed(futs):
                try:
                    results.append(fut.result())
                except Exception as e:
                    print(f"[Process error] {futs[fut].name}: {e}")

        results = [r for r in results if "error" not in r]
        results.sort(key=lambda x: x["score"], reverse=True)

        # Store sorted results globally
        latest_results = results

    return render_template("index.html", results=results, job_desc_text=job_desc_text)


@app.route("/download_csv")
def download_csv():
    global latest_results
    if not latest_results:
        return "No results to download", 400

    keys = ["first_name", "last_name", "email", "phone", "score", "matching_points"]
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in latest_results:
            writer.writerow({
                "first_name": r.get("first_name", ""),
                "last_name": r.get("last_name", ""),
                "email": r.get("email", ""),
                "phone": r.get("phone", ""),
                "score": r.get("score", 0.0),
                "matching_points": "; ".join(r.get("matching_points", []))
            })

    return send_file(RESULTS_CSV, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
