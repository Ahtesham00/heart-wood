import asyncio
from sse_starlette.sse import EventSourceResponse

async def gen():
    yield '{"type": "text"}'
    yield {"data": '{"type": "text"}'}

import uvicorn
from fastapi import FastAPI
app = FastAPI()
@app.get("/")
def get():
    return EventSourceResponse(gen())

