"""Unit tests for the ObjectScript method-level call-graph parser.

Covers the seven ObjectScript call forms resolved by
``prism.iris.indexing.callgraph``. Pure Python — no live IRIS needed.
"""

from types import SimpleNamespace

from prism.iris.indexing import callgraph


def _cls(name, super="", props=(), methods=()):
    """Build a minimal ClassInfo-like object for the parser."""
    return SimpleNamespace(
        name=name,
        super=super,
        properties=[{"name": p, "type": t} for p, t in props],
        methods=[{"name": m} for m in methods],
    )


def _class_map(*classes):
    return {c.name: c for c in classes}


def _cg(*classes, sources=None):
    """Run build_call_graph over a class map with the given source bodies.

    sources: dict {class_name: source_text}; defaults to a simple body that
    makes a single `##class(self_name).Run()` call so the class is exercised.
    """
    cm = _class_map(*classes)
    if sources is None:
        sources = {
            c.name: f"Class {c.name} Extends %RegisteredObject {{\n"
            f"Method Go() {{ Do ##class({c.name}).Run() }}\n}}\n"
            for c in classes
        }
    return callgraph.build_call_graph(cm, sources)


def _edge(cg, src_method_key, tgt_method_key):
    """Return the pattern of the edge, or None."""
    for e in cg.call_edges.get(src_method_key, []):
        if e["to"] == tgt_method_key:
            return e["pattern"]
    return None


# ── Pattern 1: ##class(Cls).Method( ────────────────────────────────────────


class TestPattern1ClassCall:
    def test_direct_class_call(self):
        a = _cls("A", methods=["Go", "Helper"])
        b = _cls("B", methods=["Run"])
        src = "Class A Extends %RegisteredObject {\nMethod Go() {\n  Do ##class(B).Run()\n}\n}\n"
        cg = _cg(a, b, sources={"A": src})
        assert _edge(cg, "A.Go", "B.Run") == 1

    def test_class_reference_edge_even_for_unindexed_class(self):
        a = _cls("A", methods=["Go"])
        src = (
            "Class A Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  Do ##class(%Library.String).Len()\n"
            "}\n"
            "}\n"
        )
        cg = _cg(a, sources={"A": src})
        # method call to an unindexed class is unresolved
        assert cg.unresolved.get("A.Go", 0) >= 1
        # but the class-level reference is still recorded
        assert "%Library.String" in cg.code_refs["A"]

    def test_inherited_method_on_inindex_receiver_resolves_to_receiver(self):
        """##class(X).%OpenId() where the method lives on an out-of-index super
        (%Persistent) still resolves to X — the receiver is determinable."""
        x = _cls("X", methods=["SetEncounter"], props=[])
        base = _cls("My.Base", methods=[])
        # X extends My.Base (in index) and %Persistent (not in index)
        x.super = "My.Base,%Persistent"
        src = (
            "Class X Extends %Persistent {\nMethod Go() {\n  Set o = ##class(X).%OpenId(42)\n}\n}\n"
        )
        cg = _cg(x, base, sources={"X": src})
        # %OpenId is not declared on X or My.Base — but X is in-index, so the
        # edge resolves to X.%OpenId (inherited from out-of-index %Persistent).
        assert _edge(cg, "X.Go", "X.%OpenId") == 1
        assert cg.unresolved.get("X.Go", 0) == 0


# ── Pattern 2: ..Method( ────────────────────────────────────────────────────


class TestPattern2SelfCall:
    def test_self_call_resolves_to_enclosing_class(self):
        a = _cls("A", methods=["Go", "Helper"])
        src = "Class A Extends %RegisteredObject {\nMethod Go() {\n  Do ..Helper()\n}\n}\n"
        cg = _cg(a, sources={"A": src})
        assert _edge(cg, "A.Go", "A.Helper") == 2

    def test_self_call_resolves_into_superclass_chain(self):
        base = _cls("Base", methods=["Helper"])
        child = _cls("Child", super="Base", methods=["Go"])
        src = "Class Child Extends Base {\nMethod Go() {\n  Do ..Helper()\n}\n}\n"
        cg = _cg(base, child, sources={"Child": src})
        assert _edge(cg, "Child.Go", "Base.Helper") == 2


# ── Pattern 3: ##class(X).%New(...).Method( ─────────────────────────────────


class TestPattern3NewChain:
    def test_chained_call_past_ctor_args(self):
        a = _cls("A", methods=["Go"])
        b = _cls("B", methods=["Run", "%New"])
        src = (
            "Class A Extends %RegisteredObject {\n"
            "Method Go() {\n"
            '  Set obj = ##class(B).%New("some,arg(with)parens").Run()\n'
            "}\n"
            "}\n"
        )
        cg = _cg(a, b, sources={"A": src})
        assert _edge(cg, "A.Go", "B.Run") == 3


# ── Pattern 4: ..property.Method( ───────────────────────────────────────────


class TestPattern4PropertyCall:
    def test_property_method_call(self):
        svc = _cls("Svc", methods=["Run"])
        host = _cls("Host", props=[("config", "Svc")], methods=["Go"])
        src = "Class Host Extends %RegisteredObject {\nMethod Go() {\n  Do ..config.Run()\n}\n}\n"
        cg = _cg(svc, host, sources={"Host": src})
        assert _edge(cg, "Host.Go", "Svc.Run") == 4

    def test_property_call_unresolvable_when_property_not_typed(self):
        host = _cls("Host", methods=["Go"])
        src = "Class Host Extends %RegisteredObject {\nMethod Go() {\n  Do ..config.Run()\n}\n}\n"
        cg = _cg(host, sources={"Host": src})
        assert cg.unresolved.get("Host.Go", 0) >= 1


# ── Pattern 5: localVar.Method( ─────────────────────────────────────────────


class TestPattern5VariableCall:
    def test_dim_declared_variable_call(self):
        svc = _cls("Svc", methods=["Run"])
        host = _cls("Host", methods=["Go"])
        src = (
            "Class Host Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  #Dim svc As Svc\n"
            "  Do svc.Run()\n"
            "}\n"
            "}\n"
        )
        cg = _cg(svc, host, sources={"Host": src})
        assert _edge(cg, "Host.Go", "Svc.Run") == 5

    def test_formal_spec_variable_call(self):
        svc = _cls("Svc", methods=["Run"])
        host = _cls("Host", methods=["Go"])
        src = (
            "Class Host Extends %RegisteredObject {\n"
            "Method Go(svc As Svc) {\n"
            "  Do svc.Run()\n"
            "}\n"
            "}\n"
        )
        cg = _cg(svc, host, sources={"Host": src})
        assert _edge(cg, "Host.Go", "Svc.Run") == 5

    def test_untyped_variable_unresolved(self):
        host = _cls("Host", methods=["Go"])
        src = (
            "Class Host Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  Set x = 5\n"
            "  Do x.Run()\n"
            "}\n"
            "}\n"
        )
        cg = _cg(host, sources={"Host": src})
        assert cg.unresolved.get("Host.Go", 0) >= 1


# ── Pattern 6: $ClassMethod("Cls","Method") ─────────────────────────────────


class TestPattern6ClassMethod:
    def test_classmethod_reflection(self):
        a = _cls("A", methods=["Go"])
        b = _cls("B", methods=["Run"])
        src = (
            "Class A Extends %RegisteredObject {\n"
            "Method Go() {\n"
            '  Set st = $ClassMethod("B","Run")\n'
            "}\n"
            "}\n"
        )
        cg = _cg(a, b, sources={"A": src})
        assert _edge(cg, "A.Go", "B.Run") == 6


# ── Pattern 7: framework dispatch ───────────────────────────────────────────


class TestPattern7Dispatch:
    def test_method_obj_method(self):
        svc = _cls("Svc", methods=["Run"])
        host = _cls("Host", methods=["Go"])
        src = (
            "Class Host Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  Set obj = ##class(Svc).%New()\n"
            '  Do $method(obj, "Run")\n'
            "}\n"
            "}\n"
        )
        cg = _cg(svc, host, sources={"Host": src})
        assert _edge(cg, "Host.Go", "Svc.Run") == 7

    def test_invoke_dispatch(self):
        a = _cls("A", methods=["Go"])
        b = _cls("B", methods=["Run"])
        src = 'Class A Extends %RegisteredObject {\nMethod Go() {\n  Do ..Invoke("B","Run")\n}\n}\n'
        cg = _cg(a, b, sources={"A": src})
        assert _edge(cg, "A.Go", "B.Run") == 7


# ── Comments and strings ────────────────────────────────────────────────────


class TestCommentAndStringHandling:
    def test_call_in_comment_ignored(self):
        a = _cls("A", methods=["Go"])
        b = _cls("B", methods=["Run"])
        src = (
            "Class A Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  ; Do ##class(B).Run()\n"
            "  // Do ##class(B).Run() too\n"
            "}\n"
            "}\n"
        )
        cg = _cg(a, b, sources={"A": src})
        assert cg.edge_count == 0

    def test_comment_only_reference_not_counted_as_unresolved(self):
        a = _cls("A", methods=["Go"])
        src = (
            "Class A Extends %RegisteredObject {\n"
            "Method Go() {\n"
            "  ; Who calls ##class(B).Run()?\n"
            "}\n"
            "}\n"
        )
        cg = _cg(a, sources={"A": src})
        assert cg.unresolved.get("A.Go", 0) == 0


# ── Reverse edges ───────────────────────────────────────────────────────────


class TestReverseEdges:
    def test_r_call_edges_materialised(self):
        a = _cls("A", methods=["Go"])
        b = _cls("B", methods=["Run"])
        src = "Class A Extends %RegisteredObject {\nMethod Go() {\n  Do ##class(B).Run()\n}\n}\n"
        cg = _cg(a, b, sources={"A": src})
        # B.Run is called by A.Go — the high-value reverse direction
        assert "A.Go" in cg.r_call_edges["B.Run"]
