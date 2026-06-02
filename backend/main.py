from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llm import generate_response

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


@app.post("/generate", response_model=Output)
async def generate(body: Input):

    response = generate_response(body.input)

    return Output(output=response)