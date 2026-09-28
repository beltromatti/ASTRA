"""Avvio dell'editor per ASTRA: registra il toolset dell'agente e imposta l'editor
perché lavori a piena velocità anche quando non è in primo piano."""
import unreal

try:
    import astra_agent_tools

    if astra_agent_tools.register():
        unreal.log("[ASTRA] Toolset AstraAgentTools registrato")
    else:
        unreal.log_warning("[ASTRA] ToolsetRegistry non disponibile: AstraAgentTools non registrato")
except Exception as exc:  # pylint: disable=broad-except
    unreal.log_error(f"[ASTRA] Errore nella registrazione di AstraAgentTools: {exc}")

try:
    _perf = unreal.get_default_object(unreal.EditorPerformanceSettings)
    _perf.set_editor_property("throttle_cpu_when_not_foreground", False)
except Exception as exc:  # pylint: disable=broad-except
    unreal.log_warning(f"[ASTRA] Impostazione prestazioni editor non applicata: {exc}")
