from collections import defaultdict
from typing import Dict, Set, FrozenSet, List, Tuple

ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ;")

class NFA:
    """NFA for the project's command language."""

    def __init__(self):
        self.states = set(range(46))
        self.start = 0
        self.final_states = {8, 14, 20, 29, 37, 45}
        self.epsilon = defaultdict(set)
        self.transitions = defaultdict(lambda: defaultdict(set))

        self.epsilon[0] = {1, 9, 15, 21, 30, 38}

        rows = [
            (1,"L",2),(2,"O",3),(3,"G",4),(4,"O",5),(5,"U",6),(6,"T",7),(7,";",8),
            (9,"E",10),(10,"X",11),(11,"I",12),(12,"T",13),(13,";",14),
            (15,"H",16),(16,"E",17),(17,"L",18),(18,"P",19),(19,";",20),
            (21,"L",22),(22,"O",23),(23,"G",24),(24,"I",25),(25,"N",26),(26," ",27),
            (27,"[a-z]",28),(28,"[a-z0-9]",28),(28,";",29),
            (30,"S",31),(31,"A",32),(32,"V",33),(33,"E",34),(34," ",35),
            (35,"[a-z]",36),(36,"[a-z0-9]",36),(36,";",37),
            (38,"L",39),(39,"O",40),(40,"A",41),(41,"D",42),(42," ",43),
            (43,"[a-z]",44),(44,"[a-z0-9]",44),(44,";",45),
        ]
        for src, symbol, dst in rows:
            self.transitions[src][symbol].add(dst)

    @staticmethod
    def symbol_matches(label: str, ch: str) -> bool:
        return (
            label == ch
            or (label == "[a-z]" and ch in "abcdefghijklmnopqrstuvwxyz")
            or (label == "[a-z0-9]" and (ch in "abcdefghijklmnopqrstuvwxyz" or ch in "0123456789"))
        )

    def epsilon_closure(self, states: Set[int]) -> FrozenSet[int]:
        closure = set(states)
        stack = list(states)
        while stack:
            state = stack.pop()
            for nxt in self.epsilon.get(state, set()):
                if nxt not in closure:
                    closure.add(nxt)
                    stack.append(nxt)
        return frozenset(closure)

    def move(self, states: Set[int], ch: str) -> Set[int]:
        result = set()
        for state in states:
            for label, destinations in self.transitions.get(state, {}).items():
                if self.symbol_matches(label, ch):
                    result.update(destinations)
        return result

    def accepts(self, text: str) -> bool:
        current = self.epsilon_closure({self.start})
        for ch in text:
            current = self.epsilon_closure(self.move(current, ch))
            if not current:
                return False
        return bool(current & self.final_states)

    def trace(self, text: str) -> List[dict]:
        current = self.epsilon_closure({self.start})
        trace = [{
            "step": 0,
            "input": "START",
            "state": f"{{{','.join(f'q{x}' for x in sorted(current))}}}",
            "states": sorted(current),
            "edges": [(0, dst, "ε") for dst in sorted(self.epsilon[0])],
        }]
        for step, ch in enumerate(text, 1):
            edges = []
            for src in current:
                for label, destinations in self.transitions.get(src, {}).items():
                    if self.symbol_matches(label, ch):
                        edges.extend((src, dst, label) for dst in destinations)
            moved = self.move(current, ch)
            current = self.epsilon_closure(moved)
            trace.append({
                "step": step,
                "input": "SPACE" if ch == " " else ch,
                "char": ch,
                "state": f"{{{','.join(f'q{x}' for x in sorted(current))}}}" if current else "∅",
                "states": sorted(current),
                "edges": edges,
            })
            if not current:
                break
        accepted = bool(current & self.final_states)
        return trace, accepted

    def path_trace(self, text: str) -> List[dict]:
        """Return one real NFA run: accepting if possible, otherwise longest.

        This is intentionally separate from ``trace``, which records the full
        active-state set.  It lets a path-only view show an actual NFA run
        without pretending the NFA has only one active state.
        """
        # (state, input index, rows); epsilons are retained as explicit steps.
        queue = [(self.start, 0, [{"step": 0, "input": "START", "state": "q0", "states": [0], "edges": []}])]
        best = queue[0][2]
        visited = set()
        while queue:
            state, index, rows = queue.pop(0)
            key = (state, index)
            if key in visited:
                continue
            visited.add(key)
            if index > best[-1].get("input_index", 0):
                best = rows
            if index == len(text) and state in self.final_states:
                return rows
            for destination in sorted(self.epsilon.get(state, set())):
                queue.append((destination, index, rows + [{
                    "step": len(rows), "input": "ε", "state": f"q{destination}",
                    "states": [destination], "edges": [(state, destination, "ε")], "input_index": index,
                }]))
            if index >= len(text):
                continue
            ch = text[index]
            for label, destinations in self.transitions.get(state, {}).items():
                if self.symbol_matches(label, ch):
                    for destination in sorted(destinations):
                        queue.append((destination, index + 1, rows + [{
                            "step": len(rows), "input": "SPACE" if ch == " " else ch,
                            "char": ch, "state": f"q{destination}", "states": [destination],
                            "edges": [(state, destination, label)], "input_index": index + 1,
                        }]))
        return best

    def transitions_for_diagram(self) -> List[Tuple[int, str, int]]:
        rows = [
            (src, "ε", dst)
            for src, destinations in self.epsilon.items()
            for dst in sorted(destinations)
        ]
        for src in sorted(self.transitions):
            for label, dsts in self.transitions[src].items():
                for dst in sorted(dsts):
                    rows.append((src, label, dst))
        return rows
