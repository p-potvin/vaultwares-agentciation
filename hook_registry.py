"""
HookRegistry — Central registry for agent lifecycle and event hooks.

Allows registration and triggering of hooks for agent lifecycle events:
- pre/post communication (send/receive)
- pre/post spawn/destruction
- pre/post dispatch
- pre/post code/PR management
- error/exception
- custom events

Usage:
    from hook_registry import hooks
    def my_hook(context): ...
    hooks.register('pre_communication', my_hook)
    hooks.trigger('pre_communication', context)
"""

class HookRegistry:
    def __init__(self):
        self._hooks = {}

    def register(self, event, func):
        self._hooks.setdefault(event, []).append(func)

    def unregister(self, event, func):
        if event in self._hooks and func in self._hooks[event]:
            self._hooks[event].remove(func)

    def trigger(self, event_name, *args, **kwargs):
        for func in self._hooks.get(event_name, []):
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(f"[Hook error in {event_name}]: {e}")

# Global hook registry instance
hooks = HookRegistry()
