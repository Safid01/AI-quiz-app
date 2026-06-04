from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict
import google.generativeai as genai
import os
import json
import re
import uuid

API_KEY = "AIzaSyAbz4X6EEk2ulSp6JT5Ma45EaYvhbKUxEY" 
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-3-flash-preview")

app = FastAPI(title="NeuroQuiz API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Schemas ----------------

class Question(BaseModel):
    question_text: str
    options: List[str] = Field(min_items=4, max_items=4)
    correct_option_index: int = Field(ge=0, le=3)

class QuizSchema(BaseModel):
    questions: List[Question]

class GenerateQuizRequest(BaseModel):
    topic: str
    difficulty: str = "Hard"
    count: int = 5
    duration_sec: int = 300

class SubmitRequest(BaseModel):
    answers: Dict[int, int]

# ---------------- In-memory stores (replace with Firestore) ----------------

QUIZZES = {}
ATTEMPTS = {}

# ---------------- Helpers ----------------

def extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON found")
    return match.group(0)

def gemini_generate(req: GenerateQuizRequest) -> dict:
    prompt = f"""
    Generate EXACTLY {req.count} {req.difficulty} multiple-choice questions about {req.topic}.
    Return ONLY a JSON object.
    
    Format:
    {{
      "questions": [
        {{
          "question_text": "string",
          "options": ["a", "b", "c", "d"],
          "correct_option_index": 0
        }}
      ]
    }}
    """
    # In 2026, we use 'response_mime_type' to prevent JSON parsing errors
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )

    if not response.text:
        raise RuntimeError("Gemini returned empty response")

    # No more regex needed! response_mime_type ensures clean JSON.
    return json.loads(response.text)

# ---------------- API Endpoints ----------------

@app.post("/api/admin/generate-quiz")
def generate_quiz(req: GenerateQuizRequest):
    try:
        quiz_id = str(uuid.uuid4())
        data = gemini_generate(req)
        quiz = QuizSchema.model_validate(data)

        QUIZZES[quiz_id] = {
            "meta": req.dict(),
            "quiz": quiz.model_dump()
        }

        return {"quiz_id": quiz_id, "quiz": quiz.model_dump()}

    except Exception as e:
        print("🔥 ERROR during quiz generation:", repr(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/quizzes/{quiz_id}")
def get_quiz(quiz_id: str):
    if quiz_id not in QUIZZES:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return QUIZZES[quiz_id]["quiz"]

@app.post("/api/attempts/{quiz_id}/submit")
def submit_attempt(quiz_id: str, req: SubmitRequest):
    if quiz_id not in QUIZZES:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = QUIZZES[quiz_id]["quiz"]
    score = 0
    for i, q in enumerate(quiz["questions"]):
        if req.answers.get(i) == q["correct_option_index"]:
            score += 1

    attempt_id = str(uuid.uuid4())
    ATTEMPTS[attempt_id] = {
        "quiz_id": quiz_id,
        "answers": req.answers,
        "score": score,
        "total": len(quiz["questions"])
    }

    return {"attempt_id": attempt_id, "score": score, "total": len(quiz["questions"])}

@app.get("/api/admin/results")
def get_results():
    # In real app: protect with admin auth + read from Firestore
    return ATTEMPTS