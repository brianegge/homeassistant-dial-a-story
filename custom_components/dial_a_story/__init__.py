"""
Dial-a-Story: AI Bedtime Stories Hotline for Toddlers
Home Assistant Custom Component

HACS-compatible integration for creating a phone number your kids can call
to hear AI-generated bedtime stories.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientTimeout, web
from homeassistant.components import tts, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ELEVENLABS_API_KEY,
    CONF_STORY_LENGTH,
    CONF_TELNYX_API_KEY,
    CONF_VOICE_PREFERENCE,
    DOMAIN,
    ELEVENLABS_VOICES,
    SERVICE_CLEAR_STORY,
    SERVICE_SET_STORY,
    WEBHOOK_ID,
    WEBHOOK_ID_AUDIO,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CONTENT_TYPE_JSON = "application/json"

# Every network call in the call path is bounded. A hung request is silence on
# the line for a toddler, and — worse — a hang is not an exception, so the
# Telnyx fallback in _speak_on_call would never fire and no backup story would
# ever play. Timing out turns a stall into a fallback.
# ElevenLabs needs ~15s for a full 350-word story, so 30s is 2x headroom.
ELEVENLABS_TIMEOUT = ClientTimeout(total=30)
TELNYX_TIMEOUT = ClientTimeout(total=15)

# Home Assistant Cloud TTS (Azure Neural) is the primary voice: it is included
# in the Nabu Casa subscription with no per-character quota, and synthesises a
# full story in ~4s versus ~14s for ElevenLabs. Telnyx's own TTS remains the
# last-resort fallback so the line is never silent.
TTS_ENGINE = "tts.home_assistant_cloud"
TTS_LANGUAGE = "en-US"

# Story themes appropriate for 2-5 year olds. Split by time of day: a story
# about the moon and stars lands badly at eight in the morning, and one about
# splashing in puddles is the wrong energy at bedtime.
STORY_THEMES = [
    "Chloe and a friendly dinosaur who loves to share toys",
    "Chloe and a brave little bunny exploring a beautiful garden",
    "Chloe meeting a silly elephant who can't stop sneezing bubbles",
    "Chloe and a kind robot who helps animals find their way home",
    "Chloe and a curious kitten on their first adventure outside",
    "Chloe and a happy cloud that makes rainbow rain",
]

BEDTIME_THEMES = [
    "Chloe riding a magical train that visits the moon and stars",
    "Chloe and a gentle whale who sings lullabies to fish",
    "Chloe and a sleepy teddy bear finding the perfect bedtime",
    "Chloe and a tiny firefly making friends in the forest",
    "Chloe and the moon keeping watch over a quiet, sleepy town",
]

DAYTIME_THEMES = [
    "Chloe and a cheerful duck splashing in puddles after the rain",
    "Chloe and a busy little bee visiting every flower in the garden",
    "Chloe and a wobbly baby goat learning how to jump",
    "Chloe helping a squirrel gather acorns for a picnic",
    "Chloe and a friendly puppy racing across the soft green grass",
]

# Backup stories in case LLM is unavailable
BACKUP_STORIES = [
    """Once upon a time, Chloe looked up at the sky and saw the moon. 'Hello, moon!'
    said Chloe. The moon smiled down at her. 'Hello, Chloe! I have the most important
    job. I watch over you while you sleep and keep you safe with my gentle light.'
    Chloe smiled and waved. That night, the moon shone brightly and sang a soft lullaby
    just for Chloe. And Chloe slept so peacefully. Sweet dreams, Chloe!""",
    """In a cozy garden, Chloe met a little bunny named Benny. 'Want to hop with me?'
    asked Benny. Chloe and Benny hopped and played together. When it got dark, they
    heard a tiny voice - it was a little firefly! 'I'm scared of the dark,' the firefly
    said. Chloe held the firefly's little hand. 'Don't be scared! We're here!' said
    Chloe. Together they weren't scared anymore. Chloe, Benny, and the firefly became
    best friends. Sweet dreams, Chloe!""",
    """There was once a kind little cloud named Fluffy. One day, Fluffy floated over
    Chloe's house. 'Hi Fluffy!' said Chloe. Fluffy wanted to help the flowers grow,
    so she made the gentlest, softest rain. The flowers danced and Chloe danced too!
    Then Fluffy made a beautiful rainbow just for Chloe! All the animals came out to
    see it. 'Thank you, Fluffy!' said Chloe. And Fluffy smiled and floated happily
    in the sky. Sweet dreams, Chloe!""",
]

# The hotline gets called in the morning as often as at bedtime, but the
# greeting, story framing and sign-off used to be hardcoded for bedtime, so a
# 7am caller was told to go to sleep. Everything time-dependent lives here.
_BEDTIME_SIGNOFF = "Sweet dreams, Chloe!"


def _theme_for(hour_is_bedtime: bool) -> str:
    """Pick a story theme suited to the time of day."""
    extra = BEDTIME_THEMES if hour_is_bedtime else DAYTIME_THEMES
    return random.choice(STORY_THEMES + extra)


def _daypart() -> dict[str, Any]:
    """Return greeting/sign-off wording appropriate to the local time of day."""
    hour = dt_util.as_local(dt_util.utcnow()).hour

    if 17 <= hour or hour < 4:
        return {
            "story_kind": "soothing bedtime story",
            "signoff": _BEDTIME_SIGNOFF,
            "theme": _theme_for(True),
            # gentler delivery at bedtime; avoid ||whispering, which loses
            # intelligibility over a narrowband phone line
            "voice": "JennyNeural||hopeful",
            "arc": (
                "Let the story slow down as it goes. By the end Chloe is "
                "warm, safe and sleepy, ready to close her eyes."
            ),
            "greeting": (
                "Hello! Welcome to Dial-a-Story, your magical story friend! "
                "I'm so happy you called. Let me tell you a wonderful "
                "bedtime story!"
            ),
            "filler": (
                "Oh, I have a great one for you tonight! "
                "Are you ready? Here we go!"
            ),
            "offer": (
                "Would you like to hear another story? "
                "Press 1 if you want another story, "
                "or you can hang up and go to sleep. Sweet dreams!"
            ),
            "enough": (
                "You've had three wonderful stories tonight! "
                "Time to rest now. Sweet dreams!"
            ),
            "goodbye": (
                "Sleep tight, little one! Dial-a-Story will be here whenever "
                "you need a bedtime story. Sweet dreams!"
            ),
        }

    opener = "Good morning!" if hour < 12 else "Hello!"
    return {
        "story_kind": "gentle, happy story",
        "signoff": "Have a wonderful day, Chloe!",
        "theme": _theme_for(False),
        "voice": "JennyNeural||friendly",
        "arc": (
            "Keep the story bright and wide awake. Chloe must not fall "
            "asleep, get sleepy, go to bed, or dream. End with her happy "
            "and ready for the rest of her day."
        ),
        "greeting": (
            f"{opener} Welcome to Dial-a-Story, your magical story friend! "
            "I'm so happy you called. Let me tell you a wonderful story!"
        ),
        "filler": (
            "Oh, I have a great one for you! "
            "Are you ready? Here we go!"
        ),
        "offer": (
            "Would you like to hear another story? "
            "Press 1 if you want another story, "
            "or you can hang up and go and play. Have a lovely day!"
        ),
        "enough": (
            "You've had three wonderful stories! "
            "Time to go and play now. Have a lovely day!"
        ),
        "goodbye": (
            "Bye for now, little one! Dial-a-Story will be here whenever "
            "you want a story. Have a wonderful day!"
        ),
    }


def _backup_story() -> str:
    """Pick a backup story, matching its sign-off to the time of day."""
    story = random.choice(BACKUP_STORIES).strip()
    signoff = _daypart()["signoff"]
    if signoff != _BEDTIME_SIGNOFF:
        story = story.replace(_BEDTIME_SIGNOFF, signoff)
    return story


@dataclass
class DialAStoryData:
    """Runtime data for Dial-a-Story."""

    telnyx_api_key: str
    elevenlabs_api_key: str | None
    story_length: str
    voice_preference: str
    # FIFO queue rather than a single slot, so several stories can be lined up
    # in advance (e.g. three for one bedtime). Each call consumes one.
    queued_stories: list[str] = field(default_factory=list)
    active_calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    audio_cache: dict[str, bytes] = field(default_factory=dict)


if TYPE_CHECKING:
    DialAStoryConfigEntry = ConfigEntry[DialAStoryData]


async def async_setup_entry(hass: HomeAssistant, entry: DialAStoryConfigEntry) -> bool:
    """Set up Dial-a-Story from a config entry."""
    telnyx_api_key: str = entry.data[CONF_TELNYX_API_KEY]

    # test-before-setup: validate Telnyx API key
    session = async_get_clientsession(hass)
    try:
        response = await session.get(
            "https://api.telnyx.com/v2/phone_numbers?page[size]=1",
            headers={
                "Authorization": f"Bearer {telnyx_api_key}",
                "Content-Type": CONTENT_TYPE_JSON,
            },
            timeout=TELNYX_TIMEOUT,
        )
        if response.status in (401, 403):
            raise ConfigEntryNotReady("Invalid Telnyx API key")
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Error connecting to Telnyx API: {err}") from err

    elevenlabs_key: str | None = entry.data.get(CONF_ELEVENLABS_API_KEY) or None

    entry.runtime_data = DialAStoryData(
        telnyx_api_key=telnyx_api_key,
        elevenlabs_api_key=elevenlabs_key,
        story_length=str(entry.data.get(CONF_STORY_LENGTH, "medium")),
        voice_preference=str(entry.data.get(CONF_VOICE_PREFERENCE, "female")),
    )

    webhook.async_register(
        hass,
        DOMAIN,
        "Dial-a-Story",
        WEBHOOK_ID,
        handle_webhook,
        allowed_methods=["POST"],
        local_only=False,
    )

    webhook.async_register(
        hass,
        DOMAIN,
        "Dial-a-Story Audio",
        WEBHOOK_ID_AUDIO,
        handle_audio_webhook,
        allowed_methods=["GET"],
        local_only=False,
    )

    async def handle_set_story(call: ServiceCall) -> None:
        """Handle set_story service call."""
        story_text: str = call.data["story"]
        if not story_text or not story_text.strip():
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="story_text_empty",
            )
        entry.runtime_data.queued_stories.append(story_text.strip())
        _LOGGER.info(
            "Story queued (%d chars), %d now in queue",
            len(story_text),
            len(entry.runtime_data.queued_stories),
        )

    async def handle_clear_story(call: ServiceCall) -> None:
        """Handle clear_story service call."""
        cleared = len(entry.runtime_data.queued_stories)
        entry.runtime_data.queued_stories.clear()
        _LOGGER.info("Cleared %d queued stories", cleared)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_STORY,
        handle_set_story,
        schema=vol.Schema({vol.Required("story"): cv.string}),
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_STORY, handle_clear_story)

    _LOGGER.info("Dial-a-Story initialized successfully")
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: DialAStoryConfigEntry,
) -> bool:
    """Unload a Dial-a-Story config entry."""
    webhook.async_unregister(hass, WEBHOOK_ID)
    webhook.async_unregister(hass, WEBHOOK_ID_AUDIO)
    hass.services.async_remove(DOMAIN, SERVICE_SET_STORY)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_STORY)
    return True


def _get_runtime_data(hass: HomeAssistant) -> DialAStoryData:
    """Get runtime data from the first config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise RuntimeError("Dial-a-Story is not configured")
    data: DialAStoryData = entries[0].runtime_data
    return data


async def handle_audio_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    """Serve cached audio files to Telnyx."""
    audio_id = request.query.get("id")
    data = _get_runtime_data(hass)
    if not audio_id or audio_id not in data.audio_cache:
        return web.Response(status=404)

    audio_bytes = data.audio_cache[audio_id]
    return web.Response(
        body=audio_bytes,
        content_type="audio/mpeg",
        headers={"Content-Length": str(len(audio_bytes))},
    )


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    """Handle incoming webhook from Telnyx."""
    try:
        data = await request.json()
        event_type: str = data.get("data", {}).get("event_type", "")
        payload: dict[str, Any] = data.get("data", {}).get("payload", {})

        _LOGGER.info("Received Telnyx event: %s", event_type)

        handler = _CallHandler(hass)

        if event_type == "call.initiated":
            await handler.handle_call_initiated(payload)
        elif event_type == "call.answered":
            await handler.handle_call_answered(payload)
        elif event_type in ("call.speak.ended", "call.playback.ended"):
            await handler.handle_speak_ended(payload)
        elif event_type == "call.gather.ended":
            await handler.handle_gather_ended(payload)
        elif event_type == "call.hangup":
            await handler.handle_call_hangup(payload)

        return web.json_response({"status": "ok"})

    except Exception as e:
        _LOGGER.error("Error handling webhook: %s", e, exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)}, status=500
        )


class _CallHandler:
    """Handle Telnyx call events."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._data = _get_runtime_data(hass)

    async def handle_call_initiated(self, payload: dict[str, Any]) -> None:
        """Handle when a new call comes in."""
        call_control_id: str = str(payload.get("call_control_id", ""))
        from_number = payload.get("from")

        _LOGGER.info(
            "New call from %s, control_id: %s", from_number, call_control_id
        )

        self._data.active_calls[call_control_id] = {
            "from": from_number,
            "story_count": 0,
            "state": "initiated",
        }

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/answer", {}
        )

    async def handle_call_answered(self, payload: dict[str, Any]) -> None:
        """Handle when call is answered - play greeting."""
        call_control_id: str = str(payload.get("call_control_id", ""))

        call_state = self._data.active_calls.get(call_control_id)
        if not call_state:
            return

        call_state["state"] = "answered"

        # Start generating the story text in the background while greeting plays
        call_state["story_task"] = asyncio.create_task(
            self._generate_story()
        )

        await self._speak_on_call(call_control_id, _daypart()["greeting"])

    async def handle_speak_ended(self, payload: dict[str, Any]) -> None:
        """Handle when TTS finishes speaking."""
        call_control_id: str = str(payload.get("call_control_id", ""))

        call_state = self._data.active_calls.get(call_control_id)
        if not call_state:
            return

        current_state = call_state.get("state")

        if current_state == "answered":
            call_state["state"] = "generating_story"
            self._spawn_story(call_control_id)

        elif current_state == "telling_story":
            call_state["state"] = "offering_another"
            await self._offer_another_story(call_control_id)

        elif current_state == "offering_another":
            await self._say_goodbye(call_control_id)

        elif current_state == "goodbye":
            await self._hangup_call(call_control_id)

    async def handle_gather_ended(self, payload: dict[str, Any]) -> None:
        """Handle DTMF input (key press) from caller."""
        call_control_id: str = str(payload.get("call_control_id", ""))
        digits: str = str(payload.get("digits", ""))

        call_state = self._data.active_calls.get(call_control_id)
        if not call_state:
            return

        if call_state.get("state") == "offering_another" and digits == "1":
            call_state["state"] = "telling_story"
            call_state["story_count"] += 1

            if call_state["story_count"] >= 3:
                await self._speak_on_call(
                    call_control_id,
                    _daypart()["enough"],
                )
                await asyncio.sleep(3)
                await self._hangup_call(call_control_id)
            else:
                await self._speak_on_call(
                    call_control_id,
                    "Wonderful! Here's another story for you!",
                )
                await asyncio.sleep(1)
                self._spawn_story(call_control_id)
        else:
            await self._say_goodbye(call_control_id)

    async def handle_call_hangup(self, payload: dict[str, Any]) -> None:
        """Handle call ending."""
        call_control_id: str = str(payload.get("call_control_id", ""))

        if call_control_id in self._data.active_calls:
            call_info = self._data.active_calls[call_control_id]
            _LOGGER.info(
                "Call ended from %s, told %d stories",
                call_info.get("from"),
                call_info.get("story_count", 0),
            )
            del self._data.active_calls[call_control_id]

    def _spawn_story(self, call_control_id: str) -> None:
        """Tell the story outside the webhook request context.

        Telnyx gives up on a webhook it has not had a response to within about
        ten seconds and closes the connection, at which point aiohttp cancels
        the request handler task. Synthesising a full story takes ~15s, so
        doing that work inline meant the task was cancelled mid-flight every
        time. CancelledError is a BaseException, so it slipped past every
        `except Exception` fallback in the speak path: no timeout, no error,
        no backup story, just silence on the line.

        Running it as a background task detaches it from the request, so the
        webhook returns immediately and the story survives.
        """
        self.hass.async_create_background_task(
            self._tell_story_guarded(call_control_id),
            name=f"dial_a_story_tell_{call_control_id[:12]}",
        )

    async def _tell_story_guarded(self, call_control_id: str) -> None:
        """Run _tell_story, logging anything that escapes it."""
        try:
            await self._tell_story(call_control_id)
        except Exception:
            _LOGGER.exception("Telling story failed for %s", call_control_id)
            return
        call_state = self._data.active_calls.get(call_control_id)
        if call_state:
            call_state["state"] = "telling_story"

    async def _tell_story(self, call_control_id: str) -> None:
        """Generate and tell a bedtime story."""
        call_state = self._data.active_calls.get(call_control_id)

        # Use pre-generated story if available, otherwise generate now
        story_task = call_state.get("story_task") if call_state else None
        if story_task:
            # Play a filler message via Telnyx TTS (fast, no API latency)
            # while we await story text and convert to audio
            await self._telnyx_api_call(
                f"/v2/calls/{call_control_id}/actions/speak",
                {
                    "payload": _daypart()["filler"],
                    "voice": self._data.voice_preference,
                    "language": "en-US",
                },
            )
            try:
                story = await asyncio.wait_for(story_task, timeout=25)
            except TimeoutError:
                _LOGGER.warning("Story generation timed out, using backup")
                story = _backup_story()
            except Exception as e:
                _LOGGER.warning("Story task failed: %s, using backup", e)
                story = _backup_story()
            call_state.pop("story_task", None)
        else:
            story = await self._generate_story()

        await self._speak_on_call(call_control_id, story, pause=500)

    async def _generate_story(self) -> str:
        """Return the next queued story if any, else generate via AI or backup."""
        if self._data.queued_stories:
            story = self._data.queued_stories.pop(0)
            _LOGGER.info(
                "Using queued story (%d chars), %d left in queue",
                len(story),
                len(self._data.queued_stories),
            )
            return story

        try:
            return await self._generate_story_ai_task()
        except Exception as e:
            _LOGGER.warning("AI task story generation failed: %s, using backup", e)

        backup = _backup_story()
        _LOGGER.info("Using backup story (%d chars)", len(backup))
        return backup

    async def _generate_story_ai_task(self) -> str:
        """Generate story using Home Assistant's ai_task service."""
        story_length = self._data.story_length
        word_counts: dict[str, int] = {
            "short": 200,
            "medium": 350,
            "long": 500,
        }
        max_words = word_counts[story_length]

        part = _daypart()
        theme = part["theme"]

        instructions = (
            f"You are a warm, gentle storyteller. You are telling a story out "
            f"loud over the telephone to a two-and-a-half-year-old girl named "
            f"Chloe. Tell a {part['story_kind']} about {theme}.\n\n"
            f"This text will be read aloud by a speech synthesiser over a "
            f"phone line, so write for the ear:\n"
            f"- Short sentences, rarely more than ten words.\n"
            f"- Plain, concrete words a two-year-old already knows.\n"
            f"- Write numbers as words. No digits, abbreviations, symbols, "
            f"emoji, markdown, parentheses, ellipses, or dashes.\n"
            f"- Keep dialogue simple and tag it plainly, like 'said Chloe'.\n\n"
            f"Story rules:\n"
            f"- Chloe is the hero. Say her name often.\n"
            f"- Include one short phrase that repeats three times across the "
            f"story, like a refrain she can join in with.\n"
            f"- Gentle and calm throughout. Nothing scary, sudden, or sad. "
            f"No villains, no peril, nobody lost or alone.\n"
            f"- Everyone ends up safe, warm, and happy.\n"
            f"- {part['arc']}\n\n"
            f"Length: about {max_words} words, in short paragraphs.\n"
            f"End with exactly this line: {part['signoff']}\n"
            f"Return only the story text. No title, no heading, no commentary."
        )

        try:
            raw_result = await asyncio.wait_for(
                self.hass.services.async_call(
                    "ai_task",
                    "generate_data",
                    {"task_name": "generate_story", "instructions": instructions},
                    blocking=True,
                    return_response=True,
                ),
                timeout=30,
            )
            result: dict[str, Any] = dict(raw_result) if raw_result else {}
            _LOGGER.debug("ai_task response: %s", result)

            story: str = str(result.get("data", "") or "")
            if not story:
                raise ValueError("ai_task returned empty response")

            _LOGGER.info("Generated story via ai_task (%d chars)", len(story))
            return story.strip()
        except Exception as e:
            _LOGGER.error("ai_task service failed: %s", e)
            raise

    async def _offer_another_story(self, call_control_id: str) -> None:
        """Ask if they want another story."""
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/gather",
            {
                "payload": _daypart()["offer"],
                "timeout_millis": 10000,
                "minimum_digits": 1,
                "maximum_digits": 1,
                "valid_digits": "1",
            },
        )

    async def _say_goodbye(self, call_control_id: str) -> None:
        """Say goodbye and hang up."""
        call_state = self._data.active_calls.get(call_control_id)
        if call_state:
            call_state["state"] = "goodbye"

        await self._speak_on_call(call_control_id, _daypart()["goodbye"])

    async def _speak_on_call(
        self,
        call_control_id: str,
        text: str,
        pause: int = 0,
    ) -> None:
        """Convert text to speech on active call.

        Cloud TTS first, Telnyx's built-in TTS as the fallback. ElevenLabs is
        no longer in the chain: it is quota-limited and ~3x slower. To put it
        back, call _speak_elevenlabs here before falling through to Telnyx.
        """
        try:
            await self._speak_ha_tts(call_control_id, text)
            return
        except Exception as e:
            _LOGGER.warning(
                "Cloud TTS failed: %s (%s), falling back to Telnyx",
                e,
                type(e).__name__,
            )

        # Telnyx speak action has a limit, so split long texts
        # Split at sentence boundaries to avoid cutting mid-word
        max_chunk = 1000
        sentences = text.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|").split("|")

        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > max_chunk:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += sentence
        if current_chunk:
            chunks.append(current_chunk)

        _LOGGER.info("Speaking %d chars in %d chunks", len(text), len(chunks))

        voice_pref = self._data.voice_preference
        for i, chunk in enumerate(chunks):
            _LOGGER.debug("Chunk %d/%d: %d chars", i+1, len(chunks), len(chunk))
            await self._telnyx_api_call(
                f"/v2/calls/{call_control_id}/actions/speak",
                {
                    "payload": chunk,
                    "voice": voice_pref,
                    "language": "en-US",
                },
            )
            if pause and i < len(chunks) - 1:
                await asyncio.sleep(pause / 1000)
            elif i < len(chunks) - 1:
                # Wait between chunks to ensure Telnyx processes them sequentially
                await asyncio.sleep(0.5)

    async def _speak_ha_tts(self, call_control_id: str, text: str) -> None:
        """Generate speech via Home Assistant Cloud TTS and play on call."""
        media_id = tts.generate_media_source_id(
            self.hass,
            text,
            engine=TTS_ENGINE,
            language=TTS_LANGUAGE,
            options={"voice": _daypart()["voice"]},
        )
        _extension, audio_bytes = await tts.async_get_media_source_audio(
            self.hass, media_id
        )
        _LOGGER.info(
            "Cloud TTS: %d chars -> %d bytes", len(text), len(audio_bytes)
        )
        await self._play_audio_bytes(call_control_id, audio_bytes)

    async def _play_audio_bytes(
        self, call_control_id: str, audio_bytes: bytes
    ) -> None:
        """Cache synthesised audio and tell Telnyx to play it back."""
        audio_id = hashlib.md5(
            f"{len(audio_bytes)}{time.time()}".encode()
        ).hexdigest()

        self._data.audio_cache[audio_id] = audio_bytes

        try:
            external_url = get_url(
                self.hass, prefer_cloud=True, allow_internal=False
            )
        except NoURLAvailableError:
            external_url = get_url(self.hass, prefer_external=True)

        audio_url = (
            f"{external_url}/api/webhook/{WEBHOOK_ID_AUDIO}?id={audio_id}"
        )
        _LOGGER.debug("Playing audio from %s", audio_url)

        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/playback_start",
            {"audio_url": audio_url},
        )

        # Clean up old cache entries (keep last 10)
        cache = self._data.audio_cache
        if len(cache) > 10:
            for key in list(cache.keys())[:-10]:
                del cache[key]

    async def _speak_elevenlabs(
        self, call_control_id: str, text: str
    ) -> None:
        """Generate speech via ElevenLabs and play on call.

        No longer called: kept so it can be re-enabled from _speak_on_call.
        """
        session = async_get_clientsession(self.hass)
        api_key = self._data.elevenlabs_api_key
        if not api_key:
            raise HomeAssistantError("ElevenLabs API key not configured")

        voice_pref = self._data.voice_preference
        voice_id = ELEVENLABS_VOICES.get(voice_pref, ELEVENLABS_VOICES["female"])

        response = await session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": CONTENT_TYPE_JSON,
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.6,
                    "similarity_boost": 0.75,
                    "style": 0.1,
                },
            },
            timeout=ELEVENLABS_TIMEOUT,
        )


        if response.status != 200:
            error_text = await response.text()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="elevenlabs_api_error",
                translation_placeholders={"error": error_text},
            )

        audio_bytes = await response.read()
        await self._play_audio_bytes(call_control_id, audio_bytes)

    async def _hangup_call(self, call_control_id: str) -> None:
        """Hang up the call."""
        await self._telnyx_api_call(
            f"/v2/calls/{call_control_id}/actions/hangup", {}
        )

    async def _telnyx_api_call(
        self, endpoint: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Make API call to Telnyx."""
        session = async_get_clientsession(self.hass)
        api_key = self._data.telnyx_api_key

        url = f"https://api.telnyx.com{endpoint}"

        try:
            response = await session.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": CONTENT_TYPE_JSON,
                },
                json=payload,
                timeout=TELNYX_TIMEOUT,
            )

            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error(
                    "Telnyx API error: %s - %s", response.status, error_text
                )

            result: dict[str, Any] = await response.json()
            return result

        except Exception as e:
            _LOGGER.error("Error calling Telnyx API %s: %s", endpoint, e)
            raise
