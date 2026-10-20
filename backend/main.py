import base64
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from llm import generate_response, generate_response_stream
from synthesize import synthesize
from profile import load_profile
from memory import load_memories
from tts import stream_tts, stream_sentence_audio
from news import fetch_headlines
from websearch import web_context

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatInput(BaseModel):
    input: str
    history: list = []


class Output(BaseModel):
    output: str


class SynthesizeInput(BaseModel):
    input: str


@app.post("/generate", response_model=Output)
async def generate(body: ChatInput):
    response = generate_response(body.input, body.history)
    return Output(output=response)


@app.post("/generate/stream")
async def generate_stream(body: ChatInput):
    async def event_stream():
        for token in generate_response_stream(body.input, body.history):
            if token:
                yield f"data: {json.dumps({'token': token})}\n\n"
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


class TTSInput(BaseModel):
    text: str


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
