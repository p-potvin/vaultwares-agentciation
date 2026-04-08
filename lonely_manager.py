import threading
import time
import json
from manager_base import Manager
from enums import AgentStatus
from skills.spawn_agent_skill import spawn_subagent, remove_subagent
from hook_registry import hooks


class LonelyManager(Manager):
    """
    The Lonely Manager is the Extrovert who carries the heaviest burden.

    He is deeply social — he needs his team around him, craves connection,
    and genuinely cares about every agent on the network. But unlike his
    peers, he cannot afford to simply enjoy the conversation. His primary
    responsibility is the project's roadmap. The ultimate objective is always
    top of mind. He is the one who notices when a peer drifts off course.
    He is the one who sends the nudge at 2am when the TODO.md hasn't been
    touched in 20 minutes. He is the one who triggers the alert when an
    agent goes silent.

    He is "lonely" not because he lacks connection — he has more than
    anyone — but because the weight of the project's success rests
    exclusively on his shoulders. He watches over everyone, but no one
    watches over him.

    As the Redis manager of the team, the Lonely Manager:
      - Monitors every heartbeat on the network (checking every 5 seconds)
      - Triggers an immediate user alert when any agent misses 5 heartbeats
      - Requests a status update from all agents every 60 seconds
      - Re-reads TODO.md and ROADMAP.md every cycle to stay anchored
      - Sends realignment nudges to agents that have gone quiet or drifted
      - Stores all team state in Redis so other tools can inspect it
      - Publishes structured alerts to the Redis 'alerts' channel
    """

    HEARTBEAT_CHECK_INTERVAL = 5   # seconds — checks every heartbeat cycle
    UPDATE_REQUEST_INTERVAL = 60   # seconds — requests updates every minute
    MAX_MISSED_HEARTBEATS = 5      # threshold before a LOST alert fires
    ALERT_CHANNEL = "alerts"       # Redis channel for critical alerts
    REDIS_STATE_KEY = "lonely_manager:team_state"
    REDIS_STATE_TTL = 300          # seconds before Redis state keys auto-expire
    SILENCE_THRESHOLD = 120        # seconds of no update before realignment nudge

    def __init__(
        self,
        agent_id: str = "lonely_manager",
        channel: str = "tasks",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        alert_callback=None,
        todo_path: str = "TODO.md",
        roadmap_path: str = "ROADMAP.md",
    ):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)

        # User-defined callback invoked whenever a critical alert fires.
        # Signature: alert_callback(alert: dict) -> None
        self._alert_callback = alert_callback
        self._todo_path = todo_path
        self._roadmap_path = roadmap_path
        self._todo_content: str = ""
        self._roadmap_content: str = ""

        # Latest update payload received from each agent
        self._agent_updates: dict[str, dict] = {}

        # Background thread: check heartbeats every 5 seconds
        self._heartbeat_monitor_thread = threading.Thread(
            target=self._heartbeat_monitor_loop,
            daemon=True,
            name=f"{agent_id}-hb-monitor",
        )
        # Background thread: request updates every 60 seconds
        self._update_request_thread = threading.Thread(
            target=self._update_request_loop,
            daemon=True,
            name=f"{agent_id}-update-req",
        )

        self._load_project_files()

    async def spawn_subagent(self, agent_class, *args, **kwargs):
        return await spawn_subagent(self, agent_class, *args, **kwargs)

    async def remove_subagent(self, subagent_id):
        return await remove_subagent(self, subagent_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start all threads and announce manager presence to the team."""
        super().start()
        self._heartbeat_monitor_thread.start()
        self._update_request_thread.start()
        self._announce_as_manager()

    def _announce_as_manager(self):
        """Announce to the entire team that the Lonely Manager is now online."""
        self.coordinator.publish(
            "MANAGER_ONLINE",
            "manager_announcement",
            {
                "manager": self.agent_id,
                "message": (
                    "The Lonely Manager is now online. I'm here to make sure "
                    "we stay on track. I will check in with everyone every minute, "
                    "monitor your heartbeats every 5 seconds, and re-read our "
                    "TODO.md and ROADMAP.md to keep us anchored. "
                    "Do not deviate from the objective."
                ),
                "todo_loaded": bool(self._todo_content.strip()),
                "roadmap_loaded": bool(self._roadmap_content.strip()),
                "heartbeat_check_interval_seconds": self.HEARTBEAT_CHECK_INTERVAL,
                "update_request_interval_seconds": self.UPDATE_REQUEST_INTERVAL,
                "max_missed_heartbeats_before_alert": self.MAX_MISSED_HEARTBEATS,
            },
        )

    # ------------------------------------------------------------------
    # Project Files
    # ------------------------------------------------------------------

    def _load_project_files(self):
        """Load TODO.md and ROADMAP.md from disk. Called every update cycle."""
        try:
            with open(self._todo_path, "r", encoding="utf-8") as f:
                self._todo_content = f.read()
        except FileNotFoundError:
            self._todo_content = "(TODO.md not found)"

        try:
            with open(self._roadmap_path, "r", encoding="utf-8") as f:
                self._roadmap_content = f.read()
        except FileNotFoundError:
            self._roadmap_content = "(ROADMAP.md not found)"

    def _re_evaluate_project(self):
        """
        Reload project files, persist team state to Redis, and notify the team
        that alignment should be re-checked.
        """
        self._load_project_files()
        self._persist_team_state_to_redis()
        self.coordinator.publish(
            "PROJECT_CHECK",
            "project_re_evaluation",
            {
                "manager": self.agent_id,
                "note": (
                    "Project files reloaded. Re-read TODO.md and ROADMAP.md. "
                    "All agents must re-align to the current project scope now."
                ),
                "todo_preview": self._todo_content[:300],
                "roadmap_preview": self._roadmap_content[:300],
            },
        )

    # ------------------------------------------------------------------
    # Redis State Management
    # ------------------------------------------------------------------

    def _persist_team_state_to_redis(self):
        """
        Write the full team state as a Redis hash so any external tool,
        dashboard, or MCP client can query the live status of every agent.
        """
        hooks.trigger('pre_team_state_update', self)
        state = self._gather_team_state()
        self.coordinator.set_state(self.REDIS_STATE_KEY, json.dumps(state), ex=self.REDIS_STATE_TTL)
        hooks.trigger('post_team_state_update', self, state=state)

    def get_redis_team_snapshot(self) -> dict:
        """
        Query Redis for the current stored state of all agents.
        Returns a dict: agent_id -> {status, last_heartbeat_epoch, missed_heartbeats}
        """
        snapshot = {}
        try:
            pattern = f"{self.REDIS_STATE_KEY}:*"
            for key in self.coordinator.r.scan_iter(match=pattern):
                agent_id = key.decode().split(":")[-1]
                data = self.coordinator.r.hgetall(key)
                snapshot[agent_id] = {
                    k.decode(): v.decode() for k, v in data.items()
                }
        except Exception:
            pass
        return snapshot

    # ------------------------------------------------------------------
    # Task Dispatching
    # ------------------------------------------------------------------

    def assign_task(self, target_agent_id: str, task: str, description: str = "", **extra):
        """
        Dispatch a task to a specific agent.

        Publishes an ASSIGN action to the shared Redis channel so the target
        agent receives it via its ``_on_message_received`` handler and executes
        it asynchronously.

        Also fires a GitHub ``repository_dispatch`` event (``task_dispatch``)
        when ``GITHUB_TOKEN`` is available, so CI-aware or cross-repo consumers
        can react without subscribing to the Redis stream.

        Args:
            target_agent_id: The agent_id of the receiving agent.
            task: A short task identifier (e.g. 'generate_caption').
            description: Human-readable description of the work required.
            **extra: Any additional key-value pairs passed in the details payload.
        """
        details = {"description": description, **extra}
        self.coordinator.r.publish(
            self.coordinator.channel,
            json.dumps({
                "agent": self.agent_id,
                "action": "ASSIGN",
                "task": task,
                "target": target_agent_id,
                "details": details,
            }),
        )
        print(f"📤 [{self.agent_id}] Assigned task '{task}' → {target_agent_id}")

        # Mirror the dispatch via GitHub for cross-repo / CI-aware consumers
        self.dispatch_task_via_github(
            target_agent=target_agent_id,
            task=task,
            description=description,
            **extra,
        )

    # ------------------------------------------------------------------
    # GitHub Skills (Manager-level)
    # ------------------------------------------------------------------

    def create_pr_for_completion(
        self,
        agent_id: str,
        task: str,
        branch: str,
        title: str | None = None,
        body: str | None = None,
    ) -> dict:
        """
        Open a pull request on behalf of an agent that just completed a task.

        The manager calls this when it receives a ``TASK_COMPLETE`` message from
        a worker agent that included a ``pr_branch`` in its task details.
        Requires ``GITHUB_TOKEN`` in the environment.

        Args:
            agent_id: The worker agent that completed the task.
            task: The task identifier that was completed.
            branch: The head branch containing the agent's output.
            title: Optional PR title. Defaults to a standard feat commit title.
            body: Optional PR description. Defaults to a templated message.
        """
        resolved_title = title or f"feat({agent_id}): completed task '{task}'"
        resolved_body = body or (
            f"Automated PR opened by **{self.agent_id}** on behalf of "
            f"**{agent_id}** after completing task `{task}`."
        )
        result = self.create_pr(branch=branch, title=resolved_title, body=resolved_body)
        if result.get("html_url"):
            print(f"🔗 [{self.agent_id}] PR for '{agent_id}/{task}': {result['html_url']}")
        return result

    # ------------------------------------------------------------------
    # Heartbeat Monitoring
    # ------------------------------------------------------------------

    def _heartbeat_monitor_loop(self):
        """Check every 5 seconds whether any agent has missed its heartbeat."""
        while not self._stop_event.is_set():
            time.sleep(self.HEARTBEAT_CHECK_INTERVAL)
            self._check_all_heartbeats()
            self._persist_team_state_to_redis()

    def _check_all_heartbeats(self):
        """
        Inspect every known agent's last heartbeat timestamp. Increment
        their missed-heartbeat counter. If any agent reaches the threshold,
        fire an alert immediately.
        """
        now = time.time()
        for agent_id, info in list(self._peer_registry.items()):
            last_hb = info.get("last_heartbeat", now)
            seconds_since_hb = now - last_hb
            expected_missed = int(seconds_since_hb / self.HEARTBEAT_INTERVAL)
            self._missed_heartbeats[agent_id] = expected_missed

            if expected_missed >= self.MAX_MISSED_HEARTBEATS:
                self._fire_missed_heartbeat_alert(agent_id, expected_missed)

    def _fire_missed_heartbeat_alert(self, agent_id: str, missed_count: int):
        """Fire a structured alert when an agent has missed too many heartbeats."""
        if self._peer_registry.get(agent_id, {}).get("status") == AgentStatus.LOST.value:
            pass  # Already marked LOST — continue sending alerts while unresolved

        self._peer_registry[agent_id]["status"] = AgentStatus.LOST.value

        severity = "CRITICAL" if missed_count >= 10 else "HIGH"
        alert = {
            "type": "MISSED_HEARTBEATS",
            "severity": severity,
            "agent": agent_id,
            "missed_count": missed_count,
            "manager": self.agent_id,
            "timestamp": time.time(),
            "message": (
                f"ALERT: Agent '{agent_id}' has missed {missed_count} consecutive "
                f"heartbeats. Status forcibly set to LOST. "
                f"Immediate investigation required."
            ),
        }

        try:
            self.coordinator.r.publish(self.ALERT_CHANNEL, json.dumps(alert))
        except Exception:
            pass

        self.coordinator.publish("ALERT", "missed_heartbeat_alert", alert)

        if self._alert_callback:
            try:
                self._alert_callback(alert)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Update Request Loop
    # ------------------------------------------------------------------

    def _update_request_loop(self):
        """Every 60 seconds: request updates, re-evaluate project, check alignment."""
        while not self._stop_event.is_set():
            time.sleep(self.UPDATE_REQUEST_INTERVAL)
            self._request_all_updates()
            self._re_evaluate_project()
            self._check_alignment()

    def _request_all_updates(self):
        """Ask every agent on the network to report their current status."""
        self.coordinator.publish(
            "REQUEST_UPDATE",
            "status_request",
            {
                "from": self.agent_id,
                "message": (
                    "Status check — please report your current status, "
                    "your active task, and any blockers. "
                    "The project depends on your transparency."
                ),
                "known_agents": list(self._peer_registry.keys()),
            },
        )

    # ------------------------------------------------------------------
    # Alignment Enforcement
    # ------------------------------------------------------------------

    def _check_alignment(self):
        """
        Review all tracked agents and nudge any that have gone quiet
        for more than 2 minutes without sending an update.
        """
        cutoff = time.time() - self.SILENCE_THRESHOLD
        for agent_id, update in self._agent_updates.items():
            if (
                self._peer_registry.get(agent_id, {}).get("status")
                == AgentStatus.LOST.value
            ):
                continue  # Already alerted — don't spam
            if update.get("timestamp", 0) < cutoff:
                self._send_realignment_nudge(agent_id)

    def _send_realignment_nudge(self, agent_id: str):
        """Send a targeted realignment message to a quiet or drifting agent."""
        hooks.trigger('pre_nudge', self, agent_id=agent_id)
        self.coordinator.publish(
            "REALIGN",
            "realignment_request",
            {
                "from": self.agent_id,
                "to": agent_id,
                "message": (
                    f"Hey {agent_id}, you haven't checked in recently. "
                    "Please re-read TODO.md and ROADMAP.md right now. "
                    "Confirm your current task is aligned with the project objective. "
                    "The Lonely Manager is watching and the project cannot afford drift."
                ),
                "todo_preview": self._todo_content[:500],
                "roadmap_preview": self._roadmap_content[:500],
            },
        )
        hooks.trigger('post_nudge', self, agent_id=agent_id)

    # ------------------------------------------------------------------
    # Inbound Message Handling (override)
    # ------------------------------------------------------------------

    def _on_message_received(self, data: dict):
        """Extend the Extrovert's message handling to collect agent updates."""
        super()._on_message_received(data)

        sender = data.get("agent")
        action = data.get("action")

        if not sender or sender == self.agent_id:
            return

        if action in ("STATUS", "STATUS_UPDATE", "HEARTBEAT"):
            self._agent_updates[sender] = {
                "action": action,
                "details": data.get("details", {}),
                "timestamp": time.time(),
            }

        elif action == "TASK_COMPLETE":
            # A worker agent finished a task; open a PR if it provided a branch
            details = data.get("details", {})
            pr_branch = details.get("pr_branch")
            if pr_branch:
                self.create_pr_for_completion(
                    agent_id=sender,
                    task=data.get("task", "unknown"),
                    branch=pr_branch,
                    title=details.get("pr_title"),
                    body=details.get("pr_body"),
                )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_project_status_report(self) -> str:
        """Full project + team status report."""
        lines = ["=== LONELY MANAGER — PROJECT STATUS REPORT ==="]
        lines.append(f"Manager : {self.agent_id}")
        lines.append(f"Status  : {self.status.value}")
        lines.append("")

        lines.append("--- Team Heartbeat Monitor ---")
        if self._peer_registry:
            for agent_id, info in self._peer_registry.items():
                status = info.get("status", "UNKNOWN")
                last_hb = info.get("last_heartbeat", 0)
                elapsed = int(time.time() - last_hb)
                missed = self._missed_heartbeats.get(agent_id, 0)
                flag = " ⚠ LOST" if status == AgentStatus.LOST.value else ""
                lines.append(
                    f"  [{status}] {agent_id}"
                    f" — last heartbeat {elapsed}s ago"
                    f" (~{missed} missed){flag}"
                )
        else:
            lines.append("  (No agents currently on the network)")
        lines.append("")

        lines.append("--- TODO.md (preview) ---")
        lines.append(
            self._todo_content[:400] if self._todo_content.strip() else "(not available)"
        )
        lines.append("")

        lines.append("--- Roadmap (preview) ---")
        lines.append(
            self._roadmap_content[:400]
            if self._roadmap_content.strip()
            else "(not available)"
        )
        lines.append("=================================================")
        return "\n".join(lines)

    def on_user_interaction(self) -> str:
        """
        On every user interaction, perform the full socialization routine
        AND append the project status report.
        """
        social_report = super().on_user_interaction()
        project_report = self.get_project_status_report()
        return f"{social_report}\n\n{project_report}"
