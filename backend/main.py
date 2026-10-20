import base64
import json
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import httpx

from config import settings, setup_logging
from assistant import assistant_service
from synthesize import synthesize
from profile import load_profile
from memory import load_memories
from tts import stream_tts, stream_sentence_audio
from news import fetch_headlines
from websearch import web_context

setup_logging()
logger = logging.getLogger("afsar.api")

app = FastAPI(title="AFSAR Assistant API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


class ChatInput(BaseModel):
    input: str
    history: list = []
    conversation_id: str | None = None


class Output(BaseModel):
    output: str
    conversation_id: str | None = None


class CreateConversationInput(BaseModel):
    title: str = "New Conversation"


class UpdateConversationInput(BaseModel):
    title: str


class SynthesizeInput(BaseModel):
    input: str


class TTSInput(BaseModel):
    text: str


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "env": settings.ENV,
    }


@app.get("/health/ready")
async def health_ready(response: Response):
    readiness = {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama": {
            "status": "unknown",
            "url": settings.OLLAMA_URL,
            "model": settings.MODEL_NAME,
            "model_available": False,
        },
        "storage": {
            "status": "ok",
            "data_dir": str(settings.DATA_DIR),
            "writable": False,
        },
    }

    # 1. Verify storage
    try:
        test_file = settings.DATA_DIR / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        readiness["storage"]["writable"] = True
    except Exception as e:
        readiness["storage"]["status"] = f"error: {e}"
        readiness["status"] = "degraded"

    # 2. Verify Ollama & Model availability
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                model_matches = any(
                    settings.MODEL_NAME in m or m.startswith(settings.MODEL_NAME)
                    for m in models
                )
                readiness["ollama"]["status"] = "ok"
                readiness["ollama"]["model_available"] = model_matches
                if not model_matches:
                    readiness["status"] = "degraded"
                    readiness["ollama"]["warning"] = f"Configured model '{settings.MODEL_NAME}' not found in installed models"
            else:
                readiness["ollama"]["status"] = f"unexpected_status_{res.status_code}"
                readiness["status"] = "degraded"
    except Exception as e:
        readiness["ollama"]["status"] = f"unreachable: {e}"
        readiness["status"] = "degraded"

    if readiness["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return readiness


@app.post("/generate", response_model=Output)
async def generate(body: ChatInput):
    result = assistant_service.chat(
        user_input=body.input,
        conversation_id=body.conversation_id,
        client_history=body.history,
    )
    return Output(
        output=result["output"],
        conversation_id=result.get("conversation_id"),
    )


@app.post("/generate/stream")
async def generate_stream(body: ChatInput):
    async def event_stream():
        for token in assistant_service.chat_stream(
            user_input=body.input,
            conversation_id=body.conversation_id,
            client_history=body.history,
        ):
            if token:
                yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True, 'conversation_id': body.conversation_id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/conversations")
async def get_conversations(limit: int = 50, offset: int = 0):
    return {"conversations": assistant_service.list_conversations(limit=limit, offset=offset)}


@app.post("/conversations")
async def create_new_conversation(body: CreateConversationInput):
    conv = assistant_service.create_conversation(title=body.title)
    return {"conversation": conv}


@app.get("/conversations/{conv_id}")
async def get_conversation_details(conv_id: str):
    conv = assistant_service.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = assistant_service.get_messages(conv_id)
    return {"conversation": conv, "messages": messages}


@app.patch("/conversations/{conv_id}")
async def update_conversation_title_route(conv_id: str, body: UpdateConversationInput):
    import db
    success = db.update_conversation_title(conv_id, body.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", "title": body.title}


@app.delete("/conversations/{conv_id}")
async def delete_conversation_route(conv_id: str):
    success = assistant_service.delete_conversation(conv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", "deleted": conv_id}



@app.get("/tts")
async def text_to_speech(text: str):
    return StreamingResponse(
        stream_tts(text),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "Content-Disposition": "inline",
        },
    )


@app.post("/tts/stream")
async def text_to_speech_stream(body: TTSInput):
    async def event_stream():
        async for segment in stream_sentence_audio(body.text):
            audio = base64.b64encode(segment).decode("ascii")
            yield f"data: {json.dumps({'audio': audio})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/data")
async def get_data():
    return {
        "profile": load_profile(),
        "memories": load_memories(),
    }


@app.post("/synthesize")
async def synthesize_endpoint(body: SynthesizeInput):
    return synthesize(body.input)


@app.get("/news")
def get_news():
    return {"headlines": fetch_headlines()}


@app.get("/search")
def search_endpoint(q: str):
    return {"query": q, "context": web_context(q)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=(settings.ENV == "development"))

