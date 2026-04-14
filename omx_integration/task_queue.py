"""
Task queue with claim-safe lifecycle, inspired by OMX team-api task management.

Implements the OMX task lifecycle:
  create-task -> claim-task -> transition-task-status (in_progress -> completed)

All state is stored in Redis for durability and cross-agent visibility.
"""

import json
import time
import uuid
from enum import Enum
from typing import Optional

try:
    import redis
except ImportError:
    redis = None


class TaskStatus(Enum):
    """Task lifecycle states matching OMX team-api conventions."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """A single unit of work in the team task queue."""

    def __init__(
        self,
        task_id: str,
        subject: str,
        description: str = "",
        owner: str = "",
        status: TaskStatus = TaskStatus.PENDING,
        version: int = 1,
        claim_token: str = "",
        claimed_by: str = "",
        created_at: float = 0.0,
        completed_at: float = 0.0,
        result: str = "",
    ):
        self.task_id = task_id
        self.subject = subject
        self.description = description
        self.owner = owner
        self.status = status
        self.version = version
        self.claim_token = claim_token
        self.claimed_by = claimed_by
        self.created_at = created_at or time.time()
        self.completed_at = completed_at
        self.result = result

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "subject": self.subject,
            "description": self.description,
            "owner": self.owner,
            "status": self.status.value,
            "version": self.version,
            "claim_token": self.claim_token,
            "claimed_by": self.claimed_by,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            task_id=data["task_id"],
            subject=data["subject"],
            description=data.get("description", ""),
            owner=data.get("owner", ""),
            status=TaskStatus(data.get("status", "pending")),
            version=data.get("version", 1),
            claim_token=data.get("claim_token", ""),
            claimed_by=data.get("claimed_by", ""),
            created_at=data.get("created_at", 0.0),
            completed_at=data.get("completed_at", 0.0),
            result=data.get("result", ""),
        )


class TaskQueue:
    """
    Claim-safe task queue backed by Redis.

    Follows the OMX team-api pattern:
      create_task -> claim_task (with version check) -> transition_status
    """

    REDIS_KEY_PREFIX = "omx:taskqueue"

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

    @property
    def _key(self) -> str:
        return f"{self.REDIS_KEY_PREFIX}:{self.team_name}"

    def _get_redis(self):
        """Lazy Redis connection."""
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

    def create_task(self, subject: str, description: str = "", owner: str = "") -> Task:
        """Create a new task in PENDING state."""
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            subject=subject,
            description=description,
            owner=owner,
        )
        r = self._get_redis()
        r.hset(self._key, task.task_id, json.dumps(task.to_dict()))
        return task

    def claim_task(self, task_id: str, worker: str, expected_version: int = 1) -> Optional[str]:
        """
        Claim a task with version-check safety.
        Returns claim_token on success, None on version mismatch.
        """
        r = self._get_redis()
        raw = r.hget(self._key, task_id)
        if not raw:
            return None
        task = Task.from_dict(json.loads(raw))
        if task.version != expected_version:
            return None
        if task.status != TaskStatus.PENDING:
            return None
        claim_token = str(uuid.uuid4())[:12]
        task.status = TaskStatus.IN_PROGRESS
        task.claimed_by = worker
        task.claim_token = claim_token
        task.version += 1
        r.hset(self._key, task.task_id, json.dumps(task.to_dict()))
        return claim_token

    def transition_status(
        self,
        task_id: str,
        from_status: str,
        to_status: str,
        claim_token: str,
        result: str = "",
    ) -> bool:
        """Transition task status with claim-token validation."""
        r = self._get_redis()
        raw = r.hget(self._key, task_id)
        if not raw:
            return False
        task = Task.from_dict(json.loads(raw))
        if task.claim_token != claim_token:
            return False
        if task.status.value != from_status:
            return False
        task.status = TaskStatus(to_status)
        task.version += 1
        task.result = result
        if to_status == TaskStatus.COMPLETED.value:
            task.completed_at = time.time()
        r.hset(self._key, task.task_id, json.dumps(task.to_dict()))
        return True

    def list_tasks(self) -> list:
        """List all tasks in the queue."""
        r = self._get_redis()
        raw_all = r.hgetall(self._key)
        tasks = []
        for raw in raw_all.values():
            tasks.append(Task.from_dict(json.loads(raw)))
        return tasks

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a specific task by ID."""
        r = self._get_redis()
        raw = r.hget(self._key, task_id)
        if not raw:
            return None
        return Task.from_dict(json.loads(raw))

    def cleanup(self):
        """Remove all tasks for this team."""
        r = self._get_redis()
        r.delete(self._key)
