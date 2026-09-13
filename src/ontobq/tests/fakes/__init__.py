"""In-process fakes for orchestration tests. Not mock.patch substitutes."""

from ontobq.tests.fakes.executor import FakeMutationExecutor

__all__ = ["FakeMutationExecutor"]
