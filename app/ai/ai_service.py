"""
MODULE 6 — Generative AI Tutor Service
=======================================
All OpenAI interactions are centralised here.
Prompts are personalised using learner context (mastery, weak topics, quiz history).
"""

import os
import json
from openai import OpenAI
from datetime import datetime
from ..models import db, AIResponse

# Initialise client once — key read from environment
_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY not set in environment.')
        base_url = os.getenv('OPENROUTER_BASE_URL', 'https://api.openai.com/v1')
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Project Synapse",
            },
        )
    return _client

def _call_openai(system_prompt: str, user_prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
    """
    Low-level wrapper around the Chat Completions API.
    Returns (response_text, tokens_used).
    """
    client = _get_client()
    model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    response = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user',   'content': user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )

    text = response.choices[0].message.content.strip()
    tokens = response.usage.total_tokens if response.usage else 0
    return text, tokens


def _save_response(user_id: int, response_type: str, prompt: str,
                   generated_response: str, weak_topics: str,
                   mastery_score: float, tokens_used: int):
    """Persist every AI interaction to the database for audit/research."""
    record = AIResponse(
        user_id=user_id,
        response_type=response_type,
        prompt=prompt,
        generated_response=generated_response,
        weak_topics=weak_topics,
        mastery_score=mastery_score,
        tokens_used=tokens_used,
        model_used=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
    )
    db.session.add(record)
    db.session.commit()
    return record


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def generate_explanation(user_id: int, topic: str, weak_topics: list,
                         mastery_score: float, lesson_content: str = '') -> str:
    """
    Generate a personalised explanation for a topic.
    Context: learner's weak areas and current mastery level.
    """
    weak_str = ', '.join(weak_topics) if weak_topics else 'general concepts'
    level = _mastery_to_level(mastery_score)

    system_prompt = (
        "You are an expert adaptive tutor in an online learning platform. "
        "Your explanations are clear, concise, and tailored to the student's level. "
        "Use analogies and examples. Avoid jargon unless explaining it first."
    )
    user_prompt = (
        f"The student is a {level} learner with a mastery score of {mastery_score:.1f}%. "
        f"Their weak topics are: {weak_str}. "
        f"Please explain '{topic}' in a way that directly addresses their gaps. "
        f"Keep the explanation under 300 words and structured with bullet points where helpful."
    )
    if lesson_content:
        user_prompt += f"\n\nLesson context:\n{lesson_content[:500]}"

    response, tokens = _call_openai(system_prompt, user_prompt, max_tokens=600)
    _save_response(user_id, 'explanation', user_prompt, response, weak_str, mastery_score, tokens)
    return response


def generate_summary(user_id: int, lesson_title: str, lesson_content: str,
                     mastery_score: float, weak_topics: list) -> str:
    """
    Generate a revision summary of a lesson tailored to the student.
    """
    weak_str = ', '.join(weak_topics) if weak_topics else 'none identified'
    level = _mastery_to_level(mastery_score)

    system_prompt = (
        "You are a knowledgeable tutor creating concise study summaries. "
        "Highlight key concepts and emphasise areas the student finds difficult."
    )
    user_prompt = (
        f"Create a revision summary for a {level} student (mastery: {mastery_score:.1f}%) "
        f"of the lesson: '{lesson_title}'. Their weak topics: {weak_str}.\n\n"
        f"Lesson content:\n{lesson_content[:1000]}\n\n"
        "Format: use headings and bullet points. Max 400 words."
    )

    response, tokens = _call_openai(system_prompt, user_prompt, max_tokens=700)
    _save_response(user_id, 'summary', user_prompt, response, weak_str, mastery_score, tokens)
    return response


def generate_quiz(user_id: int, topic: str, weak_topics: list,
                  mastery_score: float, num_questions: int = 5) -> list:
    """
    Generate adaptive multiple-choice quiz questions.
    Returns a list of question dicts: {question, options, correct}.
    """
    weak_str = ', '.join(weak_topics) if weak_topics else topic
    level = _mastery_to_level(mastery_score)

    system_prompt = (
        "You are an assessment designer. Generate multiple-choice questions in strict JSON format. "
        "Return ONLY a JSON array, no markdown fences, no extra text."
    )
    user_prompt = (
        f"Generate {num_questions} multiple-choice questions about '{topic}' "
        f"for a {level} learner (mastery: {mastery_score:.1f}%) focusing on: {weak_str}. "
        "Each question: {\"question\": \"...\", \"options\": [\"A. ...\", \"B. ...\", \"C. ...\", \"D. ...\"], \"correct\": \"A\"}"
    )

    response, tokens = _call_openai(system_prompt, user_prompt, max_tokens=1200)
    _save_response(user_id, 'quiz', user_prompt, response, weak_str, mastery_score, tokens)

    # Parse JSON safely
    try:
        # Strip potential markdown fences just in case
        clean = response.strip().lstrip('```json').rstrip('```').strip()
        questions = json.loads(clean)
        return questions if isinstance(questions, list) else []
    except json.JSONDecodeError:
        return []


def generate_revision_notes(user_id: int, course_title: str, weak_topics: list,
                             mastery_score: float) -> str:
    """
    Generate personalised revision notes targeting weak areas.
    """
    weak_str = ', '.join(weak_topics) if weak_topics else 'all topics'
    level = _mastery_to_level(mastery_score)

    system_prompt = (
        "You are an expert revision guide writer. Create focused, actionable revision notes "
        "that help students overcome their specific knowledge gaps."
    )
    user_prompt = (
        f"Write personalised revision notes for a {level} student studying '{course_title}'. "
        f"Their mastery score is {mastery_score:.1f}% and they struggle with: {weak_str}. "
        "Structure: Overview → Key Concepts → Common Mistakes → Practice Tips. "
        "Max 500 words. Use numbered lists and sub-bullets."
    )

    response, tokens = _call_openai(system_prompt, user_prompt, max_tokens=800)
    _save_response(user_id, 'revision', user_prompt, response, weak_str, mastery_score, tokens)
    return response


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _mastery_to_level(mastery: float) -> str:
    """Convert numeric mastery to descriptive level string."""
    if mastery < 30:
        return 'struggling beginner'
    elif mastery < 50:
        return 'beginner'
    elif mastery < 70:
        return 'intermediate'
    elif mastery < 85:
        return 'advanced'
    else:
        return 'expert'
