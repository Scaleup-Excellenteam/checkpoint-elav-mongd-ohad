import asyncio
from functools import partial
import json
import logging
from websockets.asyncio.server import serve
from .anti_bot import AntiBotService
from .database import MessageRepository
from .discovery import register_server, unregister_server
from .logging_config import configure_logging, log_event
from .moderation import DLPService
from .rooms import add_client, get_clients, get_rooms, remove_client, room_exists


PORT = 8765
logger = configure_logging()


def get_remote_address(websocket):
    remote_address = websocket.remote_address
    if isinstance(remote_address, tuple):
        return f"{remote_address[0]}:{remote_address[1]}"
    return str(remote_address)


async def choose_room(websocket, username):
    while True:
        await websocket.send(json.dumps({"type": "rooms", "rooms": get_rooms()}))
        request = json.loads(await websocket.recv())

        action = request.get("action")
        room = str(request.get("room", "")).strip().casefold()

        if not room:
            log_event(logger, logging.WARNING, "ROOM_REJECTED", username=username, reason="ROOM_NAME_REQUIRED")
            await websocket.send(json.dumps({"type": "error", "message": "Room name is required"}))
        elif action == "create_room" and room_exists(room):
            log_event(logger, logging.WARNING, "ROOM_REJECTED", username=username, room=room, reason="ROOM_EXISTS")
            await websocket.send(json.dumps({"type": "error", "message": "Room already exists"}))
        elif action == "join_room" and not room_exists(room):
            log_event(logger, logging.WARNING, "ROOM_REJECTED", username=username, room=room, reason="ROOM_NOT_FOUND")
            await websocket.send(json.dumps({"type": "error", "message": "Room does not exist"}))
        elif action not in {"create_room", "join_room"}:
            log_event(logger, logging.WARNING, "ROOM_REJECTED", username=username, reason="INVALID_ACTION")
            await websocket.send(json.dumps({"type": "error", "message": "Invalid room action"}))
        else:
            add_client(room, websocket)
            await websocket.send(json.dumps({"type": "joined", "room": room}))
            event = "ROOM_CREATED" if action == "create_room" else "ROOM_JOINED"
            log_event(logger, logging.INFO, event, username=username, room=room)
            return room


async def handle_client(
    websocket,
    message_repository=None,
    moderation_service=None,
    anti_bot_service=None,
):
    remote_address = get_remote_address(websocket)
    username = None
    room = None
    log_event(logger, logging.INFO, "CLIENT_CONNECTED", remote_address=remote_address)

    try:
        username = (await websocket.recv()).strip()
        room = await choose_room(websocket, username)

        async for message in websocket:
            if anti_bot_service is not None:
                rate_limit = anti_bot_service.check_message(websocket)
                if not rate_limit.allowed:
                    log_event(
                        logger,
                        logging.WARNING,
                        "ANTIBOT_MESSAGE_REJECTED",
                        username=username,
                        room=room,
                        retry_after_seconds=rate_limit.retry_after_seconds,
                    )
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "RATE_LIMITED",
                                "message": "You are sending messages too quickly",
                                "retryAfterSeconds": rate_limit.retry_after_seconds,
                            }
                        )
                    )
                    continue

            if moderation_service is not None:
                try:
                    moderation_result = await moderation_service.check_message(
                        repository=message_repository,
                        sender=username,
                        room=room,
                        content=message,
                    )
                except Exception as error:
                    log_event(
                        logger,
                        logging.ERROR,
                        "DLP_CHECK_FAILED",
                        username=username,
                        room=room,
                        error_type=type(error).__name__,
                    )
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "DLP_UNAVAILABLE",
                                "message": "Message blocked because the security check is unavailable",
                            }
                        )
                    )
                    continue

                if moderation_result.checked_by_llm:
                    log_event(
                        logger,
                        logging.WARNING if not moderation_result.allowed else logging.INFO,
                        "DLP_DECISION",
                        username=username,
                        room=room,
                        decision="allowed" if moderation_result.allowed else "blocked",
                        rule_score=moderation_result.rule_score,
                        categories=moderation_result.categories,
                        confidence=moderation_result.confidence,
                        reason_code=moderation_result.reason_code,
                        watched=moderation_result.watched,
                        violation_count=moderation_result.violation_count,
                    )

                if not moderation_result.allowed:
                    if moderation_result.should_disconnect:
                        log_event(
                            logger,
                            logging.WARNING,
                            "DLP_CLIENT_DISCONNECTED",
                            username=username,
                            room=room,
                            violation_count=moderation_result.violation_count,
                        )
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "DLP_TOO_MANY_VIOLATIONS",
                                    "message": (
                                        "Too many security policy violations. "
                                        "You have been disconnected."
                                    ),
                                    "blockedContent": message,
                                    "violationCount": moderation_result.violation_count,
                                }
                            )
                        )
                        await websocket.close(
                            code=1008,
                            reason="Too many security policy violations",
                        )
                        break

                    max_warnings = moderation_service.max_violations - 1
                    warning_number = moderation_result.violation_count
                    warning_label = (
                        "Final warning"
                        if warning_number == max_warnings
                        else "Warning"
                    )
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "DLP_BLOCKED",
                                "message": (
                                    "Message blocked by the company security policy. "
                                    f"{warning_label} {warning_number} of {max_warnings}."
                                ),
                                "blockedContent": message,
                                "warningNumber": warning_number,
                                "maxWarnings": max_warnings,
                                "warningsRemaining": max_warnings - warning_number,
                            }
                        )
                    )
                    continue

            full_message = f"{username}: {message}"
            clients = get_clients(room)
            recipient_count = sum(client != websocket for client in clients)

            if message_repository is not None:
                try:
                    message_id, _ = await message_repository.save_message(
                        room=room,
                        sender=username,
                        content=message,
                    )
                    log_event(
                        logger,
                        logging.INFO,
                        "MESSAGE_STORED",
                        message_id=message_id,
                        username=username,
                        room=room,
                    )
                except Exception as error:
                    log_event(
                        logger,
                        logging.ERROR,
                        "MESSAGE_STORE_FAILED",
                        username=username,
                        room=room,
                        error_type=type(error).__name__,
                    )
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "MESSAGE_NOT_STORED",
                                "message": "Message could not be saved",
                            }
                        )
                    )
                    continue

            log_event(
                logger,
                logging.INFO,
                "MESSAGE_RECEIVED",
                username=username,
                room=room,
                message_length=len(message),
                recipient_count=recipient_count,
            )

            for client in clients:
                if client != websocket:
                    await client.send(full_message)
    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "CLIENT_ERROR",
            username=username,
            room=room,
            remote_address=remote_address,
            error_type=type(e).__name__,
        )
    finally:
        if anti_bot_service is not None:
            anti_bot_service.remove_client(websocket)
        if room is not None:
            remove_client(room, websocket)
        log_event(
            logger,
            logging.INFO,
            "CLIENT_DISCONNECTED",
            username=username,
            room=room,
            remote_address=remote_address,
        )

async def main():
    server_name = input("Choose a server name: ").strip()
    if not server_name:
        server_name = "chat-server"

    log_event(logger, logging.INFO, "SERVER_STARTING", requested_name=server_name, port=PORT)
    message_repository = MessageRepository()
    moderation_service = DLPService()
    anti_bot_service = AntiBotService()

    try:
        await message_repository.connect()
        log_event(
            logger,
            logging.INFO,
            "DATABASE_CONNECTED",
            database=message_repository.database_name,
        )
        await moderation_service.check_ready()
        log_event(
            logger,
            logging.INFO,
            "DLP_READY",
            model=moderation_service.model,
        )
    except Exception as error:
        log_event(
            logger,
            logging.ERROR,
            "SERVER_DEPENDENCY_FAILED",
            database=message_repository.database_name,
            model=moderation_service.model,
            error_type=type(error).__name__,
        )
        await moderation_service.close()
        await message_repository.close()
        return

    zeroconf, service_info, advertised_name, server_ip = await asyncio.to_thread(
        register_server, server_name, PORT
    )

    try:
        client_handler = partial(
            handle_client,
            message_repository=message_repository,
            moderation_service=moderation_service,
            anti_bot_service=anti_bot_service,
        )
        async with serve(client_handler, "0.0.0.0", PORT):
            log_event(
                logger,
                logging.INFO,
                "SERVER_STARTED",
                server_name=advertised_name,
                ip=server_ip,
                port=PORT,
            )
            await asyncio.Future()
    finally:
        await asyncio.to_thread(unregister_server, zeroconf, service_info)
        await moderation_service.close()
        anti_bot_service.clear()
        await message_repository.close()
        log_event(logger, logging.INFO, "DLP_STOPPED", model=moderation_service.model)
        log_event(logger, logging.INFO, "DATABASE_DISCONNECTED")
        log_event(logger, logging.INFO, "SERVER_STOPPED", server_name=advertised_name)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
