# CommandAutomaton

Tkinter-based **Automata Command Recognizer & Simulator**. Test the command language,
read the validation explanation, inspect real NFA/DFA traces, and view the corresponding
highlighted path in either diagram. The UI intentionally contains NFA and DFA diagrams only.

## Run

```bash
python main.py
```

No third-party packages are required.

## Using the visualizer

- **TEST** is the primary workflow: enter an input and select **VALIDATE**.
- **NFA** and **DFA** select the corresponding generated automaton diagram.
- **STATE TRACE** and **HISTORY** expose the simulator output; selecting a history row re-runs
  its recorded result without creating a duplicate entry.
- Mouse wheel zooms a diagram; Shift+drag or middle-drag pans it. FIT, RESET, and zoom controls
  are provided beneath the graph.

## Language

- `LOGOUT;`
- `EXIT;`
- `HELP;`
- `LOGIN <identifier>;`
- `SAVE <identifier>;`
- `LOAD <identifier>;`

Identifier:

```text
[a-z][a-z0-9]*
```

Whitespace is exact: argument commands contain exactly one normal space.

## Important fix

The identifier-loop NFA states `q28`, `q36`, and `q44` each have TWO outgoing transitions:

- `[a-z0-9]` → itself
- `;` → accepting state

Keeping both transitions is essential. If the semicolon transition is overwritten, inputs such as `LOGIN alice;` fail and the corresponding accepting DFA states disappear.

The visualizer uses the minimized DFA transition table: states `M0`–`M20`, accepting state `M7`, and one shared dead state `Md`. Every otherwise undefined input transitions to `Md`, which loops for the complete alphabet.
