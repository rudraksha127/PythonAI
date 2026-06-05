import unittest

from src.utils.swarm import AgentSwarm, TaskDecomposer


class TaskSwarmTests(unittest.TestCase):
    def test_decomposer_adds_dependencies_for_code_tasks(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose(
            {"title": "Async IO", "codes": ["print('hi')"], "id": "chunk-1"},
            {
                "basic": "basic prompt",
                "reasoning": "reasoning prompt",
                "code_review": "code review prompt",
                "multi_agent": "multi agent prompt",
            },
        )

        by_type = {task.task_type: task for task in tasks}

        self.assertEqual(by_type["code_review"].dependencies, ("basic",))
        self.assertEqual(by_type["multi_agent"].dependencies, ("reasoning",))

    def test_swarm_executes_all_ready_tasks(self):
        swarm = AgentSwarm(max_workers=2)
        tasks = TaskDecomposer().decompose(
            {"title": "Async IO", "codes": [], "id": "chunk-2"},
            {
                "basic": "basic prompt",
                "reasoning": "reasoning prompt",
                "version": "version prompt",
            },
        )

        results = swarm.execute(tasks, lambda task: {"task_type": task.task_type, "pairs": [task.task_type]})

        self.assertEqual(set(results), {task.task_id for task in tasks})
        basic_id = next(task.task_id for task in tasks if task.task_type == "basic")
        self.assertEqual(results[basic_id]["pairs"], ["basic"])


if __name__ == "__main__":
    unittest.main()
