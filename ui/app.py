import tkinter as tk
from tkinter import ttk
import math
from datetime import datetime

from automata.dfa import DFA
from automata.nfa import NFA
from simulator.simulator import AutomatonSimulator

BG = "#07090b"
PANEL = "#0d1115"
PANEL2 = "#11161b"
BORDER = "#202830"
TEXT = "#e7edf2"
MUTED = "#82909d"
ACCENT = "#6ee7b7"
ACCENT2 = "#5eead4"
RED = "#fb7185"
GRID = "#151b20"
NODE = "#0d1318"
NODE_BORDER = "#3a4650"
TRACE = "#facc15"


class DiagramCanvas(tk.Canvas):
    """Scrollable/zoomable automaton diagram canvas."""

    def __init__(self, master, prefix="D", final_states=None, dead_state=None, bg=BG, **kwargs):
        super().__init__(master, bg=bg, highlightthickness=0, **kwargs)
        self.prefix = prefix
        self.final_states = set(final_states or [])
        self.dead_state = dead_state
        self.dead_aliases = set()
        self.zoom = 1.0
        self.offset_x = 40
        self.offset_y = 40
        self.nodes = {}
        self.edges = []
        self.edge_routes = {}
        self.edge_label_positions = {}
        self.loop_sides = {}
        self.start_state = None
        self.active_states = set()
        self.current_state = None
        self.active_edges = set()
        self.extra_edges = []
        self.focused = False
        self.path_only = False
        self.drag_start = None

        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.12))
        self.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.12))
        self.bind("<ButtonPress-2>", self._pan_start)
        self.bind("<B2-Motion>", self._pan_move)
        self.bind("<ButtonRelease-2>", self._pan_end)
        self.bind("<ButtonPress-1>", self._left_pan_start)
        self.bind("<B1-Motion>", self._left_pan_move)
        self.bind("<ButtonRelease-1>", self._pan_end)

    def _wheel(self, event):
        self._zoom_at(event.x, event.y, 1.12 if event.delta > 0 else 1 / 1.12)

    def _zoom_at(self, mx, my, factor):
        old = self.zoom
        new = max(0.35, min(3.0, old * factor))
        if abs(new - old) < 1e-9:
            return
        # Keep the point beneath the cursor fixed while zooming.
        world_x = (mx - self.offset_x) / old
        world_y = (my - self.offset_y) / old
        self.zoom = new
        self.offset_x = mx - world_x * new
        self.offset_y = my - world_y * new
        self.render()

    def _pan_start(self, event):
        self.drag_start = (event.x, event.y, self.offset_x, self.offset_y)

    def _left_pan_start(self, event):
        # Shift + left drag pans; ordinary click does nothing.
        if event.state & 0x0001:
            self.drag_start = (event.x, event.y, self.offset_x, self.offset_y)

    def _pan_move(self, event):
        if self.drag_start is None:
            return
        x, y, ox, oy = self.drag_start
        self.offset_x = ox + event.x - x
        self.offset_y = oy + event.y - y
        self.render()

    def _left_pan_move(self, event):
        if self.drag_start is not None:
            self._pan_move(event)

    def _pan_end(self, _event):
        self.drag_start = None

    def _draw_grid(self):
        """Draw the dark graph-paper background at screen coordinates."""
        self.delete("grid")
        w = max(self.winfo_width(), 800)
        h = max(self.winfo_height(), 600)
        spacing = max(12, int(28 * self.zoom))
        x0 = -(self.offset_x % spacing)
        y0 = -(self.offset_y % spacing)
        for x in range(int(x0), w + spacing, spacing):
            self.create_line(x, 0, x, h, fill=GRID, width=1, tags="grid")
        for y in range(int(y0), h + spacing, spacing):
            self.create_line(0, y, w, y, fill=GRID, width=1, tags="grid")
        self.tag_lower("grid")

    def clear(self):
        self.delete("all")

    def fit(self):
        if not self.nodes:
            return
        xs = [p[0] for p in self.nodes.values()]
        ys = [p[1] for p in self.nodes.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        graph_w = max_x - min_x + 180
        graph_h = max_y - min_y + 180
        cw = max(self.winfo_width(), 600)
        ch = max(self.winfo_height(), 500)
        self.zoom = max(0.35, min(1.8, min(cw / graph_w, ch / graph_h)))
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.offset_x = cw / 2 - cx * self.zoom
        self.offset_y = ch / 2 - cy * self.zoom
        self.render()

    def reset(self):
        self.zoom = 1.0
        self.offset_x = 40
        self.offset_y = 40
        self.render()

    def _p(self, x, y):
        return x * self.zoom + self.offset_x, y * self.zoom + self.offset_y

    def _node_radius(self):
        return max(20, 28 * self.zoom)

    def _diagram_font_size(self, base, minimum):
        """Scale text while retaining a readable minimum at small zoom."""
        return max(minimum, int(base * max(self.zoom, .72)))

    def _arrow_shape(self):
        z = max(self.zoom, .5)
        return (9 * z, 11 * z, 4 * z)

    def _node_label(self, state):
        if self.prefix == "D":
            if state == self.dead_state:
                return "qd"
            return f"D{state}"
        if self.prefix == "M":
            if state == self.dead_state or state in self.dead_aliases:
                return "qd"
            return f"M{state}"
        return f"q{state}"

    # ---- geometry helpers -------------------------------------------------
    @staticmethod
    def _toward(a, b, dist):
        """Point `dist` away from a in the direction of b."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1
        return a[0] + dx / d * dist, a[1] + dy / d * dist

    def _circle_hit(self, outside, hint, center, r):
        """First point where the ray outside -> hint meets a circle.

        Used so every arrow starts and ends exactly on a node's outline
        (arrowheads are no longer hidden underneath the node fill).
        """
        dx, dy = hint[0] - outside[0], hint[1] - outside[1]
        a = dx * dx + dy * dy
        if a == 0:
            return hint
        fx, fy = outside[0] - center[0], outside[1] - center[1]
        b = 2 * (dx * fx + dy * fy)
        c = fx * fx + fy * fy - r * r
        disc = b * b - 4 * a * c
        if disc < 0:
            return self._toward(center, outside, r)
        t = (-b - math.sqrt(disc)) / (2 * a)
        return outside[0] + t * dx, outside[1] + t * dy

    def render(self):
        self.delete("all")
        self._draw_grid()
        r = self._node_radius()

        visible_nodes = self.active_states if self.path_only else set(self.nodes)
        if self.path_only and not visible_nodes:
            self.create_text(self.winfo_width() / 2, self.winfo_height() / 2,
                             text="Enter a command to visualize its automaton path.",
                             fill=MUTED, font=("Segoe UI", 12, "italic"))
            return
        if self.start_state in visible_nodes:
            x, y = self._p(*self.nodes[self.start_state])
            self.create_line(
                x - r - 38 * self.zoom, y, x - r - 2, y,
                fill="#c6d0d8", width=1.5, arrow=tk.LAST,
                arrowshape=(8 * max(self.zoom, .5), 10 * max(self.zoom, .5), 4 * max(self.zoom, .5)),
            )
            self.create_text(x - r - 20 * self.zoom, y - 12, text="START", fill=MUTED,
                             font=("Segoe UI", self._diagram_font_size(8, 7), "bold"))

        for edge_index, (src, dst, label) in enumerate(self.edges + self.extra_edges):
            if src not in self.nodes or dst not in self.nodes:
                continue
            if self.path_only and (src not in visible_nodes or dst not in visible_nodes):
                continue
            c1 = self._p(*self.nodes[src])
            c2 = self._p(*self.nodes[dst])
            active = edge_index in self.active_edges or edge_index >= len(self.edges)
            color = ACCENT if active else ("#273038" if self.focused else "#5b6670")
            width = 2.4 if active else 1.2
            label_color = ACCENT if active else "#c6d0d8"
            label_font = ("Segoe UI", self._diagram_font_size(9, 8), "bold")

            if src == dst:
                self._draw_loop(c1[0], c1[1], r, label, color, width,
                                self.loop_sides.get(src, "top"))
                continue

            route = self.edge_routes.get((src, dst))
            label_world = self.edge_label_positions.get((src, dst))

            if route and len(route) >= 2:
                # Explicit elbow route: waypoints are fixed by the layout;
                # only the two ends are snapped onto the node outlines.
                pts = [self._p(*pt) for pt in route]
                first = self._circle_hit(pts[1], pts[0], c1, r)
                last = self._circle_hit(pts[-2], pts[-1], c2, r)
                pts[0], pts[-1] = first, last
                self.create_line(*(v for pt in pts for v in pt),
                                 fill=color, width=width, arrow=tk.LAST,
                                 arrowshape=self._arrow_shape(), joinstyle=tk.MITER)
                if label_world:
                    lx, ly = self._p(*label_world)
                else:
                    segs = list(zip(pts, pts[1:]))
                    a, b = max(segs, key=lambda s: math.dist(*s))
                    lx, ly = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 11
                self.create_text(lx, ly, text=label, fill=label_color, font=label_font)
                continue

            if label_world:
                # Straight arrow between node outlines.
                start = self._toward(c1, c2, r)
                end = self._toward(c2, c1, r)
                self.create_line(*start, *end, fill=color, width=width, arrow=tk.LAST,
                                 arrowshape=self._arrow_shape())
                lx, ly = self._p(*label_world)
                self.create_text(lx, ly, text=label, fill=label_color, font=label_font)
                continue

            # Default (used by the NFA): gently curved edge.
            dx, dy = c2[0] - c1[0], c2[1] - c1[1]
            dist = max(math.hypot(dx, dy), 1)
            nx, ny = -dy / dist, dx / dist
            bend = min(38 * self.zoom, max(0, dist * 0.12))
            sign = -1 if (int(src) + int(dst)) % 2 else 1
            cx = (c1[0] + c2[0]) / 2 + nx * bend * sign
            cy = (c1[1] + c2[1]) / 2 + ny * bend * sign
            start = self._toward(c1, (cx, cy), r)
            end = self._toward(c2, (cx, cy), r)
            self.create_line(*start, cx, cy, *end, fill=color, width=width, smooth=True,
                             arrow=tk.LAST, arrowshape=self._arrow_shape())
            self.create_text(cx, cy - 10 * max(self.zoom, .6), text=label,
                             fill=label_color, font=label_font)

        # Nodes.
        for state, (x, y) in self.nodes.items():
            if self.path_only and state not in visible_nodes:
                continue
            px, py = self._p(x, y)
            active = state in self.active_states
            current = state == self.current_state
            accepting = state in self.final_states
            dead = state == self.dead_state or state in self.dead_aliases
            outline = RED if current and dead else (ACCENT if current else (TRACE if active else ("#273038" if self.focused else NODE_BORDER)))
            width = 3 if current else (2 if active else 1)
            fill = "#34141d" if current and dead else ("#10231d" if current else ("#0a0e12" if self.focused and not active else NODE))

            self.create_oval(px-r, py-r, px+r, py+r,
                             fill=fill, outline=outline, width=width)
            if accepting:
                rr = r - max(4, 5 * self.zoom)
                self.create_oval(px-rr, py-rr, px+rr, py+rr,
                                 outline=outline, width=max(1, int(width * .8)))
            self.create_text(
                px, py, text=self._node_label(state), fill=(TEXT if active or current or not self.focused else MUTED),
                font=("Segoe UI", self._diagram_font_size(10, 9), "bold")
            )

        self.configure(scrollregion=(-2000, -2000, 6000, 5000))

    def _draw_loop(self, x, y, r, label, color, width, side="top"):
        """Self-loop bulging out of the node on the requested side."""
        angle = math.radians({"top": -90, "right": 0, "bottom": 90, "left": 180}.get(side, -90))
        spread = math.radians(38)
        lift = r * 3.4
        dx, dy = math.cos(angle), math.sin(angle)

        def on(a, dist):
            return x + dist * math.cos(a), y + dist * math.sin(a)

        p0 = on(angle - spread, r)
        p3 = on(angle + spread, r)
        c1 = on(angle - spread * 1.5, r + lift)
        c2 = on(angle + spread * 1.5, r + lift)
        pts = []
        for i in range(25):
            t = i / 24
            m = 1 - t
            pts.append((
                m**3 * p0[0] + 3 * m * m * t * c1[0] + 3 * m * t * t * c2[0] + t**3 * p3[0],
                m**3 * p0[1] + 3 * m * m * t * c1[1] + 3 * m * t * t * c2[1] + t**3 * p3[1],
            ))
        self.create_line(*(v for p in pts for v in p), fill=color, width=width,
                         arrow=tk.LAST, arrowshape=self._arrow_shape())
        label_dist = r * 1.8 + 10 + 4 * self.zoom
        self.create_text(x + dx * label_dist, y + dy * label_dist, text=label, fill=color,
                         font=("Segoe UI", self._diagram_font_size(8, 8), "bold"))

    def set_graph(self, nodes, edges, final_states=None, start_state=None, dead_state=None, dead_aliases=None,
                  edge_routes=None, edge_label_positions=None, loop_sides=None):
        self.nodes = dict(nodes)
        self.edges = list(edges)
        self.edge_routes = dict(edge_routes or {})
        self.edge_label_positions = dict(edge_label_positions or {})
        self.loop_sides = dict(loop_sides or {})
        self.start_state = start_state
        if final_states is not None:
            self.final_states = set(final_states)
        self.dead_state = dead_state
        self.dead_aliases = set(dead_aliases or [])
        self.active_states = set()
        self.current_state = None
        self.active_edges = set()
        self.extra_edges = []
        self.render()

    def highlight(self, active_states, current_state=None, active_edges=None, focused=True, path_only=False, extra_edges=None):
        self.active_states = set(active_states)
        self.current_state = current_state
        self.active_edges = set(active_edges or [])
        self.focused = focused
        self.path_only = path_only
        self.extra_edges = list(extra_edges or [])
        self.render()

    def show_full(self, show=True):
        self.path_only = not show
        self.render()


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Automata Command Recognizer")
        self.root.geometry("1280x820")
        self.root.minsize(760, 560)
        self.root.configure(bg=BG)

        self.sim = AutomatonSimulator()
        self.dfa = self.sim.dfa
        self.nfa = self.sim.nfa
        self.last = None
        self.history = []
        self.trace_step = 0

        self._style()
        self._build()
        self._load_diagrams()

    def _style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        padding=(15, 9), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", PANEL2)],
                  foreground=[("selected", ACCENT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                        borderwidth=0)
        style.map("Treeview", background=[("selected", "#153329")],
                  foreground=[("selected", TEXT)])

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=22, pady=(18, 10))
        tk.Label(header, text="COMMAND AUTOMATON", bg=BG, fg=TEXT,
                 font=("Segoe UI", 19, "bold")).pack(side="left")
        tk.Label(header, text="REGULAR EXPRESSION  ->  NFA  ->  DFA",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=18)
        tk.Label(header, text="READY", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="right")

        nav = tk.Frame(self.root, bg=BG)
        nav.pack(fill="x", padx=22, pady=(0, 8))
        for label, command in (("TEST", self.focus_test), ("NFA", self.focus_nfa),
                               ("DFA", self.focus_dfa), ("TRACE", self.focus_trace),
                               ("HISTORY", self.focus_history)):
            tk.Button(nav, text=label, command=command, bg=PANEL, fg=MUTED, relief="flat",
                      activebackground=PANEL2, activeforeground=ACCENT,
                      font=("Segoe UI", 8, "bold"), padx=11, pady=6).pack(side="left", padx=(0, 4))

        controls = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        controls.pack(fill="x", padx=22, pady=(0, 10))
        tk.Label(controls, text="Commands use uppercase; identifiers use lowercase letters and digits.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(8, 0))
        input_row = tk.Frame(controls, bg=PANEL)
        input_row.pack(fill="x", padx=14, pady=(6, 4))
        tk.Label(input_row, text="COMMAND INPUT", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        self.entry = tk.Entry(input_row, bg="#080b0e", fg=TEXT, insertbackground=ACCENT,
                              relief="flat", font=("Consolas", 12), width=42)
        self.entry.pack(side="left", fill="x", expand=True, padx=4, ipady=7)
        self.entry.insert(0, "LOGIN alice;")
        self.entry.bind("<Return>", lambda _e: self.check())
        tk.Button(input_row, text="VALIDATE", command=self.check, bg=ACCENT, fg="#06110c",
                  activebackground=ACCENT2, activeforeground="#06110c", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=18, pady=8).pack(side="right", padx=(8, 0))
        examples = tk.Frame(controls, bg=PANEL)
        examples.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(examples, text="Examples", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        for sample in ("LOGOUT;", "SAVE report1;", "LOAD data9;"):
            tk.Button(examples, text=sample, command=lambda s=sample: self.set_input(s),
                      bg=PANEL2, fg=MUTED, activebackground="#18201f",
                      relief="flat", font=("Consolas", 9), padx=8).pack(side="left", padx=3)

        self.status = tk.Label(examples, text="Ready", bg=PANEL, fg=MUTED,
                               font=("Segoe UI", 10, "bold"))
        self.status.pack(side="right")

        body = tk.PanedWindow(self.root, orient="horizontal", bg=BG, sashwidth=5,
                              showhandle=False, bd=0)
        body.pack(fill="both", expand=True, padx=22, pady=(0, 22))

        left = tk.Frame(body, bg=PANEL, width=400)
        right = tk.Frame(body, bg=PANEL)
        body.add(left, minsize=270)
        body.add(right, minsize=420)

        tk.Label(left, text="VALIDATION RESULTS", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(15, 8))
        self.cards_frame = tk.Frame(left, bg=PANEL)
        self.cards_frame.pack(fill="x", padx=12)
        self.cards = {}
        for i, name in enumerate(("ALPHABET", "REGEX", "NFA", "DFA", "RESULT")):
            card = tk.Frame(self.cards_frame, bg=PANEL2,
                            highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=i//2, column=i%2, sticky="ew", padx=3, pady=3)
            self.cards_frame.grid_columnconfigure(i % 2, weight=1)
            tk.Label(card, text=name, bg=PANEL2, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=9, pady=(7, 1))
            lab = tk.Label(card, text="—", bg=PANEL2, fg=MUTED,
                           font=("Segoe UI", 10, "bold"))
            lab.pack(anchor="w", padx=9, pady=(0, 8))
            self.cards[name] = lab

        tk.Label(left, text="EXPLANATION", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(14, 4))
        self.explanation = tk.Label(left, text="Enter a command and select VALIDATE to see why it is accepted or rejected.",
                                    bg=PANEL2, fg=TEXT, justify="left", anchor="w", wraplength=300,
                                    font=("Segoe UI", 9), padx=10, pady=8)
        self.explanation.pack(fill="x", padx=12)
        left.bind("<Configure>", self._resize_left_content)

        tk.Label(left, text="STATE TRACE", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(18, 7))
        trace_tabs = ttk.Notebook(left)
        trace_tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12), ipady=70)
        self.trace_tabs = trace_tabs
        self.trace_views = {}
        for tabname, key in (("DFA", "dfa_trace"), ("NFA", "nfa_trace")):
            frame = tk.Frame(trace_tabs, bg=PANEL2)
            trace_tabs.add(frame, text=tabname)
            tv = ttk.Treeview(frame, columns=("step", "input", "state"), show="headings")
            for c, w in (("step", 55), ("input", 90), ("state", 180)):
                tv.heading(c, text=c.upper())
                tv.column(c, width=w, anchor="center")
            sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=sb.set, xscrollcommand=hsb.set)
            tv.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
            sb.pack(side="right", fill="y", pady=5)
            hsb.pack(side="bottom", fill="x", padx=5)
            self.trace_views[key] = tv

        history_frame = tk.Frame(trace_tabs, bg=PANEL2)
        trace_tabs.add(history_frame, text="HISTORY")
        history_actions = tk.Frame(history_frame, bg=PANEL2)
        history_actions.pack(fill="x", padx=5, pady=5)
        tk.Button(history_actions, text="CLEAR HISTORY", command=self.clear_history, bg=PANEL2, fg=RED,
                  relief="flat", font=("Segoe UI", 8, "bold")).pack(side="right")
        self.history_view = ttk.Treeview(history_frame, columns=("result", "input", "time"), show="headings")
        for column, width in (("result", 85), ("input", 160), ("time", 115)):
            self.history_view.heading(column, text=column.upper())
            self.history_view.column(column, width=width, anchor="center")
        history_sb = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_view.yview)
        history_hsb = ttk.Scrollbar(history_frame, orient="horizontal", command=self.history_view.xview)
        self.history_view.configure(yscrollcommand=history_sb.set, xscrollcommand=history_hsb.set)
        self.history_view.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=(0, 5))
        history_sb.pack(side="right", fill="y", pady=(0, 5))
        history_hsb.pack(side="bottom", fill="x", padx=5)
        self.history_view.bind("<<TreeviewSelect>>", self.open_history)

        tabs = ttk.Notebook(right)
        tabs.pack(fill="both", expand=True)

        dfa_tab = tk.Frame(tabs, bg=BG)
        nfa_tab = tk.Frame(tabs, bg=BG)
        tabs.add(dfa_tab, text="MINIMIZED DFA • 22 STATES")
        tabs.add(nfa_tab, text="NFA • 46 STATES")

        self.dfa_canvas = DiagramCanvas(dfa_tab, prefix="M", final_states=self.dfa.final_states,
                                        dead_state=self.dfa.dead_state)
        self.nfa_canvas = DiagramCanvas(nfa_tab, prefix="q", final_states=self.nfa.final_states)
        self.dfa_canvas.pack(fill="both", expand=True)
        self.nfa_canvas.pack(fill="both", expand=True)

        btnbar = tk.Frame(right, bg=PANEL2)
        btnbar.pack(fill="x")
        for label, cmd in (("FIT", self.fit_current), ("RESET", self.reset_current),
                           ("ZOOM +", lambda: self.zoom_current(1.15)),
                           ("ZOOM −", lambda: self.zoom_current(1/1.15))):
            tk.Button(btnbar, text=label, command=cmd, bg=PANEL2, fg=MUTED,
                      activebackground="#1a2228", relief="flat",
                      font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="left", padx=3, pady=4)
        tk.Label(btnbar, text="Mouse wheel: zoom  •  Shift+drag / middle drag: pan",
                 bg=PANEL2, fg=MUTED, font=("Segoe UI", 8)).pack(side="right", padx=10)

        tk.Button(btnbar, text="TRACE PREV", command=lambda: self.move_trace(-1), bg=PANEL2, fg=MUTED,
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=7).pack(side="left", padx=3, pady=4)
        tk.Button(btnbar, text="TRACE NEXT", command=lambda: self.move_trace(1), bg=PANEL2, fg=MUTED,
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=7).pack(side="left", padx=3, pady=4)
        self.full_view = False
        tk.Button(btnbar, text="VIEW FULL", command=self.toggle_full_view, bg=PANEL2, fg=MUTED,
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=7).pack(side="left", padx=3, pady=4)
        self.diagram_tabs = tabs
        tabs.bind("<<NotebookTabChanged>>", lambda _e: self.fit_current())

    def current_canvas(self):
        index = self.diagram_tabs.index(self.diagram_tabs.select())
        return (self.dfa_canvas, self.nfa_canvas)[index]

    def _resize_left_content(self, event):
        """Reflow side-panel text and table columns as its pane is resized."""
        width = max(220, event.width - 48)
        self.explanation.config(wraplength=width)

        trace_width = max(210, event.width - 45)
        for view in self.trace_views.values():
            view.column("step", width=max(45, int(trace_width * .18)), stretch=False)
            view.column("input", width=max(65, int(trace_width * .30)), stretch=True)
            view.column("state", width=max(90, int(trace_width * .52)), stretch=True)
        self.history_view.column("result", width=max(70, int(trace_width * .26)), stretch=False)
        self.history_view.column("input", width=max(100, int(trace_width * .42)), stretch=True)
        self.history_view.column("time", width=max(95, int(trace_width * .32)), stretch=True)

    def focus_test(self):
        self.entry.focus_set()

    def focus_dfa(self):
        self.diagram_tabs.select(0)
        self.fit_current()

    def focus_nfa(self):
        self.diagram_tabs.select(1)
        self.fit_current()

    def focus_trace(self):
        self.trace_tabs.select(0)

    def focus_history(self):
        self.trace_tabs.select(2)

    def focus_guide(self):
        self.entry.focus_set()

    def toggle_full_view(self):
        self.full_view = not self.full_view
        for canvas in (self.dfa_canvas, self.nfa_canvas):
            canvas.show_full(self.full_view)

    def fit_current(self):
        self.root.update_idletasks()
        self.current_canvas().fit()

    def reset_current(self):
        self.current_canvas().reset()

    def zoom_current(self, factor):
        canvas = self.current_canvas()
        canvas.zoom = max(.35, min(3.0, canvas.zoom * factor))
        canvas.render()

    def set_input(self, value):
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        self.check()

    def _load_diagrams(self):
        # ------------------------------------------------------------------
        # DFA layout. Every coordinate below is read straight off the
        # reference diagram (pixel coordinates of the image) and multiplied
        # by K so the nodes (radius 28) have the same proportions as there.
        # ------------------------------------------------------------------
        K = 0.7

        def w(pt):
            return (pt[0] * K, pt[1] * K)

        img_positions = {
            # Shared start and LOG prefix.
            0: (200, 740), 1: (400, 740), 2: (600, 740), 3: (760, 580),
            # LOGOUT branch and final state.
            4: (960, 470), 5: (1160, 470), 6: (1360, 470), 7: (1700, 650),
            # EXIT and HELP lanes.
            8: (400, 360), 9: (600, 360),
            10: (400, 40), 11: (600, 40), 12: (800, 40),
            # SAVE, LOAD, LOGIN and the shared identifier suffix.
            13: (400, 1170), 14: (600, 1170), 15: (800, 1170), 16: (760, 980),
            17: (970, 720), 18: (970, 980), 19: (1320, 980), 20: (1520, 980),
            # qd nodes: 21 = the real dead state (right of D7),
            # 22 = top (HELP/EXIT lanes), 23 = bottom-left, 24 = centre-right.
            21: (1890, 650), 22: (600, 220), 23: (480, 950), 24: (1360, 670),
        }
        positions = {s: w(p) for s, p in img_positions.items()}
        assert set(range(self.dfa.state_count)).issubset(positions)

        dead_aliases = {22, 23, 24}
        dead_destinations = {
            0: 23, 1: 23, 2: 23,
            8: 22, 9: 22, 10: 22, 11: 22, 12: 22,
            3: 24, 4: 24, 5: 24, 6: 24, 17: 24,
            13: 23, 14: 23, 15: 23, 16: 23, 18: 24, 19: 24, 20: 24,
        }
        self.dfa_dead_alias_by_source = dead_destinations
        dfa_edges = [
            (source, dead_destinations.get(source, destination) if destination == self.dfa.dead_state else destination, label)
            for source, destination, label in self.dfa.grouped_edges(include_dead_transitions=True)
        ]
        # Each qd alias visibly loops for every following input.
        dfa_edges.extend((alias, alias, "Σ") for alias in dead_aliases)

        # Elbow routes (first/last point only give the direction; the canvas
        # snaps them onto the node outlines so arrowheads stay visible).
        img_routes = {
            (0, 8):   [(230, 712), (230, 360), (360, 360)],
            (0, 10):  [(172, 712), (172, 40), (360, 40)],
            (0, 13):  [(200, 780), (200, 1170), (360, 1170)],
            (2, 3):   [(640, 712), (760, 712), (760, 620)],
            (2, 16):  [(640, 768), (760, 768), (760, 940)],
            (3, 4):   [(785, 550), (785, 470), (920, 470)],
            (3, 17):  [(790, 606), (790, 720), (930, 720)],
            (9, 5):   [(640, 360), (1160, 360), (1160, 430)],
            (12, 6):  [(840, 40), (1360, 40), (1360, 430)],
            (6, 7):   [(1400, 470), (1700, 470), (1700, 610)],
            (20, 7):  [(1560, 980), (1700, 980), (1700, 690)],
            (15, 18): [(840, 1170), (970, 1170), (970, 1020)],
        }
        routes = {key: [w(p) for p in pts] for key, pts in img_routes.items()}

        img_labels = {
            # Straight edges.
            (0, 1): (305, 722), (1, 2): (520, 722),
            (4, 5): (1060, 455), (5, 6): (1260, 455),
            (8, 9): (500, 345),
            (10, 11): (505, 20), (11, 12): (695, 20),
            (13, 14): (500, 1155), (14, 15): (700, 1155),
            (16, 18): (860, 965), (17, 18): (950, 850),
            (18, 19): (1140, 965), (19, 20): (1418, 965),
            (7, 21): (1790, 635),
            # Elbow edges.
            (0, 8): (299, 345), (0, 10): (255, 20), (0, 13): (299, 1155),
            (2, 3): (700, 695), (2, 16): (700, 755),
            (3, 4): (860, 455), (3, 17): (870, 645),
            (9, 5): (940, 345), (12, 6): (955, 20),
            (6, 7): (1560, 455), (20, 7): (1620, 965),
            (15, 18): (990, 1095),
            # Edges into the dead-state aliases.
            (0, 23): (330, 855), (1, 23): (470, 825), (2, 23): (590, 845),
            (13, 23): (385, 1065), (14, 23): (530, 1095),
            (15, 23): (720, 1075), (16, 23): (650, 949),
            (8, 22): (440, 285), (9, 22): (650, 285),
            (10, 22): (445, 155), (11, 22): (565, 125), (12, 22): (680, 115),
            (3, 24): (990, 595), (4, 24): (1170, 565), (5, 24): (1290, 565),
            (6, 24): (1410, 565), (17, 24): (1120, 695),
            (18, 24): (1120, 855), (19, 24): (1280, 903), (20, 24): (1498, 835),
        }
        label_positions = {key: w(p) for key, p in img_labels.items()}

        # Side of the node on which each self-loop is drawn (as in the
        # reference diagram): D20 and the right-most qd on top, the others
        # on the side that is free of incoming arrows.
        loop_sides = {20: "top", 21: "top", 22: "right", 23: "left", 24: "right"}

        self.dfa_canvas.set_graph(positions, dfa_edges, self.dfa.final_states,
                                  start_state=self.dfa.start, dead_state=self.dfa.dead_state,
                                  dead_aliases=dead_aliases, edge_routes=routes,
                                  edge_label_positions=label_positions, loop_sides=loop_sides)

        # NFA layout mirrors the six epsilon branches in the supplied diagram.
        npos = {0: (70, 390)}
        branches = [
            ([1, 2, 3, 4, 5, 6, 7, 8], 70),
            ([9, 10, 11, 12, 13, 14], 170),
            ([15, 16, 17, 18, 19, 20], 270),
            ([21, 22, 23, 24, 25, 26, 27, 28, 29], 390),
            ([30, 31, 32, 33, 34, 35, 36, 37], 520),
            ([38, 39, 40, 41, 42, 43, 44, 45], 650),
        ]
        for ids, y in branches:
            for i, state in enumerate(ids):
                npos[state] = (180 + i * 112, y)
        assert len(npos) == 46
        nedges = [(src, dst, label) for src, label, dst in self.nfa.transitions_for_diagram()]
        self.nfa_canvas.set_graph(npos, nedges, self.nfa.final_states,
                                  start_state=self.nfa.start)
        self.dfa_canvas.show_full(False)
        self.nfa_canvas.show_full(False)

        self.root.after(250, self._fit_all)

    def _fit_all(self):
        for canvas in (self.dfa_canvas, self.nfa_canvas):
            canvas.fit()

    def _set_card(self, name, ok):
        lab = self.cards[name]
        lab.config(text="PASS" if ok else "FAIL", fg=ACCENT if ok else RED)

    def _trace_state_ids(self, rows):
        return [r["state_id"] for r in rows if r.get("state_id") is not None]

    def _dfa_visual_trace_ids(self, rows):
        """Map the one real dead state onto the qd alias that was entered."""
        visual_ids = []
        aliases = self.dfa_canvas.dead_aliases
        for row in rows:
            state_id = row.get("state_id")
            if state_id != self.dfa.dead_state:
                visual_ids.append(state_id)
                continue
            edge = row.get("edge")
            if edge and edge[0] != self.dfa.dead_state:
                visual_ids.append(self.dfa_dead_alias_by_source.get(edge[0], self.dfa.dead_state))
            elif visual_ids and visual_ids[-1] in aliases | {self.dfa.dead_state}:
                visual_ids.append(visual_ids[-1])
            else:
                visual_ids.append(self.dfa.dead_state)
        return [state_id for state_id in visual_ids if state_id is not None]

    def move_trace(self, direction):
        if not self.last:
            return
        maximum = max(len(self.last["dfa_trace"]), len(self.last["nfa_path_trace"])) - 1
        self.trace_step = max(0, min(maximum, self.trace_step + direction))
        self._highlight_trace_step()

    def _highlight_trace_step(self):
        """Draw only a prefix of the actual simulator traces."""
        result = self.last
        if not result:
            return
        drows = result["dfa_trace"][:self.trace_step + 1]
        nrows = result["nfa_path_trace"][:self.trace_step + 1]
        dfa_ids = self._dfa_visual_trace_ids(drows)
        nfa_ids = [sid for row in nrows for sid in row.get("states", [])]
        dfa_pairs = set(zip(dfa_ids, dfa_ids[1:]))
        nfa_taken = {edge for row in nrows for edge in row.get("edges", [])}
        dfa_edges = [i for i, (src, dst, _label) in enumerate(self.dfa_canvas.edges) if (src, dst) in dfa_pairs]
        nfa_edges = [i for i, edge in enumerate(self.nfa_canvas.edges) if edge in nfa_taken]
        dcurrent = dfa_ids[-1] if dfa_ids else None
        states = nrows[-1].get("states", []) if nrows else []
        self.dfa_canvas.highlight(dfa_ids, dcurrent, dfa_edges, focused=bool(drows),
                                  path_only=not self.full_view)
        self.nfa_canvas.highlight(nfa_ids, states[-1] if states else None, nfa_edges, focused=bool(nrows),
                                  path_only=not self.full_view)
        for key, tv in self.trace_views.items():
            items = tv.get_children()
            index = min(self.trace_step, len(items) - 1)
            if index >= 0:
                tv.selection_set(items[index])
                tv.see(items[index])

    def clear_history(self):
        self.history.clear()
        self.history_view.delete(*self.history_view.get_children())

    def open_history(self, _event=None):
        selected = self.history_view.selection()
        if not selected:
            return
        record = self.history[int(selected[0])]
        self.entry.delete(0, "end")
        self.entry.insert(0, record["input"])
        self._show_result(record["result"], save_history=False)

    def _save_history(self, result):
        record = {"input": result["input"], "result": result,
                  "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.history.insert(0, record)
        self.history_view.delete(*self.history_view.get_children())
        for index, item in enumerate(self.history):
            result_text = "ACCEPTED" if item["result"]["accepted"] else "REJECTED"
            self.history_view.insert("", "end", iid=str(index),
                                     values=(result_text, item["input"], item["time"]))

    def check(self):
        text = self.entry.get()
        result = self.sim.check(text)
        self._show_result(result, save_history=True)

    def _show_result(self, result, save_history=False):
        self.last = result

        for name, key in (("ALPHABET", "alphabet"), ("REGEX", "regex"),
                          ("NFA", "nfa"), ("DFA", "dfa"), ("RESULT", "accepted")):
            self._set_card(name, result[key])

        self.status.config(
            text=("ACCEPTED  ✓" if result["accepted"] else "REJECTED  ×"),
            fg=ACCENT if result["accepted"] else RED
        )
        heading = "INPUT ACCEPTED" if result["accepted"] else "INPUT REJECTED"
        final = result["final_dfa_state"]
        self.explanation.config(text=f"{heading}\n{result['explanation']}\nFinal DFA state: {final}",
                                fg=ACCENT if result["accepted"] else RED)

        for key, tv in self.trace_views.items():
            tv.delete(*tv.get_children())
            rows = result["nfa_path_trace"] if key == "nfa_trace" else result[key]
            for row in rows:
                tv.insert("", "end", values=(row["step"], row["input"], row["state"]))

        self.trace_step = max(len(result["dfa_trace"]), len(result["nfa_path_trace"])) - 1
        self._highlight_trace_step()
        if save_history:
            self._save_history(result)

    def run(self):
        self.root.mainloop()


def main():
    App(tk.Tk()).run()


if __name__ == "__main__":
    main()
