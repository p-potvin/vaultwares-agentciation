"""
RedisCommSkill — Redis-based communication and coordination for VaultWares agents.

This skill provides reusable functions for agent communication, status updates,
peer registry management, and broadcast messaging using Redis pub/sub.

Usage:
    from skills.redis_comm_skill import (
        publish_status, send_heartbeat, broadcast_message, register_peer,
        update_peer_status, handle_incoming_message
    )
"""

def publish_status(coordinator, agent_id, status):
    """Publish the agent's status to Redis."""
    coordinator.publish('STATUS', 'status_update', {'agent': agent_id, 'status': status})

def send_heartbeat(coordinator, agent_id, details=None):
    """Send a heartbeat message to Redis."""
    coordinator.publish('HEARTBEAT', 'heartbeat', {'agent': agent_id, 'details': details or {}})

def broadcast_message(coordinator, agent_id, message):
    """Broadcast a message to all agents via Redis."""
    coordinator.publish('BROADCAST', 'broadcast_message', {'agent': agent_id, 'message': message})

def register_peer(peer_registry, agent_id, status, last_heartbeat):
    """Register or update a peer in the local registry."""
    peer_registry[agent_id] = {'status': status, 'last_heartbeat': last_heartbeat}

def update_peer_status(peer_registry, agent_id, status):
    """Update the status of a peer in the registry."""
    if agent_id in peer_registry:
        peer_registry[agent_id]['status'] = status

import time

def handle_incoming_message(data, peer_registry, missed_heartbeats):
    """Handle an incoming Redis message and update peer state."""
    sender = data.get('agent')
    action = data.get('action')
    details = data.get('details', {})
    if not sender:
        return
    import time
    now = time.time()
    if action == 'HEARTBEAT':
        register_peer(peer_registry, sender, details.get('status', 'WORKING'), now)
        missed_heartbeats[sender] = 0
    elif action in ('STATUS', 'STATUS_UPDATE'):
        update_peer_status(peer_registry, sender, details.get('status', 'WORKING'))
    elif action == 'JOIN':
        register_peer(peer_registry, sender, details.get('status', 'WAITING_FOR_INPUT'), now)
        missed_heartbeats[sender] = 0
    elif action == 'LEAVE':
        peer_registry.pop(sender, None)
        missed_heartbeats.pop(sender, None)
