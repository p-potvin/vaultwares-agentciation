"""
OMX Leader — Orchestrates the team and owns verification.

Follows the AGENTS.md child_agent_protocol for leaders:
1. Pick the mode and keep the user-facing brief current.
2. Delegate only bounded, verifiable subtasks with clear ownership.
3. Integrate results, decide follow-up, and own final verification.

The leader manages the full OMX pipeline:
  team-plan -> team-prd -> team-exec -> team-verify -> team-fix (loop)
"""

import json
import os
import time
import threading
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enums import AgentStatus
from redis_coordinator import RedisCoordinator
from hook_registry import hooks
from omx_integration.task_queue import TaskQueue, TaskStatus
from omx_integration.mailbox import Mailbox
from omx_integration.skill_router import SkillRouter


class OMXLeader:
    """
    Team leader that orchestrates workers through the OMX pipeline.

    Responsibilities:
    - Plan decomposition and task assignment
    - Worker health monitoring
    - Result integration and verification
    - GitHub PR creation for deliverables
    """

    HEARTBEAT_INTERVAL = 5
    WORKER_CHECK_INTERVAL = 10

    def __init__(
        self,
        leader_id: str = "leader-fixed",
        team_name: str = "omx-team",
        project_dir: str = ".",
        redis_host: str = "localhost",
        redis_port: int = 6379,
    ):
        self.leader_id = leader_id
        self.team_name = team_name
        self.project_dir = os.path.abspath(project_dir)
        self.status = AgentStatus.RELAXING
        self._stop_event = threading.Event()

        # Redis coordinator for team communication
        self.coordinator = RedisCoordinator(
            agent_id=leader_id,
            channel="tasks",
            redis_host=redis_host,
            redis_port=redis_port,
        )

        # Task queue for claim-safe task management
        self.task_queue = TaskQueue(
            team_name=team_name,
            redis_host=redis_host,
            redis_port=redis_port,
        )

        # Mailbox for structured messages
        self.mailbox = Mailbox(
            team_name=team_name,
            redis_host=redis_host,
            redis_port=redis_port,
        )

        # Skill router for keyword detection
        self.skill_router = SkillRouter(omx_runtime=True)

        # Worker tracking
        self.workers: dict[str, dict] = {}
        self.completed_tasks: list = []
        self.pipeline_stage: str = "idle"

    def start(self):
        """Start the leader: announce, begin monitoring."""
        hooks.trigger("pre_agent_start", self.leader_id)
        self.status = AgentStatus.WORKING

        self.coordinator.publish({
            "agent": self.leader_id,
            "action": "JOIN",
            "details": {
                "team": self.team_name,
                "role": "leader",
                "status": self.status.value,
            },
        })

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

        hooks.trigger("post_agent_start", self.leader_id)
        print(f"[{self.leader_id}] Leader started (team={self.team_name})")

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            self.coordinator.publish({
                "agent": self.leader_id,
                "action": "HEARTBEAT",
                "details": {
                    "status": self.status.value,
                    "pipeline_stage": self.pipeline_stage,
                    "team": self.team_name,
                    "worker_count": len(self.workers),
                },
            })
            self._stop_event.wait(self.HEARTBEAT_INTERVAL)

    def register_worker(self, worker_id: str, role: str = "executor"):
        """Register a worker in the team."""
        self.workers[worker_id] = {
            "role": role,
            "status": "idle",
            "registered_at": time.time(),
            "last_heartbeat": time.time(),
        }
        self.mailbox.send_message(
            self.leader_id, worker_id,
            f"Welcome to team {self.team_name}. Role: {role}. Awaiting task assignment."
        )
        print(f"[{self.leader_id}] Registered worker: {worker_id} (role={role})")

    def create_plan(self, task_descriptions: list) -> list:
        """
        Team-plan stage: decompose work into tasks.

        Args:
            task_descriptions: List of dicts with 'subject', 'description', 'owner'.

        Returns:
            List of created Task objects.
        """
        self.pipeline_stage = "team-plan"
        print(f"[{self.leader_id}] Pipeline stage: team-plan")

        tasks = []
        for desc in task_descriptions:
            task = self.task_queue.create_task(
                subject=desc["subject"],
                description=desc.get("description", ""),
                owner=desc.get("owner", ""),
            )
            tasks.append(task)
            print(f"[{self.leader_id}]   Created task: {task.task_id} — {task.subject}")

        self.pipeline_stage = "team-prd"
        return tasks

    def assign_tasks(self, assignments: list):
        """
        Team-exec stage: assign tasks to workers.

        Args:
            assignments: List of dicts with 'task_id', 'worker_id'.
        """
        self.pipeline_stage = "team-exec"
        print(f"[{self.leader_id}] Pipeline stage: team-exec")

        for assignment in assignments:
            task_id = assignment["task_id"]
            worker_id = assignment["worker_id"]

            # Claim on behalf of worker
            claim_token = self.task_queue.claim_task(task_id, worker_id)
            if claim_token:
                # Send assignment via Redis
                self.coordinator.publish({
                    "agent": self.leader_id,
                    "action": "ASSIGN",
                    "task": task_id,
                    "target": worker_id,
                    "details": {
                        "claim_token": claim_token,
                        "team": self.team_name,
                    },
                })

                # Also via mailbox
                task = self.task_queue.get_task(task_id)
                if task:
                    self.mailbox.send_message(
                        self.leader_id, worker_id,
                        f"ASSIGN: task={task_id}, subject={task.subject}, "
                        f"claim_token={claim_token}"
                    )
                print(f"[{self.leader_id}]   Assigned {task_id} -> {worker_id}")
            else:
                print(f"[{self.leader_id}]   Failed to claim {task_id} for {worker_id}")

    def record_completion(self, task_id: str, claim_token: str, result: str = ""):
        """Record a task as completed."""
        success = self.task_queue.transition_status(
            task_id, "in_progress", "completed", claim_token, result
        )
        if success:
            self.completed_tasks.append(task_id)
            print(f"[{self.leader_id}] Task completed: {task_id}")
        return success

    def verify_completion(self) -> dict:
        """
        Team-verify stage: check all tasks are done.

        Returns:
            Dict with verification results.
        """
        self.pipeline_stage = "team-verify"
        print(f"[{self.leader_id}] Pipeline stage: team-verify")

        all_tasks = self.task_queue.list_tasks()
        completed = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
        pending = [t for t in all_tasks if t.status == TaskStatus.PENDING]
        in_progress = [t for t in all_tasks if t.status == TaskStatus.IN_PROGRESS]
        failed = [t for t in all_tasks if t.status == TaskStatus.FAILED]

        result = {
            "total": len(all_tasks),
            "completed": len(completed),
            "pending": len(pending),
            "in_progress": len(in_progress),
            "failed": len(failed),
            "all_done": len(pending) == 0 and len(in_progress) == 0 and len(failed) == 0,
            "tasks": [t.to_dict() for t in all_tasks],
        }

        if result["all_done"]:
            self.pipeline_stage = "complete"
            print(f"[{self.leader_id}] All tasks verified complete!")
        else:
            print(f"[{self.leader_id}] Verification: {result['completed']}/{result['total']} complete")

        return result

    def get_team_report(self) -> str:
        """Generate a formatted team status report."""
        lines = [
            f"## Team Status: {self.team_name}",
            f"**Leader**: {self.leader_id}",
            f"**Pipeline Stage**: {self.pipeline_stage}",
            f"**Workers**: {len(self.workers)}",
            "",
        ]
        for wid, info in self.workers.items():
            lines.append(f"- **{wid}** — role: {info['role']}, status: {info['status']}")

        all_tasks = self.task_queue.list_tasks()
        if all_tasks:
            lines.append("")
            lines.append("### Tasks")
            for t in all_tasks:
                lines.append(f"- [{t.status.value}] {t.task_id}: {t.subject}")

        return "\n".join(lines)

    def shutdown(self):
        """Shut down the team: notify workers, clean up state."""
        self.pipeline_stage = "shutdown"
        hooks.trigger("pre_agent_stop", self.leader_id)
        self._stop_event.set()

        # Notify all workers
        for wid in self.workers:
            self.mailbox.send_message(
                self.leader_id, wid,
                "SHUTDOWN: Team is shutting down. Complete current work and stop."
            )

        # Announce departure
        self.coordinator.publish({
            "agent": self.leader_id,
            "action": "LEAVE",
            "details": {"team": self.team_name},
        })

        self.coordinator.stop()
        hooks.trigger("post_agent_stop", self.leader_id)
        print(f"[{self.leader_id}] Leader shutdown complete")

    def cleanup(self):
        """Clean up all team state from Redis."""
        self.task_queue.cleanup()
        self.mailbox.cleanup(list(self.workers.keys()))
        print(f"[{self.leader_id}] Team state cleaned up")
