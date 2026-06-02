from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_ollama import OllamaLLM

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = OllamaLLM(model="qwen2.5:1.5b")


class Input(BaseModel):
    input: str


class Output(BaseModel):
    output: str


@app.post("/generate", response_model=Output)
async def generate(body: Input):
    result = model.invoke(body.input)
    return Output(output=result)
