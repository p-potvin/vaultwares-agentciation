"""
VaultWares Agent Skills — callable actions agents can invoke at runtime.

Available skill sets:
  GitHubSkills — GitHub API actions: create a PR, trigger a task dispatch event.
"""

from .github_skills import GitHubSkills

__all__ = ["GitHubSkills"]
