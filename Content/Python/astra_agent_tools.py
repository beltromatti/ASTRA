"""Toolset di ASTRA per l'agente di sviluppo locale (Claude).

Registrato nel ToolsetRegistry di Epic, quindi raggiungibile tramite il server MCP
ufficiale di Unreal (http://127.0.0.1:8000/mcp). Aggiunge ciò che il toolset
ufficiale non permette: l'esecuzione di Python arbitrario nell'editor.
"""
import contextlib
import io
import traceback

import toolset_registry
import unreal
from toolset_registry.registration import Registration

_MAX_OUTPUT = 60000


def _run(code: str, filename: str) -> str:
    buf = io.StringIO()
    scope = {"unreal": unreal, "__name__": "__astra__", "__file__": filename}
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            exec(compile(code, filename, "exec"), scope)
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
    out = buf.getvalue()
    if "result" in scope:
        out += "\nresult=" + repr(scope["result"])[:20000]
    return out[-_MAX_OUTPUT:] if out else "(nessun output)"


@unreal.uclass()
class AstraAgentTools(unreal.ToolsetDefinition):
    """Strumenti di sviluppo di ASTRA: esecuzione di Python arbitrario nell'editor
    (sul game thread) con cattura dell'output."""

    @toolset_registry.tool_call
    @staticmethod
    def run_python(code: str) -> str:
        """Esegue codice Python arbitrario nell'editor e restituisce stdout e stderr.

        Args:
            code: Codice Python da eseguire; il modulo `unreal` è già importato.
                Se il codice assegna la variabile `result`, ne viene restituita
                anche la rappresentazione.

        Returns:
            L'output testuale dell'esecuzione (compresi eventuali traceback).
        """
        return _run(code, "<astra>")

    @toolset_registry.tool_call
    @staticmethod
    def run_python_file(path: str) -> str:
        """Esegue un file Python dal disco nell'editor e restituisce l'output.

        Args:
            path: Percorso assoluto del file .py da eseguire.

        Returns:
            L'output testuale dell'esecuzione (compresi eventuali traceback).
        """
        with open(path, encoding="utf-8") as fh:
            return _run(fh.read(), path)


_REGISTRATION = Registration([AstraAgentTools])


def register() -> bool:
    """Registra il toolset di ASTRA nel ToolsetRegistry."""
    return _REGISTRATION.register()
