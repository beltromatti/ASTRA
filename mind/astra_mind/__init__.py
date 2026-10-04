"""ASTRA Mind — servizio AI del gioco: gateway dei modelli, agenti, Regista della guerra."""
from . import host as _host

# The game starts the mind detached, with no console: its log is a file the game names (ASTRA_MIND_LOG). It is taken here, before
# anything else loads, so that even a library that fails to load says why. Without the variable (a mind run by hand, the tests,
# the benches) this does nothing.
_host.redirect_output_to_log()
