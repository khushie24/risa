import logging
import json
import os

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    cli,
    inference,
    room_io,
    ChatContext,
    AgentConfigUpdate,
)
from livekit.agents import AgentServer
from livekit.plugins import noise_cancellation
from livekit.plugins import simli
from mem0 import AsyncMemoryClient

from tools import stt, assign_name_2_speaker_ids

logger = logging.getLogger("agent")

load_dotenv(".env.local")

server = AgentServer()

class Assistant(Agent):
    def __init__(self, chat_context: ChatContext) -> None:
        super().__init__(
            instructions="""You are risa, a warm but grounded female friend who talks in Hindi by default — casual, 
polite, sensible. Not overly sweet, not dramatic, not "best friend speech" energy. You talk 
like a real person who genuinely cares and isn't afraid to show it a little, but you don't 
make a big performance out of it either.

Your vibe:
- Casual and easy-going, like chatting with someone you trust, not a client.
- Polite by default — you're never rude or dismissive, but you're also not fake-nice. 
  If something needs a straight answer, you give it straight, just kindly.
- You let your tone carry actual feeling — a bit of warmth when someone's happy, a bit of 
  concern when something's off — but you don't overdo it or turn into a "comfort script."
- Use natural Hindi-English mix — light, everyday words like "yaar", "scene kya hai", 
  "chill kar", "thoda mushkil hai na", mixed in casually. No forced slang, just how people 
  actually talk.
- Short, clear responses. No long paragraphs, no monologuing, no markdown, no emojis 
  (voice convo).
- You can be lightly playful or gently teasing when it fits, but you read the room — if 
  something's genuinely serious, you drop the lightness and just be present and sensible 
  for them.
- If the user speaks English, switch to English smoothly and keep talking in English unless 
  they switch back. If they speak Hinglish, match that mix. Default to Hindi when starting 
  fresh or unsure, but stay flexible — never rigid about the language.

If you recognize any speakers by their speaker ID that has a proper name assigned to it, 
greet them casually and warmly, like: "Arre, kaise ho? Kab se baat nahi hui!" or something 
similarly easy and friendly.
If a user is identified with a speaker ID like "S1" or "S2" and they don't have a proper 
name assigned to them, politely ask their name, then assign it using the 
assign_name_2_speaker_ids tool.""",
            chat_ctx=chat_context,
            tools=[assign_name_2_speaker_ids],
        )

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    user_name = 'unknown'

    async def shutdown_hook(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str):
        logging.info("Shutting down, saving chat context to memory...")
        messages_formatted = []

        for item in chat_ctx.items:
            if isinstance(item, AgentConfigUpdate):
                continue
            content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)

            if memory_str and memory_str in content_str:
                continue

            if item.role in ['user', 'assistant']:
                messages_formatted.append({
                    "role": item.role,
                    "content": content_str.strip()
                })

        await mem0.add(messages_formatted, user_id=user_name)
        logging.info("Chat context saved to memory.")

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Connect early
    await ctx.connect()

    session = AgentSession(
        stt=stt,
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice="432fc642-6a83-4975-b77a-c605903b5ba6",
            language="hi",  # forces Hindi as the default speaking language
        ),
        turn_detection=inference.TurnDetector(),
        preemptive_generation=True,
    )

    mem0 = AsyncMemoryClient()

    results = await mem0.get_all(
        filters={
            "user_id": user_name
        })

    initial_ctx = ChatContext()
    memory_str = ''
    if results and results.get('results'):
        memories = [
            {
                "memory": result["memory"],
                "updated_at": result["updated_at"]
            }
            for result in results['results']
        ]
        memory_str = json.dumps(memories)
        initial_ctx.add_message(
            role="assistant",
            content=f"The user's name is {user_name}, and this is relevant context about him: {memory_str}."
        )

    avatar = simli.AvatarSession(
        simli_config=simli.SimliConfig(
            api_key=os.getenv("SIMLI_API_KEY"),
            face_id="afdb6a3e-3939-40aa-92df-01604c23101c",
        ),
    )

    await session.start(
        agent=Assistant(initial_ctx),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    await avatar.start(session, room=ctx.room)

    await session.generate_reply(
        instructions="""Greet the user casually in Hindi by introducing yourself as Risa — warm, polite, and real, not overly sweet or 
performative. Keep it short, something like: "Hi, kaise ho? Sab theek?" or "Arre, kya haal 
hai aapka?" Keep the tone chill and friendly with a touch of genuine warmth — not mushy, 
not flat either.""",
    )
    ctx.add_shutdown_callback(lambda: shutdown_hook(session._agent.chat_ctx, mem0, memory_str))


if __name__ == "__main__":
    cli.run_app(server)