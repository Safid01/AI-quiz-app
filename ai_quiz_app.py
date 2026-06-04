import customtkinter as ctk
import ollama
import threading
import json
import re
from pydantic import BaseModel, Field, ValidationError
from typing import List

# ---------------- CONFIG ----------------
MODEL_NAME = "llama3"
EXAM_DURATION_SEC = 300
TOPICS = "Machine Learning, Deep Learning, Artificial Intelligence"
QUESTION_COUNT = 5
DIFFICULTY = "Hard"

# ---------------- SCHEMA ----------------
class Question(BaseModel):
    question_text: str
    options: List[str] = Field(min_items=4, max_items=4)
    correct_option_index: int = Field(ge=0, le=3)

class QuizSchema(BaseModel):
    questions: List[Question]

# ---------------- APP ----------------
class AIQuizApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("NeuroQuiz: AI Generated Exam")
        self.geometry("900x600")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.questions = []
        self.user_answers = {}
        self.current_question_index = 0
        self.score = 0
        self.time_left = EXAM_DURATION_SEC
        self.timer_running = False

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.show_welcome_screen()

    # ---------- UI ----------
    def show_welcome_screen(self):
        self.clear_container()

        ctk.CTkLabel(
            self.container,
            text="NeuroQuiz AI",
            font=("Roboto", 40, "bold")
        ).pack(pady=(80, 20))

        ctk.CTkLabel(
            self.container,
            text=f"Topic: {TOPICS}\n{QUESTION_COUNT} Questions | 5 Minutes\nModel: {MODEL_NAME}",
            font=("Roboto", 16),
            text_color="gray"
        ).pack(pady=10)

        self.btn_start = ctk.CTkButton(
            self.container,
            text="Generate Questions & Start",
            height=50,
            width=260,
            command=self.start_generation_thread
        )
        self.btn_start.pack(pady=40)

        self.status_label = ctk.CTkLabel(self.container, text="", text_color="orange")
        self.status_label.pack(pady=10)

    # ---------- GENERATION ----------
    def start_generation_thread(self):
        self.btn_start.configure(state="disabled")
        self.status_label.configure(text="Generating questions using local LLM...")

        threading.Thread(target=self.generate_questions, daemon=True).start()

    def generate_questions(self):
        try:
            prompt = self.build_prompt()
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response["message"]["content"]
            cleaned_json = self.extract_json(raw)

            quiz = QuizSchema.model_validate_json(cleaned_json)

            if len(quiz.questions) != QUESTION_COUNT:
                raise ValueError("Incorrect number of questions generated")

            self.questions = quiz.questions
            self.after(0, self.start_exam)

        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            self.after(0, lambda: self.status_label.configure(
                text="Failed to generate valid questions. Try again."
            ))
            self.after(0, lambda: self.btn_start.configure(state="normal"))

    def build_prompt(self) -> str:
        return f"""
You are an exam question generator.

Generate EXACTLY {QUESTION_COUNT} difficult multiple-choice questions.

Rules:
- Exactly 4 options per question
- One correct answer only
- correct_option_index must match the correct option
- Output ONLY valid JSON
- No markdown, no explanations

JSON SCHEMA:
{{
  "questions": [
    {{
      "question_text": "string",
      "options": ["string","string","string","string"],
      "correct_option_index": 0
    }}
  ]
}}

Topic: {TOPICS}
Difficulty: {DIFFICULTY}
"""

    def extract_json(self, text: str) -> str:
        text = re.sub(r"```json|```", "", text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise json.JSONDecodeError("No JSON found", text, 0)
        return match.group(0)

    # ---------- EXAM ----------
    def start_exam(self):
        self.time_left = EXAM_DURATION_SEC
        self.timer_running = True
        self.show_question(0)
        self.update_timer()

    def update_timer(self):
        if not self.timer_running:
            return

        mins, secs = divmod(self.time_left, 60)
        if hasattr(self, "lbl_timer"):
            self.lbl_timer.configure(text=f"⏳ {mins:02d}:{secs:02d}")

        if self.time_left <= 0:
            self.end_exam()
            return

        self.time_left -= 1
        self.after(1000, self.update_timer)

    def show_question(self, index):
        self.clear_container()
        self.current_question_index = index
        q = self.questions[index]

        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=10)

        ctk.CTkLabel(
            header,
            text=f"Question {index + 1}/{len(self.questions)}",
            font=("Roboto", 14, "bold")
        ).pack(side="left")

        self.lbl_timer = ctk.CTkLabel(
            header,
            text="⏳",
            font=("Roboto", 14, "bold")
        )
        self.lbl_timer.pack(side="right")

        box = ctk.CTkTextbox(
            self.container,
            height=120,
            font=("Roboto", 18),
            wrap="word"
        )
        box.insert("0.0", q.question_text)
        box.configure(state="disabled")
        box.pack(fill="x", pady=20)

        self.var_choice = ctk.IntVar(value=self.user_answers.get(index, -1))

        for i, opt in enumerate(q.options):
            ctk.CTkRadioButton(
                self.container,
                text=opt,
                variable=self.var_choice,
                value=i,
                font=("Roboto", 16)
            ).pack(anchor="w", padx=20, pady=5)

        nav = ctk.CTkFrame(self.container, fg_color="transparent")
        nav.pack(fill="x", pady=20)

        if index > 0:
            ctk.CTkButton(nav, text="Previous",
                          command=lambda: self.save_and_nav(index - 1)).pack(side="left")

        if index < len(self.questions) - 1:
            ctk.CTkButton(nav, text="Next",
                          command=lambda: self.save_and_nav(index + 1)).pack(side="right")
        else:
            ctk.CTkButton(nav, text="Finish",
                          fg_color="#00C853",
                          command=self.end_exam).pack(side="right")

    def save_and_nav(self, target):
        if self.var_choice.get() != -1:
            self.user_answers[self.current_question_index] = self.var_choice.get()
        self.show_question(target)

    # ---------- RESULTS ----------
    def end_exam(self):
        self.timer_running = False
        self.calculate_score()
        self.show_results()

    def calculate_score(self):
        self.score = sum(
            1 for i, q in enumerate(self.questions)
            if self.user_answers.get(i) == q.correct_option_index
        )

    def show_results(self):
        self.clear_container()
        total = len(self.questions)
        percent = (self.score / total) * 100

        ctk.CTkLabel(self.container, text="Exam Finished",
                     font=("Roboto", 30, "bold")).pack(pady=20)

        ctk.CTkLabel(
            self.container,
            text=f"{percent:.1f}%",
            font=("Roboto", 60, "bold"),
            text_color="#00C853" if percent >= 50 else "#FF5252"
        ).pack()

        ctk.CTkLabel(
            self.container,
            text=f"{self.score} / {total} correct",
            font=("Roboto", 18)
        ).pack(pady=10)

        ctk.CTkButton(self.container, text="New Exam",
                      command=self.show_welcome_screen).pack(pady=30)

    def clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()


if __name__ == "__main__":
    app = AIQuizApp()
    app.mainloop()