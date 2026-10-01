from automata.nfa import NFA, ALPHABET
from automata.dfa import DFA
from automata.regex import matches


class AutomatonSimulator:
    """Single source of truth for validation, traces, diagnostics and diagrams."""
    def __init__(self):
        self.nfa = NFA()
        self.dfa = DFA(self.nfa)

    def alphabet_valid(self, text):
        bad = [ch for ch in text if ch not in ALPHABET]
        return not bad, bad

    def check(self, text):
        alphabet_ok, bad = self.alphabet_valid(text)
        if not alphabet_ok:
            nfa_trace, _ = self.nfa.trace(text)
            nfa_path_trace = self.nfa.path_trace(text)
            dfa_trace = self.dfa.trace(text)
            return {"input": text, "alphabet": False, "bad_symbols": bad,
                    "regex": False, "nfa": False, "dfa": False, "accepted": False,
                    "nfa_trace": nfa_trace, "nfa_path_trace": nfa_path_trace, "dfa_trace": dfa_trace,
                    "reason": "Input contains symbols outside the automaton alphabet.",
                    "explanation": f"Unsupported symbol(s): {', '.join(repr(ch) for ch in bad)}.",
                    "final_nfa_state": nfa_trace[-1]["state"],
                    "final_dfa_state": dfa_trace[-1]["state"]}
        regex_ok = matches(text)
        nfa_trace, nfa_ok = self.nfa.trace(text)
        nfa_path_trace = self.nfa.path_trace(text)
        dfa_trace = self.dfa.trace(text)
        dfa_ok = self.dfa.accepts(text)
        accepted = dfa_ok
        return {"input": text, "alphabet": True, "bad_symbols": [], "regex": regex_ok,
                "nfa": nfa_ok, "dfa": dfa_ok, "accepted": accepted,
                "nfa_trace": nfa_trace, "nfa_path_trace": nfa_path_trace, "dfa_trace": dfa_trace,
                "reason": "Valid command." if accepted else self._rejection_reason(text),
                "explanation": self._explanation(text, accepted),
                "final_nfa_state": nfa_trace[-1]["state"],
                "final_dfa_state": dfa_trace[-1]["state"]}

    def _rejection_reason(self, text):
        # Diagnosis follows a rejected NFA/DFA run; it never decides acceptance.
        if not text.endswith(";"):
            return "Missing terminating semicolon ';'."
        command = text.split(" ", 1)[0].rstrip(";")
        argument, no_argument = {"LOGIN", "SAVE", "LOAD"}, {"LOGOUT", "EXIT", "HELP"}
        if command in argument:
            remainder = text[len(command):]
            if remainder == ";":
                return "Missing identifier; expected one space followed by [a-z][a-z0-9]*."
            if not remainder.startswith(" ") or remainder.startswith("  "):
                return "Argument commands require exactly one space between the command and identifier."
            identifier = remainder[1:-1]
            if not identifier:
                return "Missing identifier."
            if not ("a" <= identifier[0] <= "z"):
                return "Identifier must begin with a lowercase letter."
            if any(not ("a" <= ch <= "z" or "0" <= ch <= "9") for ch in identifier):
                return "Identifier may contain only lowercase letters and digits."
        if command in no_argument:
            return f"This command takes no identifier; use exactly {command};"
        if command.upper() in argument | no_argument:
            return "Keywords must be uppercase."
        return "Input does not match any command path in the automaton."

    def _explanation(self, text, accepted):
        if not accepted:
            return self._rejection_reason(text)
        command = text.split(" ", 1)[0].rstrip(";")
        if command in {"LOGOUT", "EXIT", "HELP"}:
            return f"{command} is a valid no-argument command and ends with ';'."
        identifier = text.split(" ", 1)[1][:-1]
        return (f"{command} is valid: exactly one space, identifier '{identifier}' starts "
                "with lowercase and uses only lowercase letters or digits, then ends with ';'.")
