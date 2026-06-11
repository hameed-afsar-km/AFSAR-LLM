from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llm import generate_response
from synthesize import synthesize
from profile import load_profile
from memory import load_memories

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Input(BaseModel):
    input: str


class Output(BaseModel):
    output: str


class SynthesizeInput(BaseModel):
    input: str


@app.post("/generate", response_model=Output)
async def generate(body: Input):
    response = generate_response(body.input)
    return Output(output=response)


@app.get("/data")
async def get_data():
    return {
        "profile": load_profile(),
        "memories": load_memories(),
    }


@app.post("/synthesize")
async def synthesize_endpoint(body: SynthesizeInput):
    return synthesize(body.input)