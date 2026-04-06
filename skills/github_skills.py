"""
GitHubSkills — GitHub API actions available to any VaultWares agent.

Agents receive a ``github`` attribute (a GitHubSkills instance) after calling
``ExtrovertAgent.__init__``. All skills are no-ops when no token is supplied,
so agents work in token-free environments without crashing.

Usage inside any agent::

    # Create a PR when a task is complete
    self.github.create_pr(
        branch="agent/image-agent/generate-image-20260406",
        title="feat(image-agent): generated image from prompt",
        body="Completed task: generate_image\\n\\nResult: ...",
    )

    # Route a task to another agent via GitHub repository_dispatch
    self.github.dispatch_task(
        target_agent="video-agent",
        task="trim_video",
        description="Trim the intro from sample.mp4",
        source="sample.mp4",
        start_time=0,
        end_time=15,
    )
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any


class GitHubSkills:
    """
    GitHub API skill set for VaultWares agents.

    Parameters
    ----------
    token:
        A GitHub personal access token (or ``GITHUB_TOKEN`` env var).
        When omitted the class reads ``GITHUB_TOKEN`` from the environment.
        All methods degrade gracefully to a warning when no token is found.
    owner:
        GitHub repository owner (user or organisation).
        Falls back to the ``GITHUB_REPOSITORY_OWNER`` env var.
    repo:
        GitHub repository name (without the owner prefix).
        Falls back to the ``GITHUB_REPOSITORY`` env var (strips the owner prefix).
    base_branch:
        Default target branch for pull requests. Defaults to ``"main"``.
    """

    GITHUB_API = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        base_branch: str = "main",
    ):
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._base_branch = base_branch

        # Resolve owner / repo from env vars when not given explicitly
        env_repo = os.getenv("GITHUB_REPOSITORY", "")  # "owner/repo"
        if owner:
            self._owner = owner
        else:
            self._owner = os.getenv("GITHUB_REPOSITORY_OWNER", env_repo.split("/")[0] if "/" in env_repo else "")

        if repo:
            self._repo = repo
        else:
            self._repo = env_repo.split("/")[1] if "/" in env_repo else ""

    # ------------------------------------------------------------------
    # Public Skills
    # ------------------------------------------------------------------

    def create_pr(
        self,
        branch: str,
        title: str,
        body: str = "",
        base: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a GitHub pull request from *branch* into *base*.

        Called by an agent after completing a task to surface its output
        for human review.

        Parameters
        ----------
        branch:
            The head branch that contains the agent's changes.
        title:
            Pull request title.
        body:
            Pull request description / body (Markdown supported).
        base:
            Target branch. Defaults to the ``base_branch`` set at construction.
        owner / repo:
            Override the repository coordinates for this call only.

        Returns
        -------
        dict
            The GitHub API response (includes ``html_url``, ``number``, etc.).
            Returns an empty dict when no token is available.
        """
        if not self._token:
            warnings.warn(
                "GitHubSkills.create_pr: no GITHUB_TOKEN found — skipping PR creation.",
                stacklevel=2,
            )
            return {}

        payload = {
            "title": title,
            "body": body,
            "head": branch,
            "base": base or self._base_branch,
        }
        return self._post(
            f"/repos/{owner or self._owner}/{repo or self._repo}/pulls",
            payload,
        )

    def dispatch_task(
        self,
        target_agent: str,
        task: str,
        description: str = "",
        owner: str | None = None,
        repo: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Trigger a ``repository_dispatch`` event to route a task to another agent.

        Any consumer that listens for the ``task_dispatch`` event type (e.g., a
        CI runner or another Python process subscribed to the Redis channel) will
        receive the full payload and can act on it.

        Parameters
        ----------
        target_agent:
            The ``agent_id`` of the agent that should receive the task.
        task:
            Task identifier (e.g. ``"generate_image"``).
        description:
            Human-readable description of what is being requested.
        owner / repo:
            Override the repository coordinates for this call only.
        **extra:
            Additional key-value pairs merged into the ``client_payload``.

        Returns
        -------
        dict
            Empty dict on success (GitHub returns 204 No Content); the raw
            response body on error.  Returns an empty dict when no token is
            available.
        """
        if not self._token:
            warnings.warn(
                "GitHubSkills.dispatch_task: no GITHUB_TOKEN found — skipping dispatch.",
                stacklevel=2,
            )
            return {}

        payload = {
            "event_type": "task_dispatch",
            "client_payload": {
                "target_agent": target_agent,
                "task": task,
                "description": description,
                **extra,
            },
        }
        return self._post(
            f"/repos/{owner or self._owner}/{repo or self._repo}/dispatches",
            payload,
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict[str, Any]:
        """Send a POST request to the GitHub REST API."""
        try:
            import urllib.request

            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.GITHUB_API}{path}",
                data=data,
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                body = resp.read()
                return json.loads(body) if body else {}
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"GitHubSkills._post({path}): {exc}", stacklevel=3)
            return {"error": str(exc)}
