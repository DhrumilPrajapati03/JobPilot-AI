"""Resume Parser Service.

Handles text extraction from file bytes (PDF/DOCX) and structuring via LLMs.
"""

import docx
import pypdf
from io import BytesIO
from app.models.resume import Resume
from app.services.llm import get_llm_client


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text page-by-page from PDF bytes."""
    reader = pypdf.PdfReader(BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract all paragraph text from DOCX bytes."""
    doc = docx.Document(BytesIO(file_bytes))
    text = ""
    for paragraph in doc.paragraphs:
         text += paragraph.text + "\n"
    return text


def parse_resume_text(text: str) -> Resume:
    """Sends raw resume text to the LLM and parses it into the Resume model.

    Uses LangChain structured output to enforce schema validation.
    """
    # Using Groq (Llama 3.1 70B) for fast and structured parsing
    llm = get_llm_client("groq")
    
    # Force the LLM to output structural JSON matching the Resume Pydantic model
    structured_llm = llm.with_structured_output(Resume)
    
    prompt = (
        "You are an expert resume parsing assistant. Analyze the raw resume text provided "
        "below and extract it into a structured schema matching the requested schema.\n"
        "Instructions:\n"
        "- Do not make up facts. Extract only information present in the text.\n"
        "- Standardize dates where possible.\n"
        "- Separate primary technical skills (languages, frameworks) from secondary skills.\n\n"
        f"Raw Resume Text:\n{text}"
    )
    
    # The return value is a fully populated and validated Resume Pydantic object
    parsed_resume = structured_llm.invoke(prompt)
    return parsed_resume
