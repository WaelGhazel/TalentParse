# TalentParse

A **Flask web application** to extract text from CVs (PDF, DOCX, TXT), parse them into structured JSON using **Ollama LLM**, and score their fit against a job description. Additionally, you can **download the results as a CSV file** for further analysis.

---

## 📁 Project Structure

```
.
├── app.py              # Main Flask application
├── templates/
│   └── index.html      # HTML template
├── cvs/                # Folder to place CV files
├── cache/              # Cache folder for processed files (auto-created)
└── README.md
```

---

## ⚡ Features

* Parse **PDF, DOCX, TXT** CVs.
* Automatically handle **scanned PDFs** via OCR.
* Extract structured JSON including:

  * First & last name
  * Email & phone
  * Skills
  * Years of experience
  * Companies worked for
  * Languages
  * Certifications
  * Education
* Extract key requirements from a job description.
* Compute a **relevance score (0–100)** for each candidate.
* Determine **matching points** explaining why the candidate is a good fit.
* Web interface for uploading CVs and job descriptions.
* Multi-threaded processing for speed.
* **Download results as a CSV file** with all processed candidate data.

---

## 🛠 Installation

### 1. Clone the repository

```bash
git https://github.com/WaelGhazel/TalentParse
cd TalentParse
```

### 2. Install Python dependencies

```bash
pip install flask PyMuPDF pdf2image pytesseract pillow python-docx ollama numpy
```

### 3. Install external tools

#### **Tesseract OCR**

* **Windows:** [Download installer](https://github.com/tesseract-ocr/tesseract) and add to PATH
* **Linux:** `sudo apt install tesseract-ocr`
* **macOS:** `brew install tesseract`

#### **Poppler**

* **Windows:** [Download binaries](http://blog.alivate.com.au/poppler-windows/) and add `bin` to PATH
* **Linux:** `sudo apt install poppler-utils`
* **macOS:** `brew install poppler`

#### **Ollama**

* Install from [https://ollama.com](https://ollama.com/docs/installation)
* Ensure required models are available: `qwen:3b` or `gemma:3b` for parsing, `nomic-embed-text` for embeddings.

---

## 📝 Usage

1. **Upload CVs** (PDF, DOCX, TXT) through the web interface.

2. **Paste the job description** in the provided text area.

3. **Submit the form**. The app will:

   * Extract text from each CV.
   * Parse the CV into structured JSON retrieving:

     * First & last name
     * Email & phone
     * Skills
     * Years of experience
     * Companies worked for
     * Languages
     * Certifications
     * Education
   * Extract key requirements from the job description.
   * Compute a **relevance score (0–100)** for each candidate based on:

     * Skills matching (most important)
     * Education matching
     * Years of experience (only if explicitly stated)
     * Languages, certifications, companies (if present)
   * Determine **matching points**, showing why this candidate is a good fit.
   * Display results in descending order with:

     * Candidate name
     * Email & phone
     * Relevance score
     * Strongest matching points

4. **Download CSV of results**:

   * After processing, click the **“Download CSV Report”** button.
   * This will download a file named `results.csv` containing all candidate details and scores.

5. **Open the app in a browser**:

```
http://127.0.0.1:5000/
```

6. **Click "Process CVs"** to see ranked candidates with detailed matching points and contact info.

---

## ⚙️ Configuration

You can modify these settings at the top of `app.py`:

```python
CV_FOLDER = "cvs"
CACHE_DIR = "cache"
RESULTS_CSV = "results.csv"

LLM_MODEL = "gemma3:4b"         # Candidate & Job parsing
MAX_WORKERS = min(8, os.cpu_count() or 4)
```

---

## 🖥 Supported File Types

| Extension | Extraction method      |
| --------- | ---------------------- |
| `.pdf`    | PyMuPDF + OCR fallback |
| `.docx`   | python-docx            |
| `.txt`    | Plain text             |

---

## ⚠️ Notes

* OCR is used **only for PDF pages without extractable text**.
* Cached text is stored in `cache/` to speed up repeated processing.
* LLM parsing depends on **Ollama API locally installed and models downloaded**.
* Job fit scoring uses **LLM-based scoring** rather than exact matches.
* CSV download is **only available after processing CVs**.

---

## 🔗 References

* [Flask Documentation](https://flask.palletsprojects.com/)
* [PyMuPDF](https://pymupdf.readthedocs.io/)
* [pdf2image](https://github.com/Belval/pdf2image)
* [pytesseract](https://github.com/madmaze/pytesseract)
* [Ollama](https://ollama.com)

---

## 📝 License

MIT License
