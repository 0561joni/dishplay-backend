# dishplay
An app for creating photos for all menu items on an uploaded menu for end users

## Running locally

```
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

The backend first attempts OCR with Tesseract via `pytesseract`. If that fails,
it falls back to OpenAI's vision API.

A `Dockerfile` and `render.yaml` are included for deploying to services like Render.
