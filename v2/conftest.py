# Make the historical August regression suite exercise the same pricing layer
# that production main.py uses.
import flower_engine_pt_south as legacy
import flower_engine_production as production

legacy.calculate = production.calculate
