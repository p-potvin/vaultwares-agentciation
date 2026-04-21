import os
import sys
import json
import time

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omx_integration.omx_worker import OMXWorker
from cheddar_bob import CheddarBob

class CheddarBobWorker(OMXWorker):
    """
    A specialized OMX Worker that integrates Cheddar Bob's pedantic UI logic.
    """
    def __init__(self, *args, **kwargs):
        # The role is already passed in kwargs by the TeamOrchestrator
        super().__init__(*args, **kwargs)
        # Cheddar Bob needs a target URL or file, we'll default to localhost:3000 for web apps
        self.bob = CheddarBob(target_url="localhost:3000")

    def execute_task(self, task_id: str, subject: str, description: str, output_files: dict):
        """
        Execute a UI/UX task with Cheddar Bob's pedantic flair.
        """
        print(f"[{self.worker_id}] Cheddar Bob is taking over for task: {subject}")
        print(f"[{self.worker_id}] 'I hope you didn't use #FF0000 for a primary button. That's for amateurs.'")
        
        # 1. Run Bob's critique logic (simulated or real if URL is up)
        self.bob.boot_up()
        
        # If the description contains indicators for a visual scan, we do it
        if "scan" in description.lower() or "review" in description.lower():
            self.bob.run_environment_scan()
            self.bob.process_visual_verdict()
        
        # 2. Apply fixes / Write files
        # We'll use the standard write logic from super, but add Bob's "disgust"
        created_files = super().execute_task(task_id, subject, description, output_files)
        
        print(f"[{self.worker_id}] 'There. I've corrected your sloppy work. The grid is now mathematically perfect.'")
        self.bob.shut_down()
        
        return created_files

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Cheddar Bob as an OMX Worker.")
    parser.add_argument("--id", required=True, help="Worker ID")
    parser.add_argument("--team", required=True, help="Team name")
    parser.add_argument("--project", required=True, help="Project directory")
    args = parser.parse_args()

    worker = CheddarBobWorker(
        worker_id=args.id,
        team_name=args.team,
        project_dir=args.project
    )
    worker.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        worker.stop()
