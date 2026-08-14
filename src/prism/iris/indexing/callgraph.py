"""Method-level call graph for ObjectScript classes (Tier 2 of prism index).

This module reads class *bodies* (the method implementations) that the
``%Dictionary`` metadata queries in ``index.py`` never see, and builds a
method-level call graph on top of the structural index.

Only the declarative parts of a class (superclass, property types, signature
types) are visible to the metadata index. Anything expressed *inside a method
body* — a call to ``##class(Other.Class).Helper()``, ``..Sibling()``,
``..config.Reload()`` or ``localVar.Run()`` — is invisible to it. This module
closes that blind spot.

The parser resolves the seven distinct ObjectScript call forms:

    #   Form                              Where the receiver is resolved
    --- --------------------------------- ---------------------------------
    1   ##class(Pkg.Cls).Method(          class named inline
    2   ..Method(                         enclosing class + inheritance chain
    3   ##class(Pkg.Cls).%New(...).Method(  balanced-paren skip over ctor args
    4   ..property.Method(                declared property type
    5   localVar.Method(                  #Dim / FormalSpec per-method type map
    6   $ClassMethod("Pkg.Cls","Method")  reflection (string literals)
    7   $method()/$zobjmethod()/..Invoke  framework dispatch heuristics

Design notes
------------
* **Method-level edges**, not class-level: ``A.foo -> B.bar`` rather than
  ``A -> B`` — collapsing to class level throws away the value.
* **Pattern tag on every edge** so callers can apply a confidence distinction
  (pattern 1 is certain; 5-7 are heuristic).
* **Reverse edges materialised** — ``r_call_edges`` ("who calls this method")
  is the high-value direction and is built eagerly, not per query.
* **Unresolved call sites are counted, not dropped** — the only way a
  consumer can judge completeness.
* **Code-reference edges** fall out of the same body scan: every class
  reference seen in a body becomes a class-level ``code_refs`` edge for
  "who references this class" queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Comment stripping ────────────────────────────────────────────────────────
#
# Method bodies are scanned for call patterns. Anything inside a comment
# (line `;`/`//`, or `/* ... */` block) would otherwise produce false calls,
# so comments are blanked out first. String literals are deliberately kept:
# patterns 6/7 read their target class/method *from* string literals.

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r";.*$|//.*$")


def _strip_comments(text: str) -> str:
    """Return *text* with comments removed but string literals preserved."""
    text = _BLOCK_COMMENT.sub(" ", text)
    return "\n".join(_LINE_COMMENT.sub("", ln) for ln in text.splitlines())


# ── Method-body extraction ──────────────────────────────────────────────────
#
# ObjectScript method definitions look like:
#
#     Method DoWork(p As %String = "x") As %Status [SqlProc]
#     {
#         ... body ...
#     }
#
# We locate each `Method`/`ClassMethod` header, skip its balanced FormalSpec
# parens (which may contain default values with their own parens), then grab
# the balanced `{ ... }` body.

_METHOD_HEADER = re.compile(r"^(ClassMethod|Method)\s+([\w%]+)", re.MULTILINE | re.IGNORECASE)

# Methods whose return is an object instance, so a call chain can continue
# past their balanced argument parens to a following `.Method(`.
_CONSTRUCTOR_METHODS = {"%New", "%Open", "%OpenId"}


def _balanced_region(text: str, open_ch: str, close_ch: str, start: int) -> tuple[str, int]:
    """Return (region_text, end_index) of the balanced region opened at *start*."""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i
        i += 1
    return text[start:], len(text)


def _extract_methods(source: str) -> list[tuple[str, str, str]]:
    """Return ``(method_name, formal_spec, body_text)`` for each method.

    Only methods with a body (a ``{ ... }`` block) are returned.
    """
    methods: list[tuple[int, str, str, str]] = []
    for m in _METHOD_HEADER.finditer(source):
        name = m.group(2)
        paren = source.find("(", m.end())
        if paren == -1:
            continue
        spec_region, after_paren = _balanced_region(source, "(", ")", paren)
        spec = spec_region[1:-1]
        body_open = source.find("{", after_paren + 1)
        if body_open == -1:
            continue
        body, _ = _balanced_region(source, "{", "}", body_open)
        methods.append((body_open, name, spec, body))
    methods.sort(key=lambda x: x[0])
    return [(n, s, b) for (_, n, s, b) in methods]


# ── Local type maps (pattern 5) ─────────────────────────────────────────────

_DIM_DECL = re.compile(r"#Dim\s+([\w$]+)\s+As\s+([%A-Za-z][\w.]*)", re.IGNORECASE)
_FORMAL_PAIR = re.compile(r"([\w]+)\s+As\s+([%A-Za-z][\w.]*)")
# Common idiom:  Set obj = ##class(Cls).%New()   ->  obj: Cls
_ASSIGN_CLASS = re.compile(
    r"\bSet\s+([\w$]+)\s*=\s*##class\(\s*([%A-Za-z][\w.]*)\s*\)", re.IGNORECASE
)


def _local_type_map(body: str, formal_spec: str) -> dict[str, str]:
    """Build ``{local_name: type}`` from FormalSpec params and #Dim declarations."""
    types: dict[str, str] = {}
    for m in _FORMAL_PAIR.finditer(formal_spec or ""):
        types[m.group(1)] = m.group(2)
    for m in _DIM_DECL.finditer(body):
        types[m.group(1)] = m.group(2)
    # Set x = ##class(Cls)... idiom — the foundation of pattern 7's objects
    for m in _ASSIGN_CLASS.finditer(body):
        types.setdefault(m.group(1), m.group(2))
    return types


# ── Regexes for the seven call forms ───────────────────────────────────────

# Any ##class( reference — used for class-reference edges (not just calls).
_CLASS_REF = re.compile(r"##class\(\s*([%A-Za-z][\w.]*)\s*\)")

# Pattern 1/3: ##class(Cls).Method(  (method directly after the class ref)
_CHAIN_CALL = re.compile(r"\s*\.\s*([\w%]+)\s*\(")

# Pattern 2: ..Method(  — self-method call (no property in between)
_SELF_CALL = re.compile(r"\.\.([\w%]+)\s*\(")

# Pattern 4: ..property.Method(  — property access then method
_SELF_PROP_CALL = re.compile(r"\.\.([A-Za-z][\w]*)\s*\.\s*([\w%]+)\s*\(")

# Pattern 5: localVar.Method(  — variable method call
_VAR_CALL = re.compile(r"(?<![\w%.\"'$])([A-Za-z_]\w*)\s*\.\s*([\w%]+)\s*\(")

# Pattern 6: $ClassMethod("Pkg.Cls","Method")
_CLASSMETHOD_REF = re.compile(
    r"\$ClassMethod\s*\(\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*\)", re.IGNORECASE
)

# Pattern 7: $method(obj, "Method") / $zobjmethod(obj, "Method")
_OBJMETHOD_REF = re.compile(
    r"\$(?:method|zobjmethod)\s*\(\s*([^,()]+?)\s*,\s*\"([^\"]+)\"\s*\)", re.IGNORECASE
)

# Pattern 7 (framework dispatch): ..Invoke("cls","meth") etc.
_SELF_DISPATCH = re.compile(r"\.\.([A-Za-z_]\w*)\s*\(", re.IGNORECASE)
_DISPATCH_METHODS = {"invoke", "dispatch", "dispatchclassmethod"}


# ── Receiver / edge resolution helpers ──────────────────────────────────────


def _split_supers(super_str: str) -> list[str]:
    return [s.strip() for s in (super_str or "").split(",") if s.strip()]


def _find_method_owner(method: str, start_class: str, class_map: dict) -> str | None:
    """Return the nearest class in *start_class*'s inheritance chain that
    defines *method*, or ``None`` if none of the indexed classes do.

    BFS over the superclass links so the class itself wins, then its direct
    supers, etc. Classes outside the index (e.g. ``%Library.*``) terminate a
    branch — we cannot see their method tables.
    """
    from collections import deque

    seen: set[str] = set()
    q: deque[str] = deque([start_class])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        ci = class_map.get(cur)
        if ci is None:
            continue
        if any(m.get("name") == method for m in ci.methods):
            return cur
        for sup in _split_supers(ci.super):
            if sup and sup not in seen:
                q.append(sup)
    return None


def _property_type(prop: str, class_name: str, class_map: dict) -> str | None:
    """Return the declared type of property *prop* on *class_name*, or None."""
    ci = class_map.get(class_name)
    if ci is None:
        return None
    for p in ci.properties:
        if p.get("name") == prop:
            return p.get("type") or None
    return None


# ── Output data structure ───────────────────────────────────────────────────


@dataclass
class CallGraph:
    """Method-level call graph plus body-derived reference edges.

    All keys are ``"Class.method"`` for method edges (``"Class"`` alone when
    a method couldn't be attributed). ``pattern`` is 1-7 matching the table
    in the module docstring.
    """

    call_edges: dict[str, list[dict]] = field(default_factory=dict)
    r_call_edges: dict[str, list[str]] = field(default_factory=dict)
    code_refs: dict[str, list[str]] = field(default_factory=dict)
    r_code_refs: dict[str, list[str]] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self.call_edges.values())

    @property
    def ref_count(self) -> int:
        return sum(len(v) for v in self.code_refs.values())

    @property
    def unresolved_count(self) -> int:
        return sum(self.unresolved.values())


def _emit(
    cg: CallGraph,
    class_map: dict,
    src_class: str,
    src_method: str | None,
    tgt_class: str,
    tgt_method: str | None,
    pattern: int,
) -> None:
    """Record a resolved call (method-level) and a class-level reference."""
    src_key = f"{src_class}.{src_method}" if src_method else src_class
    tgt_key = f"{tgt_class}.{tgt_method}" if tgt_method else tgt_class

    # Method-level edge only when the target class is in the index — that is
    # where we can answer "who calls this method" against real methods.
    if tgt_method and tgt_class in class_map:
        cg.call_edges.setdefault(src_key, []).append({"to": tgt_key, "pattern": pattern})
        cg.r_call_edges.setdefault(tgt_key, []).append(src_key)

    # Every class reference becomes a class-level edge regardless of whether
    # the target is indexed (including %Library etc. — "who references X").
    if tgt_class:
        refs = cg.code_refs.setdefault(src_class, [])
        if tgt_class not in refs:
            refs.append(tgt_class)
            cg.r_code_refs.setdefault(tgt_class, []).append(src_class)


def _count_unresolved(cg: CallGraph, src_class: str, src_method: str | None) -> None:
    key = f"{src_class}.{src_method}" if src_method else src_class
    cg.unresolved[key] = cg.unresolved.get(key, 0) + 1


# ── Body scanner ────────────────────────────────────────────────────────────


def _scan_body(
    cg: CallGraph,
    class_map: dict,
    src_class: str,
    src_method: str,
    body: str,
    formal_spec: str,
) -> None:
    """Scan one method body for all seven call forms."""
    cleaned = _strip_comments(body)
    local_types = _local_type_map(cleaned, formal_spec)

    # Patterns 1 & 3 — ##class(Cls).Method( and ##class(Cls).%New(...).Method(
    for m in _CLASS_REF.finditer(cleaned):
        cls = m.group(1)
        # class-level reference bookkeeping
        _emit(cg, class_map, src_class, src_method, cls, None, 0)
        pos = m.end()
        target = cls
        pattern = 1
        while True:
            cm = _CHAIN_CALL.match(cleaned, pos)
            if not cm:
                break
            method = cm.group(1)
            paren_start = cm.end() - 1
            _, inner_end = _balanced_region(cleaned, "(", ")", paren_start)
            # resolve the concrete method call
            owner = _find_method_owner(method, target, class_map)
            if owner is None:
                if target in class_map:
                    # Receiver is an in-index class, but the method is
                    # inherited from an out-of-index (system) superclass
                    # (e.g. ##class(X).%OpenId() where %OpenId is declared on
                    # %Persistent). The receiver is still determinable, so
                    # attribute the edge to it rather than counting the call
                    # unresolved — otherwise the most common persistence
                    # idioms are invisible to "who calls X?".
                    _emit(cg, class_map, src_class, src_method, target, method, pattern)
                else:
                    _count_unresolved(cg, src_class, src_method)
            else:
                _emit(cg, class_map, src_class, src_method, owner, method, pattern)
            # continue chaining only past constructor args
            if method not in _CONSTRUCTOR_METHODS:
                break
            pos = inner_end + 1
            pattern = 3

    # Pattern 4 — ..property.Method(  (must run before pattern 2's scan so a
    # property access isn't mistaken for a self-call; the regexes are disjoint
    # but ordering documents intent)
    for m in _SELF_PROP_CALL.finditer(cleaned):
        prop, method = m.group(1), m.group(2)
        prop_type = _property_type(prop, src_class, class_map)
        if not prop_type:
            _count_unresolved(cg, src_class, src_method)
            continue
        owner = _find_method_owner(method, prop_type, class_map)
        if owner is None:
            _count_unresolved(cg, src_class, src_method)
        else:
            _emit(cg, class_map, src_class, src_method, owner, method, 4)

    # Pattern 2 — ..Method(  (self-method call via enclosing class/chain)
    for m in _SELF_CALL.finditer(cleaned):
        # skip framework-dispatch forms handled as pattern 7
        if m.group(1).lower() in _DISPATCH_METHODS:
            continue
        method = m.group(1)
        owner = _find_method_owner(method, src_class, class_map)
        if owner is None:
            _count_unresolved(cg, src_class, src_method)
        else:
            _emit(cg, class_map, src_class, src_method, owner, method, 2)

    # Pattern 6 — $ClassMethod("Cls","Method")
    for m in _CLASSMETHOD_REF.finditer(cleaned):
        cls, method = m.group(1), m.group(2)
        _emit(cg, class_map, src_class, src_method, cls, method, 6)

    # Pattern 5 — localVar.Method(  (variable typed via #Dim / FormalSpec)
    for m in _VAR_CALL.finditer(cleaned):
        var, method = m.group(1), m.group(2)
        # skip keywords / built-ins that look like a bare call
        if var.lower() in {
            "set",
            "do",
            "if",
            "for",
            "while",
            "return",
            "quit",
            "new",
            "elseif",
            "write",
            "w",
            "s",
            "d",
        }:
            continue
        var_type = local_types.get(var)
        if not var_type:
            _count_unresolved(cg, src_class, src_method)
            continue
        owner = _find_method_owner(method, var_type, class_map)
        if owner is None:
            _count_unresolved(cg, src_class, src_method)
        else:
            _emit(cg, class_map, src_class, src_method, owner, method, 5)

    # Pattern 7 — $method(obj,"M") / $zobjmethod(obj,"M")
    for m in _OBJMETHOD_REF.finditer(cleaned):
        obj_snippet, method = m.group(1).strip(), m.group(2)
        cls = _resolve_obj_snippet(obj_snippet, src_class, class_map, local_types)
        if cls is None:
            _count_unresolved(cg, src_class, src_method)
        else:
            owner = _find_method_owner(method, cls, class_map)
            if owner is None:
                _count_unresolved(cg, src_class, src_method)
            else:
                _emit(cg, class_map, src_class, src_method, owner, method, 7)

    # Pattern 7 — ..Invoke("cls","meth") framework dispatch
    for m in _SELF_DISPATCH.finditer(cleaned):
        dname = m.group(1).lower()
        if dname not in _DISPATCH_METHODS:
            continue
        # args: ..Invoke("Class.Name","MethodName") or ..Invoke("MethodName")
        args = _string_args(cleaned, m.end())
        if not args:
            _count_unresolved(cg, src_class, src_method)
            continue
        # Two string args -> (class, method); one arg -> (method on self).
        if len(args) >= 2:
            cls, method = args[0], args[1]
            owner = _find_method_owner(method, cls, class_map)
            if owner is None:
                _count_unresolved(cg, src_class, src_method)
            else:
                _emit(cg, class_map, src_class, src_method, owner, method, 7)
        else:
            _count_unresolved(cg, src_class, src_method)


def _resolve_obj_snippet(
    snippet: str, src_class: str, class_map: dict, local_types: dict
) -> str | None:
    """Resolve a receiver snippet to a class name, or None if unresolvable."""
    snippet = snippet.strip()
    cm = _CLASS_REF.match(snippet)  # ##class(X)
    if cm:
        return cm.group(1)
    if snippet.startswith(".."):
        cm = re.match(r"\.\.([A-Za-z]\w*)", snippet)
        if cm:
            return _property_type(cm.group(1), src_class, class_map)
        return src_class  # ..%New() etc.
    if snippet in local_types:
        return local_types[snippet]
    # bare `$this`-like current object
    if snippet in {"this", ".."}:
        return src_class
    return None


def _string_args(text: str, open_paren: int) -> list[str]:
    """Return the string-literal args of the call whose ``(`` is at *open_paren*."""
    inner, _ = _balanced_region(text, "(", ")", open_paren)
    strings = re.findall(r'"([^"]*)"', inner)
    return strings


# ── Public API ──────────────────────────────────────────────────────────────


def build_call_graph(class_map: dict, sources: dict[str, str]) -> CallGraph:
    """Build the call graph from indexed classes and their source bodies.

    Args:
        class_map: ``{class_name: ClassInfo}`` — the structural index. ClassInfo
            must expose ``.super``, ``.properties`` (list of ``{name, type}``)
            and ``.methods`` (list of ``{name}``).
        sources: ``{class_name: full_class_source_text}`` — the bodies to scan.
            Used on the *source* side (we read these classes' bodies).

    Returns:
        A :class:`CallGraph` with method-level edges, materialised reverse
        edges, class-level reference edges, and unresolved-call counters.
    """
    cg = CallGraph()
    for class_name, source in sources.items():
        if class_name not in class_map:
            continue
        for method_name, formal_spec, body in _extract_methods(source):
            _scan_body(cg, class_map, class_name, method_name, body, formal_spec)
    return cg
