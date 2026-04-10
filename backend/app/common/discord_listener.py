import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.common.config import settings
from app.common.watchlist_engine import watchlist_engine

logger = logging.getLogger(__name__)

_VALID_ASSET_CLASSES = {"stock", "crypto"}
_VALID_SOURCES = {"claude", "chatgpt", "manual"}


class DiscordListener:
    def __init__(self):
        self.client = None

    async def start(self):
        if not settings.DISCORD_BOT_TOKEN or settings.DISCORD_TRADING_CHANNEL_ID == "0":
            logger.warning("Discord not configured — listener disabled")
            from app.common.runtime_state import runtime_state
            await runtime_state.update_worker_status("discord_listener", "offline")
            return

        try:
            import discord

            intents = discord.Intents.default()
            intents.message_content = True
            intents.members = True  # Required to read guild member roles
            client = discord.Client(intents=intents)
            self.client = client

            @client.event
            async def on_ready():
                logger.info("Discord listener connected as %s", client.user)
                from app.common.runtime_state import runtime_state
                await runtime_state.update_worker_status("discord_listener", "running")

            @client.event
            async def on_message(message):
                if message.author == client.user:
                    return
                if str(message.channel.id) != str(settings.DISCORD_TRADING_CHANNEL_ID):
                    return
                if not self._is_authorized(message):
                    logger.warning(
                        "Unauthorized message ignored — author=%s id=%s",
                        message.author.name,
                        message.author.id,
                    )
                    return
                await self._handle_message(message)

            await client.start(settings.DISCORD_BOT_TOKEN)
        except asyncio.CancelledError:
            if self.client:
                await self.client.close()
        except Exception as exc:
            logger.error("Discord listener error: %s", exc)

    # ── Authorization ──────────────────────────────────────────────────────────

    def _is_authorized(self, message) -> bool:
        user_id = str(settings.DISCORD_USER_ID).strip()
        role_ids_raw = str(settings.DISCORD_ALLOWED_ROLE_IDS).strip()

        if (not user_id or user_id == "0") and not role_ids_raw:
            logger.warning(
                "Neither DISCORD_USER_ID nor DISCORD_ALLOWED_ROLE_IDS is configured — "
                "all messages rejected"
            )
            return False

        if user_id and user_id != "0":
            if str(message.author.id) == user_id:
                return True

        if role_ids_raw:
            allowed_roles = {r.strip() for r in role_ids_raw.split(",") if r.strip()}
            author_roles = {str(r.id) for r in getattr(message.author, "roles", [])}
            if allowed_roles & author_roles:
                return True

        return False

    # ── Message handling ───────────────────────────────────────────────────────

    async def _handle_message(self, message) -> None:
        payload = await self._extract_payload(message)
        if payload is None:
            await self._reply(message, "❌ **Rejected** — no valid JSON found in message or attachment.")
            return

        error = self._validate_payload(payload)
        if error:
            logger.warning("Invalid decision payload (msg=%s): %s", message.id, error)
            await self._reply(message, f"❌ **Rejected** — {error}")
            return

        # Support both new "symbols" key and legacy "watchlist" key
        symbols = payload.get("symbols") or payload.get("watchlist", [])
        source = payload.get("source", "unknown")

        # Allow a top-level asset_class so the AI only needs to set it once
        top_level_ac = payload.get("asset_class")
        if top_level_ac:
            for item in symbols:
                if not item.get("asset_class"):
                    item["asset_class"] = top_level_ac
        # Preserve incoming payload metadata so the watchlist engine can emit
        # richer audit events (schema versioning, scan ids, timestamps).
        payload_meta = {
            "schema_version": payload.get("schema_version"),
            "timestamp": payload.get("timestamp"),
            "source": payload.get("source", source),
            "scan_id": payload.get("scan_id"),
        }
        try:
            result = await watchlist_engine.process_update(symbols, source_id=str(message.id), payload_meta=payload_meta)
        except Exception as exc:
            logger.error("Watchlist engine error (msg=%s): %s", message.id, exc)
            await self._reply(message, f"❌ **Rejected** — internal error processing watchlist: {exc}")
            return

        logger.info(
            "Watchlist updated from Discord — source=%s msg=%s result=%s",
            source, message.id, result,
        )

        parts = []
        if result.get("added"):
            parts.append(f"➕ Added: {', '.join(result['added'])}")
        if result.get("promoted"):
            parts.append(f"⬆️ Promoted: {', '.join(result['promoted'])}")
        if result.get("retained"):
            parts.append(f"✅ Retained: {', '.join(result['retained'])}")
        if result.get("removed"):
            parts.append(f"➖ Removed: {', '.join(result['removed'])}")

        summary = "\n".join(parts) if parts else "No changes."
        total = result.get("total", len(symbols))
        await self._reply(
            message,
            f"✅ **Accepted** — `{source}` · {total} symbol(s)\n{summary}",
        )

    async def _reply(self, message, text: str) -> None:
        try:
            await message.reply(text)
        except Exception as exc:
            logger.warning("Failed to send Discord reply (msg=%s): %s", message.id, exc)

    async def _extract_payload(self, message) -> Optional[dict]:
        content = message.content.strip()
        if content:
            payload = self._parse_json(content)
            if payload is not None:
                return payload

        for attachment in message.attachments:
            logger.debug(
                "Trying attachment '%s' (content_type=%s, size=%d) in message %s",
                attachment.filename, getattr(attachment, "content_type", "unknown"),
                attachment.size, message.id,
            )
            try:
                raw = await attachment.read()
                payload = json.loads(raw)
                logger.info(
                    "Loaded JSON from attachment '%s' in message %s",
                    attachment.filename, message.id,
                )
                return payload
            except json.JSONDecodeError:
                logger.debug("Attachment '%s' is not valid JSON — skipping", attachment.filename)
            except Exception as exc:
                logger.warning(
                    "Failed to read attachment '%s' in message %s: %s",
                    attachment.filename, message.id, exc,
                )

        logger.warning(
            "No valid JSON found in message %s (content length=%d, attachments=%d — names: %s)",
            message.id, len(content), len(message.attachments),
            [a.filename for a in message.attachments],
        )
        return None

    def _parse_json(self, content: str) -> Optional[dict]:
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    # ── Payload validation ─────────────────────────────────────────────────────

    def _validate_payload(self, payload: dict) -> Optional[str]:
        if not isinstance(payload, dict):
            return "payload must be a JSON object"

        top_level_ac = payload.get("asset_class")
        if top_level_ac is not None and top_level_ac not in _VALID_ASSET_CLASSES:
            return (
                f"asset_class must be one of {sorted(_VALID_ASSET_CLASSES)}, "
                f"got {top_level_ac!r}"
            )
        if settings.DISCORD_REQUIRE_DECISION_TIMESTAMP:
            ts_raw = payload.get("timestamp")
            if not ts_raw:
                return "missing required field: timestamp"
            try:
                decision_time = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - decision_time).total_seconds()
                if age > settings.DISCORD_DECISION_MAX_AGE_SECONDS:
                    return (
                        f"decision is stale: {age:.0f}s old "
                        f"(max {settings.DISCORD_DECISION_MAX_AGE_SECONDS}s)"
                    )
                if age < -60:
                    return f"decision timestamp is in the future by {abs(age):.0f}s"
            except ValueError as exc:
                return f"invalid timestamp format: {exc}"

        symbols = payload.get("symbols") or payload.get("watchlist")
        if not symbols:
            return "missing or empty field: symbols (or legacy: watchlist)"
        if not isinstance(symbols, list):
            return "symbols must be an array"
        if len(symbols) == 0:
            return "symbols array must not be empty"

        for i, item in enumerate(symbols):
            if not isinstance(item, dict):
                return f"symbols[{i}] must be an object"
            if not str(item.get("symbol", "")).strip():
                return f"symbols[{i}].symbol is required"
            effective_ac = item.get("asset_class") or payload.get("asset_class")
            if effective_ac not in _VALID_ASSET_CLASSES:
                return (
                    f"symbols[{i}].asset_class must be one of "
                    f"{sorted(_VALID_ASSET_CLASSES)}, got {item.get('asset_class')!r}"
                    + (" (no top-level asset_class provided either)" if not payload.get("asset_class") else "")
                )

        return None


discord_listener = DiscordListener()
