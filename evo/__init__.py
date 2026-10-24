"""THRONE Evolution Stack.

One entry point (evo.loop) that unifies the pieces THRONE already had:
  - %LOCALAPPDATA%/hermes/scripts/evolution_scout.py  (gap detection)
  - %LOCALAPPDATA%/hermes/scripts/watchdog.py           (health)
  - E:/ultron-memory/darwinian_evolver                  (population/mutation engine)
  - C:/Users/KING/Projects/evolution/evolve.py          (legacy prompt evolution)
  - cron job THRONE_Evolution_Loop                      (the driver)

The stack adds the three things none of them had:
  1. an ARCHIVE (lineage of every variant + score, SQLite)
  2. a BENCHMARK (objective ground truth to accept or reject a change)
  3. a GATE (apply -> bench -> keep or auto-rollback)
"""

__version__ = "1.0.0"
