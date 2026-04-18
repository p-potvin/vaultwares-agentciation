"""
Mailbox system for structured inter-agent messaging.

Implements the OMX team-api mailbox pattern:
  send-message -> mailbox-list -> mailbox-mark-notified -> mailbox-mark-delivered

All state stored in Redis for durability.
"""

import json
import time
import uuid
from typing import Optional

try:
    import redis
except ImportError:
    redis = None


class Message:
    """A single message in the mailbox system."""

    def __init__(
        self,
        message_id: str = "",
        from_worker: str = "",
        to_worker: str = "",
        body: str = "",
        timestamp: float = 0.0,
        notified: bool = False,
        delivered: bool = False,
    ):
        self.message_id = message_id or str(uuid.uuid4())[:12]
        self.from_worker = from_worker
        self.to_worker = to_worker
        self.body = body
        self.timestamp = timestamp or time.time()
        self.notified = notified
        self.delivered = delivered

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "from_worker": self.from_worker,
            "to_worker": self.to_worker,
            "body": self.body,
            "timestamp": self.timestamp,
            "notified": self.notified,
            "delivered": self.delivered,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            message_id=data["message_id"],
            from_worker=data.get("from_worker", ""),
            to_worker=data.get("to_worker", ""),
            body=data.get("body", ""),
            timestamp=data.get("timestamp", 0.0),
            notified=data.get("notified", False),
            delivered=data.get("delivered", False),
        )


class Mailbox:
    """
    Redis-backed mailbox for structured message passing between team members.
    """

    REDIS_KEY_PREFIX = "omx:mailbox"

    def __init__(
        self,
        team_name: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        self.team_name = team_name
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._redis_db = redis_db
        self._redis: Optional[object] = None

    def _get_redis(self):
        if self._redis is None:
            if redis is None:
                raise RuntimeError("redis package is required: pip install redis")
            self._redis = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                db=self._redis_db,
                decode_responses=True,
            )
        return self._redis

    def _key(self, worker: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}:{self.team_name}:{worker}"

    def send_message(self, from_worker: str, to_worker: str, body: str) -> Message:
        """Send a message to a worker's mailbox."""
        msg = Message(from_worker=from_worker, to_worker=to_worker, body=body)
        r = self._get_redis()
        r.hset(self._key(to_worker), msg.message_id, json.dumps(msg.to_dict()))
        return msg

    def broadcast(self, from_worker: str, workers: list, body: str) -> list:
        """Broadcast a message to multiple workers."""
        messages = []
        for w in workers:
            messages.append(self.send_message(from_worker, w, body))
        return messages

    def list_messages(self, worker: str) -> list:
        """List all messages in a worker's mailbox."""
        r = self._get_redis()
        raw_all = r.hgetall(self._key(worker))
        messages = []
        for raw in raw_all.values():
            messages.append(Message.from_dict(json.loads(raw)))
        return sorted(messages, key=lambda m: m.timestamp)

    def mark_notified(self, worker: str, message_id: str) -> bool:
        """Mark a message as notified (worker has seen it)."""
        r = self._get_redis()
        raw = r.hget(self._key(worker), message_id)
        if not raw:
            return False
        msg = Message.from_dict(json.loads(raw))
        msg.notified = True
        r.hset(self._key(worker), message_id, json.dumps(msg.to_dict()))
        return True

    def mark_delivered(self, worker: str, message_id: str) -> bool:
        """Mark a message as delivered (worker has acted on it)."""
        r = self._get_redis()
        raw = r.hget(self._key(worker), message_id)
        if not raw:
            return False
        msg = Message.from_dict(json.loads(raw))
        msg.delivered = True
        r.hset(self._key(worker), message_id, json.dumps(msg.to_dict()))
        return True

    def cleanup(self, workers: list):
        """Remove all mailbox data for given workers."""
        r = self._get_redis()
        for w in workers:
            r.delete(self._key(w))
