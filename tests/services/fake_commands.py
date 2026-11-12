"""A stand-in for system commands: records each argv, answers from rules."""

import subprocess
from collections.abc import Callable, Sequence

Rule = Callable[[list[str]], tuple[int, str] | None]


class FakeCommands:
    def __init__(self, *rules: Rule) -> None:
        self.calls: list[list[str]] = []
        self.rules = list(rules)

    def __call__(self, argv: Sequence[str]) -> subprocess.CompletedProcess:
        argv = list(argv)
        self.calls.append(argv)
        for rule in self.rules:
            answer = rule(argv)
            if answer is not None:
                code, out = answer
                return subprocess.CompletedProcess(argv, code, out, "" if code == 0 else out)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def joined(self) -> list[str]:
        return [" ".join(call) for call in self.calls]
