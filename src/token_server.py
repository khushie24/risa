import logging
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# YEH ADD KAR — correct path
load_dotenv(Path(__file__).parent.parent / ".env.local")

from fastapi import FastAPI
from livekit.api import AccessToken, VideoGrants, LiveKitAPI
from livekit.api.agent_dispatch_service import CreateAgentDispatchRequest

app = FastAPI()

@app.get("/get-token")
async def get_token():
    room_name = f"room-{os.urandom(4).hex()}"
    
    token = AccessToken(
    api_key=os.getenv("LIVEKIT_API_KEY"),
    api_secret=os.getenv("LIVEKIT_API_SECRET")
).with_identity("android-user") \
 .with_grants(VideoGrants(
    room_join=True,
    room=room_name
)).to_jwt() 
    
    lkapi = LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET")
    )
    await lkapi.agent_dispatch.create_dispatch(
        CreateAgentDispatchRequest(
            agent_name="my-agent",
            room=room_name
        )
    )

    return {
        "token": token,
        "url": os.getenv("LIVEKIT_URL"),
        "room": room_name
    }