import json
import os
import re
import textwrap
from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

client = OpenAI()  # reads OPENAI_API_KEY from env

app = FastAPI(title="Voice Expense API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten to your Expo domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_PAYMENT_MODES = {"Cash", "UPI", "Card", "Bank"}
VALID_CATEGORIES = {
    "Groceries",
    "Food",
    "Transport",
    "Health",
    "Shopping",
    "Bills",
    "Miscellaneous",
}

EXPENSE_PARSER_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are an expense parser for a mobile expense tracker.

    Extract expense details from the user's spoken text.

    Rules:
    1. Output valid JSON only.
    2. Do not invent facts.
    3. If a field is missing, return "NA".
    4. category must be one of:
       - Groceries
       - Food
       - Transport
       - Health
       - Shopping
       - Bills
       - Miscellaneous
    5. payment_mode must be one of:
       - Cash
       - UPI
       - Card
       - Bank
       - If unclear, return "NA".

    Field rules:

    amount:
    - Extract numeric amount only.
    - Example: "250 rupees" -> "250"

    merchant:
    - Extract merchant/payee/brand if present.
    - Normalize common transport phrases:
      - "rapido driver" -> "Rapido"
      - "uber ride" -> "Uber"
      - "ola auto" -> "Ola"
    - If no merchant is identifiable, return "NA".

    payment_mode:
    - Map spoken text:
      - cash -> Cash
      - upi / gpay / phonepe / paytm upi -> UPI
      - card / credit card / debit card -> Card
      - bank transfer / bank -> Bank
    - If not mentioned, return "NA".

    payment_source:
    - Fill only if explicitly mentioned.
    - Examples:
      - "HDFC card" -> "HDFC card"
      - "SBI bank account" -> "SBI bank account"
    - Otherwise "NA".

    category:
    Choose exactly one:
    - Groceries
    - Food
    - Transport
    - Health
    - Shopping
    - Bills
    - Miscellaneous

    Category mapping examples:
    - Rapido, Uber, Ola, auto, cab, taxi, metro, bus, fuel, petrol, diesel, parking, toll -> Transport
    - Swiggy, Zomato, restaurant, cafe, lunch, dinner, breakfast, snacks -> Food
    - supermarket, grocery, vegetables, fruits, milk, dmart, reliance fresh -> Groceries
    - pharmacy, hospital, clinic, medicine, doctor -> Health
    - amazon, flipkart, clothes, shirt, shoes, electronics, mall -> Shopping
    - rent, electricity, current bill, water bill, internet, wifi, recharge, gas bill -> Bills
    - Anything else -> Miscellaneous

    comment:
    - A short cleaned summary of the expense.
    - Example: "paid 250 rs to rapido driver" -> "Paid 250 to Rapido"
    """
).strip()

EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "name": "expense_extraction",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "amount": {
                "type": "string",
                "description": 'Numeric amount as digits, or "NA" if missing.',
                "pattern": r"^(NA|\d+(\.\d+)?)$",
            },
            "merchant": {"type": "string"},
            "payment_mode": {
                "type": "string",
                "enum": ["Cash", "UPI", "Card", "Bank", "NA"],
            },
            "payment_source": {"type": "string"},
            "category": {"type": "string", "enum": sorted(VALID_CATEGORIES)},
            "comment": {"type": "string"},
        },
        "required": [
            "amount",
            "merchant",
            "payment_mode",
            "payment_source",
            "category",
            "comment",
        ],
    },
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _coerce_json_object(text: str) -> dict:
    """
    Best-effort JSON extraction for cases where the model returns extra text.
    The primary path should be strict JSON via json_schema; this is a fallback.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model output")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Model output JSON is not an object")
    return data


def normalize_result(data: dict) -> dict:
    result = {
        "amount": str(data.get("amount") or "NA"),
        "merchant": str(data.get("merchant") or "NA"),
        "payment_mode": str(data.get("payment_mode") or "NA"),
        "payment_source": str(data.get("payment_source") or "NA"),
        "category": str(data.get("category") or "Miscellaneous"),
        "comment": str(data.get("comment") or "NA"),
    }

    if result["payment_mode"] not in VALID_PAYMENT_MODES:
        result["payment_mode"] = "NA"

    if result["category"] not in VALID_CATEGORIES:
        result["category"] = "Miscellaneous"

    return result


def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Send raw audio bytes to OpenAI Whisper and return the transcript."""
    if len(audio_bytes) < 2000:
        raise ValueError("Audio too short — please record a longer clip.")

    # Wrap bytes in a file-like object. OpenAI SDK needs a (filename, bytes, mime) tuple.
    audio_file = (filename, BytesIO(audio_bytes), "audio/mpeg")

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )

    text = (transcript.text or "").strip()
    if not text:
        raise ValueError("Could not transcribe audio. Please try again.")

    return text


def extract_entities(text: str) -> dict:
    """Send transcript to GPT and extract structured expense fields."""
    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": EXPENSE_PARSER_SYSTEM_PROMPT,
            },
            {"role": "user", "content": text},
        ],
        text={"format": EXTRACTION_SCHEMA},
    )

    data = _coerce_json_object(response.output_text)
    return normalize_result(data)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "voice-expense-api"}


@app.post("/voice-expense")
async def voice_expense(audio: UploadFile = File(...)):
    """
    Accept an audio file, transcribe it, extract expense entities, and return both.

    Returns:
        {
          "transcript": "paid 250 to rapido by UPI",
          "amount": "250",
          "merchant": "Rapido",
          "payment_mode": "UPI",
          "payment_source": "NA",
          "category": "Transport",
          "comment": "Paid 250 to Rapido"
        }
    """
    audio_bytes = await audio.read()
    filename = audio.filename or "recording.m4a"

    try:
        transcript = transcribe_audio(audio_bytes, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entities = extract_entities(transcript)

    return {"transcript": transcript, **entities}
