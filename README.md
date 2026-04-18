# Backend — Voice Expense API

A minimal FastAPI backend that accepts an audio recording, transcribes it with OpenAI Whisper, extracts expense entities with GPT, and returns structured JSON.

The extraction prompt and JSON schema live in `backend/main.py` (`EXPENSE_PARSER_SYSTEM_PROMPT` and `EXTRACTION_SCHEMA`).

## Local development

```bash
cd backend

# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your OpenAI key
export OPENAI_API_KEY="sk-..."

# 4. Start the server
uvicorn main:app --reload --port 8000
```

Test it with curl:
```bash
curl -X POST http://localhost:8000/voice-expense \
  -F "audio=@/path/to/your/recording.m4a"
```

Expected response:
```json
{
  "transcript": "paid 300 to zomato by UPI",
  "amount": "300",
  "merchant": "Zomato",
  "payment_mode": "UPI",
  "payment_source": "NA",
  "category": "Food",
  "comment": "Paid 300 to Zomato"
}
```

---

## Deploy to Railway (free)

1. **Sign up** at [railway.app](https://railway.app) (free $5/month credit, no credit card needed)

2. **Install Railway CLI** (optional — you can also use their GitHub integration):
   ```bash
   brew install railway
   ```

3. **Login and deploy**:
   ```bash
   cd backend
   railway login
   railway init        # creates a new project
   railway up          # deploys the backend
   ```

4. **Set your environment variable** in the Railway dashboard:
   - Go to your project → Variables
   - Add `OPENAI_API_KEY` = `sk-...`

5. **Get your public URL** from the Railway dashboard (looks like `https://xxx.up.railway.app`)

6. **Update the app** — open `src/ExpenseTrackerApp.tsx` and change:
   ```typescript
   const VOICE_API_URL = "https://YOUR_APP.up.railway.app/voice-expense";
   //                      ↑ replace with your actual Railway URL
   ```

---

## Why not Vercel?

Vercel's free tier has a **10-second execution timeout** and **4.5MB request payload limit**. OpenAI Whisper + GPT together commonly take 12–20 seconds, so Vercel will time out. Railway has no timeout on HTTP responses.
