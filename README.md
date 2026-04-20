# Voice Expense API (Backend)

FastAPI backend that accepts an audio recording, transcribes it with OpenAI, extracts expense entities, and returns structured JSON.

## API

- `GET /` → health check
- `POST /voice-expense` → `multipart/form-data` with field `audio`

Response example:
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

## Environment variables

- `OPENAI_API_KEY` (required)

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

export OPENAI_API_KEY="sk-..."
uvicorn main:app --reload --port 8000
```

Test:
```bash
curl -X POST http://localhost:8000/voice-expense \
  -F "audio=@/path/to/your/recording.m4a"
```

Health:
```bash
curl http://localhost:8000/
```

## Deploy (Railway)

This repo includes `railway.toml` (Nixpacks build + `uvicorn` start command).

1. Create a Railway project (via GitHub integration or CLI).
2. Set `OPENAI_API_KEY` in Railway → Variables.
3. Deploy.
4. Verify:
   - `https://YOUR_APP.up.railway.app/` returns `{"status":"ok"...}`
   - `https://YOUR_APP.up.railway.app/docs` loads FastAPI docs

## Connect the frontend

In the Netlify site for the frontend, set:

- `EXPO_PUBLIC_VOICE_API_URL` = `https://YOUR_APP.up.railway.app/voice-expense`

Then redeploy the frontend.

## Production notes

- CORS is currently open (`allow_origins=["*"]`). Tighten it to your Netlify domain when you’re ready.
- Keep `OPENAI_API_KEY` on the server only.
