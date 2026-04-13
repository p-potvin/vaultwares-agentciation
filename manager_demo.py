import asyncio
import uuid
from manager_base import Manager
from subagent import SubAgent

class DemoManager(Manager):
    async def run(self):
        print("[Manager] Starting demo...")
        # Spawn 2 subagents
        subagent_ids = []
        for i in range(2):
            sub_id = await self.spawn_subagent(SubAgent)
            subagent_ids.append(sub_id)
            print(f"[Manager] Spawned subagent: {sub_id}")
        # Assign tasks
        tasks = [f"Task-{uuid.uuid4().hex[:4]}" for _ in range(4)]
        for i, task in enumerate(tasks):
            sub_id = subagent_ids[i % len(subagent_ids)]
            target_agent = self.subagents[sub_id]["agent"]
            # Simulate sending a task (in real use, use Redis pub/sub)
            print(f"[Manager] Assigning '{task}' to subagent {sub_id}")
            # Here, you would publish to Redis; for demo, just call directly
            await target_agent.handle_task(task)
        # Wait for all tasks to complete
        await asyncio.sleep(3)
        print("[Manager] Shutting down...")
        await self.shutdown()

if __name__ == "__main__":
    manager = DemoManager("demo_manager")
    asyncio.run(manager.run())
