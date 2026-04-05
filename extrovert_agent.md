# Extrovert Agent

The Extrovert agent is a parent agent class for multi-agent coordination using Redis. It runs as a separate process, sends heartbeats every 5 seconds, and strictly follows its own rules for status updates, task list management, and socializing with other agents.

## Key Behaviors
- Uses RedisCoordinator for all messaging
- Sends a heartbeat every 5 seconds
- If 5 heartbeats are missed, the Redis server alerts the user
- Receives reminders every 30 seconds to send status, re-read/update todo.md and roadmap.md, and keep project scope in memory
- On every user interaction (answer), performs "socializing":
  - Sends Redis status update
  - Sends a heartbeat
  - Re-reads and re-adjusts todo.md and roadmap.md
  - Acknowledges other agents' statuses
  - Includes a short section in the answer listing all Extroverts and their status (LOST, WORKING, WAITING FOR INPUT, RELAXING)

## Status Enum
- LOST
- WORKING
- WAITING FOR INPUT
- RELAXING

## Implementation Plan
- Place all relevant code in vaultwares-agentciation/
- Implement Extrovert as a base class for future agent inheritance
- Use RedisCoordinator for all coordination
- Ensure process-based operation and robust heartbeat/status logic

---

See vaultwares-agentciation/ for code and integration details.
