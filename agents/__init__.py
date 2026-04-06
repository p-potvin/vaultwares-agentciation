"""
VaultWares Agents — specialized agent implementations.

All agents inherit from ExtrovertAgent and implement domain-specific
task handling. They connect to Redis and participate in the
LonelyManager heartbeat & dispatch network.
"""

from .text_agent import TextAgent
from .image_agent import ImageAgent
from .video_agent import VideoAgent
from .workflow_agent import WorkflowAgent

__all__ = [
    "TextAgent",
    "ImageAgent",
    "VideoAgent",
    "WorkflowAgent",
]
