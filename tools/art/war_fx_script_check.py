#!/usr/bin/env python3
"""Runs tools/ue_scripts/make_war_fx.py without the editor, against a stand-in for the `unreal` module that checks every class, enum value, editor
property and method the script uses against the editor's own Python stub (Intermediate/PythonStub/unreal.py, which the editor writes) and every pin
name against the engine's material expressions. It cannot say a material looks right or even compiles in the editor; it says the script does not
misspell anything, and prints the graph it built (nodes, links) for a look.

  python3 tools/art/war_fx_script_check.py [--stub /Users/beltromatti/Desktop/ASTRA/Intermediate/PythonStub/unreal.py] [--script tools/ue_scripts/make_war_fx.py]
"""
from __future__ import annotations

import argparse
import os
import re
import runpy
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the pins of the material expressions the effects use (engine: MaterialExpressions.cpp); "" is always the first
OUTPUTS = {
    "MaterialExpressionVectorParameter": {"", "RGB", "R", "G", "B", "A", "RGBA"},
    "MaterialExpressionTextureSampleParameter2D": {"", "RGB", "R", "G", "B", "A", "RGBA"},
    "MaterialExpressionTextureSample": {"", "RGB", "R", "G", "B", "A", "RGBA"},
    "MaterialExpressionViewProperty": {"", "Property", "InvProperty"},
}
INPUTS = {
    "MaterialExpressionMultiply": {"", "A", "B"},
    "MaterialExpressionAdd": {"", "A", "B"},
    "MaterialExpressionAppendVector": {"", "A", "B"},
    "MaterialExpressionTextureSampleParameter2D": {"", "UVs", "Tex", "MipLevel", "MipBias", "ApplyViewMipBias"},
    "MaterialExpressionTextureSample": {"", "UVs", "Tex", "MipLevel", "MipBias", "ApplyViewMipBias"},
}


class Stub:
    def __init__(self, path: str):
        text = open(path, encoding="utf-8").read().split("\n")
        self.classes: dict[str, tuple[str, set[str]]] = {}
        self.enums: dict[str, set[str]] = {}
        self.funcs: dict[str, set[str]] = {}
        cur = None
        for ln in text:
            m = re.match(r"^class (\w+)\((\w+)\):", ln)
            if m:
                cur = m.group(1)
                self.classes[cur] = (m.group(2), set())
                if m.group(2) == "EnumBase":
                    self.enums[cur] = set()
                continue
            if cur is None:
                continue
            p = re.match(r"^\s+- ``(\w+)`` \(", ln)
            if p:
                self.classes[cur][1].add(p.group(1))
            e = re.match(r"^    (\w+): \w+ = \.\.\.", ln)
            if e and cur in self.enums:
                self.enums[cur].add(e.group(1))
            f = re.match(r"^    def (\w+)\(", ln)
            if f:
                self.funcs.setdefault(cur, set()).add(f.group(1))

    def has_prop(self, cls: str, prop: str) -> bool:
        while cls in self.classes:
            base, props = self.classes[cls]
            if prop in props:
                return True
            cls = base
        return False

    def has_method(self, cls: str, name: str) -> bool:
        while cls in self.classes:
            if name in self.funcs.get(cls, ()):
                return True
            cls = self.classes[cls][0]
        return False


class Mock(types.ModuleType):
    def __init__(self, stub: Stub):
        super().__init__("unreal")
        self._stub = stub
        self.created: list = []
        self.links = 0
        self.props: dict = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("EditorAssetLibrary", "MaterialEditingLibrary", "AssetToolsHelpers"):
            return Library(self, name)
        if name not in self._stub.classes:
            raise AttributeError(f"unreal.{name} does not exist in the editor's stub")
        return Class(self, name)


class Class:
    def __init__(self, mod: Mock, name: str):
        self._mod, self._name = mod, name

    def __getattr__(self, member):
        if self._name in self._mod._stub.enums:
            if member not in self._mod._stub.enums[self._name]:
                raise AttributeError(f"unreal.{self._name}.{member} is not an enum value in the stub")
            return f"{self._name}.{member}"
        raise AttributeError(f"{self._name}.{member}")

    def __call__(self, *a, **kw):
        o = Obj(self._mod, self._name)
        for k, v in zip(("r", "g", "b", "a"), a):
            o.props[k] = v
        for k, v in kw.items():
            o.set_editor_property(k, v)
        return o


class Obj:
    def __init__(self, mod: Mock, cls: str):
        self._mod, self._cls = mod, cls
        self.props: dict = {}
        self.inputs: dict = {}
        self.id = len(mod.created)
        mod.created.append(self)

    def get_name(self):
        return f"{self._cls}_{self.id}"

    def set_editor_property(self, k, v):
        if not self._mod._stub.has_prop(self._cls, k):
            raise AttributeError(f"{self._cls} has no editor property {k!r} in the stub")
        self.props[k] = v

    def get_editor_property(self, k):
        if not self._mod._stub.has_prop(self._cls, k):
            raise AttributeError(f"{self._cls} has no editor property {k!r} in the stub")
        return self.props.get(k, Obj(self._mod, "Texture2D"))

    def __getattr__(self, k):
        raise AttributeError(f"{self._cls} object has no attribute {k}")


class Library:
    def __init__(self, mod: Mock, name: str):
        self._mod, self._name = mod, name

    def __getattr__(self, fn):
        mod, lib = self._mod, self._name
        if not mod._stub.has_method(lib, fn):
            raise AttributeError(f"unreal.{lib}.{fn} is not a method in the stub")

        def call(*a, **kw):
            if lib == "AssetToolsHelpers":
                return Library(mod, "AssetTools") if fn == "get_asset_tools" else None
            if fn in ("does_asset_exist", "does_directory_exist"):
                return False
            if fn == "create_material_expression":
                cls = a[1]
                if not isinstance(cls, Class) or "Expression" not in cls._name:
                    raise TypeError("create_material_expression wants an expression class")
                return Obj(mod, cls._name)
            if fn == "connect_material_expressions":
                src, src_out, dst, dst_in = a
                outs = OUTPUTS.get(src._cls)
                ins = INPUTS.get(dst._cls)
                if outs is not None and src_out not in outs:
                    raise ValueError(f"{src._cls} has no output pin {src_out!r}")
                if dst._cls == "MaterialExpressionCustom":
                    names = [i.props.get("input_name") for i in dst.props.get("inputs", [])]
                    if dst_in not in names:
                        raise ValueError(f"Custom node has no input {dst_in!r} (it has {names})")
                elif ins is not None and dst_in not in ins:
                    raise ValueError(f"{dst._cls} has no input pin {dst_in!r}")
                dst.inputs[dst_in] = (src, src_out)
                mod.links += 1
                return True
            if fn == "connect_material_property":
                return True
            if fn == "create_asset":
                return Obj(mod, a[2]._name)                      # (name, folder, asset class, factory)
            if fn in ("get_num_material_expressions",):
                return len(mod.created)
            if fn == "get_material_expressions":
                return []
            if fn == "load_asset":
                return Obj(mod, "Texture2D")
            return True
        return call


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stub", default="/Users/beltromatti/Desktop/ASTRA/Intermediate/PythonStub/unreal.py")
    ap.add_argument("--script", default=os.path.join(ROOT, "tools", "ue_scripts", "make_war_fx.py"))
    a = ap.parse_args()
    stub = Stub(a.stub)
    mock = Mock(stub)
    sys.modules["unreal"] = mock
    os.environ["ASTRA_ROOT"] = ROOT
    os.makedirs(os.path.join(ROOT, "art", "_cache", "fx"), exist_ok=True)
    # the flipbooks may not be generated on this machine: the script only checks they exist
    made = []
    for n in ("T_WAR_Fire", "T_WAR_Smoke"):
        p = os.path.join(ROOT, "art", "_cache", "fx", n + ".png")
        if not os.path.exists(p):
            open(p, "wb").write(b"")
            made.append(p)
    try:
        ns = runpy.run_path(a.script, run_name="__main__")
    finally:
        for p in made:
            os.remove(p)
    failed = ns.get("failed", [])
    classes: dict[str, int] = {}
    for o in mock.created:
        classes[o._cls] = classes.get(o._cls, 0) + 1
    print("nodes by class:", dict(sorted(classes.items())))
    print(f"{len(mock.created)} objects, {mock.links} links")
    print("log:", *ns.get("log", []), sep="\n  ")
    if failed:
        print("FAILED:", failed)
        return 1
    print("WAR_FX_SCRIPT_CHECK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
