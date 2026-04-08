import asyncio
import uuid
from redis_coordinator import RedisCoordinator
from enums import AgentStatus
from hook_registry import hooks

class Manager:
    """
    Base Manager class for async subagent spawning and Redis-based coordination.
    """
    def __init__(self, agent_id, channel='tasks', redis_host='localhost', redis_port=6379, redis_db=0):
        self.agent_id = agent_id
        self.status = AgentStatus.WAITING_FOR_INPUT
        self.coordinator = RedisCoordinator(agent_id, channel, redis_host, redis_port, redis_db)
        self.subagents = {}  # agent_id -> task/process
        self.loop = asyncio.get_event_loop()
        self._stop = False

    async def spawn_subagent(self, agent_class, *args, **kwargs):
        """
        Spawn a subagent as an asyncio Task. Each subagent gets a unique agent_id.
        """
        hooks.trigger('pre_subagent_spawn', self, agent_class=agent_class, args=args, kwargs=kwargs)
        subagent_id = f"subagent-{uuid.uuid4().hex[:8]}"
        agent = agent_class(subagent_id, *args, **kwargs)
        task = self.loop.create_task(agent.run())
        self.subagents[subagent_id] = task
        self.coordinator.publish('SPAWN', 'subagent_spawned', {'subagent_id': subagent_id})
        hooks.trigger('post_subagent_spawn', self, subagent_id=subagent_id, agent=agent)
        return subagent_id

    async def remove_subagent(self, subagent_id):
        """
        Cancel and remove a subagent by id.
        """
        hooks.trigger('pre_subagent_remove', self, subagent_id=subagent_id)
        task = self.subagents.get(subagent_id)
        if task:
            task.cancel()
            self.coordinator.publish('REMOVE', 'subagent_removed', {'subagent_id': subagent_id})
            del self.subagents[subagent_id]
        hooks.trigger('post_subagent_remove', self, subagent_id=subagent_id)

    async def listen_for_updates(self, callback):
        """
        Listen to Redis for updates from subagents and invoke callback(data).
        """
        def _on_message(data):
            callback(data)
        self.coordinator.listen(_on_message)

    async def send_mass_message(self, message):
        """
        Send a message to all subagents via Redis.
        """
        self.coordinator.publish('MASS_MESSAGE', 'broadcast', {'message': message})

    async def shutdown(self):
        hooks.trigger('pre_manager_shutdown', self)
        self._stop = True
        for subagent_id in list(self.subagents.keys()):
            await self.remove_subagent(subagent_id)
        self.coordinator.stop()
        hooks.trigger('post_manager_shutdown', self)

    # Example run loop for the manager
    async def run(self):
        while not self._stop:
            await asyncio.sleep(1)
