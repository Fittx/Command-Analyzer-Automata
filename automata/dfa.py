from typing import Dict, List, Optional, Tuple

from .nfa import ALPHABET, NFA


class DFA:
    """The minimized DFA for the command language.

    States 0--20 are displayed as M0--M20. M7 is final and Md is the shared
    dead state completing all missing transitions. ``nfa`` is retained only
    for constructor compatibility with the simulator.
    """

    def __init__(self, nfa: Optional[NFA] = None):
        self.nfa = nfa
        self.states: List[int] = list(range(21))
        self.transitions: Dict[Tuple[int, str], int] = {}
        self.start = 0
        self.final_states = {7}
        self.dead_state = 21
        self._build()

    def _add(self, source: int, label: str, destination: int) -> None:
        if label == "[a-z]":
            chars = "abcdefghijklmnopqrstuvwxyz"
        elif label == "[a-z0-9]":
            chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        elif label == "space":
            chars = " "
        else:
            chars = label
        for ch in chars:
            self.transitions[(source, ch)] = destination

    def _build(self) -> None:
        rows = [
            (0, "E", 8), (0, "H", 10), (0, "L", 1), (0, "S", 13),
            (1, "O", 2), (2, "G", 3), (2, "A", 16),
            (3, "O", 4), (3, "I", 17), (4, "U", 5), (5, "T", 6), (6, ";", 7),
            (8, "X", 9), (9, "I", 5), (10, "E", 11), (11, "L", 12), (12, "P", 6),
            (13, "A", 14), (14, "V", 15), (15, "E", 18), (16, "D", 18), (17, "N", 18),
            (18, "space", 19), (19, "[a-z]", 20), (20, "[a-z0-9]", 20), (20, ";", 7),
        ]
        for source, label, destination in rows:
            self._add(source, label, destination)

        for state in self.states:
            for ch in ALPHABET:
                self.transitions.setdefault((state, ch), self.dead_state)
        for ch in ALPHABET:
            self.transitions[(self.dead_state, ch)] = self.dead_state
        self.states.append(self.dead_state)

    @property
    def state_count(self) -> int:
        return len(self.states)

    def transition(self, state: int, ch: str) -> int:
        return self.transitions.get((state, ch), self.dead_state)

    def accepts(self, text: str) -> bool:
        state = self.start
        for ch in text:
            state = self.transition(state, ch)
        return state in self.final_states

    def trace(self, text: str) -> List[dict]:
        state = self.start
        trace = [{"step": 0, "input": "START", "state": "M0", "state_id": state, "edge": None}]
        for step, ch in enumerate(text, 1):
            previous = state
            state = self.transition(state, ch)
            trace.append({
                "step": step, "input": "SPACE" if ch == " " else ch, "char": ch,
                "state": "qd" if state == self.dead_state else f"M{state}", "state_id": state,
                "from_state": previous, "edge": (previous, state),
            })
        return trace

    def grouped_edges(self, include_dead_transitions: bool = False) -> List[Tuple[int, int, str]]:
        """Group concrete transitions into readable diagram labels."""
        buckets: Dict[Tuple[int, int], List[str]] = {}
        for (source, ch), destination in self.transitions.items():
            buckets.setdefault((source, destination), []).append(ch)
        result = []
        for (source, destination), chars in buckets.items():
            if destination == self.dead_state and source != self.dead_state and not include_dead_transitions:
                continue
            if destination == self.dead_state and source != self.dead_state:
                label = self._dead_input_label(chars)
            else:
                label = "Σ" if source == self.dead_state else self._compress_labels(chars)
            result.append((source, destination, label))
        return sorted(result, key=lambda edge: (edge[0], edge[1], edge[2]))

    def _dead_input_label(self, chars: List[str]) -> str:
        valid = list(ALPHABET - set(chars))
        return "Σ" if not valid else "Σ − {" + self._compress_labels(valid) + "}"

    @staticmethod
    def _compress_labels(chars: List[str]) -> str:
        remaining = set(chars)
        parts = []
        lower, digits = set("abcdefghijklmnopqrstuvwxyz"), set("0123456789")
        if lower <= remaining:
            parts.append("[a-z]")
            remaining -= lower
        if digits <= remaining:
            parts.append("[0-9]")
            remaining -= digits
        for ch in sorted(remaining, key=lambda value: (value == " ", value)):
            parts.append("SPACE" if ch == " " else ch)
        return ", ".join(parts)
