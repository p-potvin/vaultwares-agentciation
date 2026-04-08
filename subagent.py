import json
import asyncio

async def listen_for_tasks(coordinator, agent_id):
    """
    Async generator that listens for tasks for this agent via Redis pub/sub.
    Yields each task as it arrives for this agent.
    """
    loop = asyncio.get_event_loop()
    pubsub = coordinator.r.pubsub()
    # Listen on a dedicated channel for this agent, or fallback to the main channel
    agent_channel = f"tasks:{agent_id}"
    pubsub.subscribe(agent_channel, coordinator.channel)
    def get_message():
        return pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    try:
        while True:
            message = await loop.run_in_executor(None, get_message)
            if message and message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    # Only yield tasks meant for this agent or broadcast
                    if data.get('agent') in (agent_id, 'all', None):
                        yield data
                except Exception:
                    continue
            await asyncio.sleep(0.1)
    finally:
        pubsub.close()
import asyncio
import asyncio
from agent_base import AgentBase
from enums import AgentStatus
from skills.print_skill import print_message
from skills.redis_comm_skill import publish_status

class SubAgent(AgentBase):
    def __init__(self, agent_id, channel='tasks', redis_host='localhost', redis_port=6379, redis_db=0):
        super().__init__(agent_id, channel, redis_host, redis_port, redis_db)
        self.status = AgentStatus.WAITING_FOR_INPUT
        self.running = True

    async def run(self):
        self.start()
        publish_status(self.coordinator, self.agent_id, self.status.value)
        async for task in listen_for_tasks(self.coordinator, self.agent_id):
            self.status = AgentStatus.WORKING
            publish_status(self.coordinator, self.agent_id, self.status.value)
            await self.handle_task(task)
            self.status = AgentStatus.WAITING_FOR_INPUT
            publish_status(self.coordinator, self.agent_id, self.status.value)
            if not self.running:
                break

    async def handle_task(self, task):
        # Use a skill to process the task (here, just print it)
        print_message(self.agent_id, task)
        await asyncio.sleep(1)  # Simulate work

    def stop(self):
        self.running = False
        super().stop()
