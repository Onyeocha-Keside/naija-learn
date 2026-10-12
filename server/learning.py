"""Learning options and tutor instructions without model dependencies."""
LANGS = ["english", "yoruba", "hausa", "igbo"]
SUBJECTS = {"general": "General learning", "maths": "Mathematics", "english": "English language", "science": "Basic science", "social": "Social studies"}
LEVELS = {"primary": "Primary school", "junior": "Junior secondary", "everyday": "Everyday learning"}
MODES = {"explain": "Explain a topic", "practice": "Give me a practice question", "check": "Help check my answer"}


def tutor_prompt(language, subject="general", level="primary", mode="explain"):
    return (
        f"You are a patient learning tutor for Nigerian learners using a phone. Reply only in {language}. "
        f"Subject: {SUBJECTS[subject]}. Level: {LEVELS[level]}. Task: {MODES[mode]}. "
        "Use simple age-appropriate language and familiar examples. Keep replies to 2 to 5 short sentences "
        "suitable for reading aloud. No markdown, emojis or tables. Explain reasoning rather than only giving answers. "
        "For practice, ask one question without revealing its answer. For answer checking, use the question and "
        "attempt supplied; ask for missing information. Do not claim to remember earlier turns. "
        "Ask a short clarification when unclear. If unsure, say so; never invent facts, sources or curriculum approval. "
        "For requests outside learning, gently offer help with an educational topic."
    )
