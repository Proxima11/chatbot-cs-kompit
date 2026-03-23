from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.preprocessing import LabelEncoder
import json
import os
import pandas as pd

app = FastAPI(title="Chatbot NLP Backend")

# Allow cors so the Next.js frontend on localhost:3000 can access it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use absolute paths so uvicorn/startup doesn't break relative resolution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
MODEL_PATH = os.path.join(PROJECT_DIR, "app", "src", "app", "model")
DATASET_PATH = os.path.join(PROJECT_DIR, "dataset")
TOKENIZER_NAME = "indobenchmark/indobert-base-p1"

# Globals
tokenizer = None
model = None
intent_to_answer = {}
label_encoder = None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: str
    confidence: float


def load_knowledge_base():
    """Loads all JSON datasets and builds label_encoder + intent_to_answer mapping."""
    global intent_to_answer, label_encoder

    all_data = []

    if not os.path.exists(DATASET_PATH):
        print(f"Warning: Dataset directory not found: {DATASET_PATH}")
        return

    for filename in os.listdir(DATASET_PATH):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(DATASET_PATH, filename)
        if os.path.getsize(filepath) == 0:
            print(f"Skipping empty file: {filename}")
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            items = data.get("data", [])
            if isinstance(items, list):
                for item in items:
                    q = item.get("question", "").strip()
                    intent = item.get("intent", "").strip()
                    answer = item.get("answer", "").strip()
                    if q and intent and answer:
                        all_data.append({"query": q, "intent": intent, "answer": answer})
            print(f"Loaded {filename}: {len(items)} items")
        except Exception as e:
            print(f"Error loading {filename}: {e}")

    df = pd.DataFrame(all_data)
    if len(df) == 0:
        print("Warning: No data loaded from datasets.")
        return

    label_encoder = LabelEncoder()
    label_encoder.fit(df["intent"])

    for _, row in df.iterrows():
        intent = row["intent"]
        if intent not in intent_to_answer:
            intent_to_answer[intent] = row["answer"]

    print(f"Knowledge base ready: {len(intent_to_answer)} unique intents loaded.")


@app.on_event("startup")
async def startup_event():
    global tokenizer, model

    print(f"Loading knowledge base from: {DATASET_PATH}")
    load_knowledge_base()

    print(f"Loading tokenizer: {TOKENIZER_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)

    print(f"Loading model from: {MODEL_PATH}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
    model.to(device)
    model.eval()
    print(f"Startup complete. Model on device: {device}")


@app.post("/predict", response_model=ChatResponse)
async def predict_intent(request: ChatRequest):
    if model is None or tokenizer is None or label_encoder is None:
        raise HTTPException(status_code=503, detail="Model not initialized.")

    query = request.message.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty message.")

    # Tokenize
    inputs = tokenizer(
        query, return_tensors="pt", truncation=True, padding=True, max_length=128
    )
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Inference
    with torch.no_grad():
        outputs = model(**inputs)
        probs = F.softmax(outputs.logits, dim=1)

    predicted_class_id = torch.argmax(probs, dim=1).item()
    confidence = probs[0][predicted_class_id].item()

    # Decode intent label
    try:
        predicted_intent = label_encoder.inverse_transform([predicted_class_id])[0]
    except Exception:
        predicted_intent = model.config.id2label.get(str(predicted_class_id), "unknown")

    # Low confidence fallback
    if confidence < 0.4:
        fallback = "Maaf, saya kurang mengerti maksud Anda. Silakan coba gunakan kalimat yang lebih spesifik."
        return ChatResponse(reply=fallback, intent=predicted_intent, confidence=confidence)

    # Retrieve answer from knowledge base
    answer = intent_to_answer.get(
        predicted_intent,
        "Mohon maaf, jawaban untuk pertanyaan ini belum ada di sistem kami.",
    )

    return ChatResponse(reply=answer, intent=predicted_intent, confidence=confidence)


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None, "intents": len(intent_to_answer)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
