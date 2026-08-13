"""Reading-interest collector - Hermes-managed background logger for Windows.

Cross-platform modules (config, datastore, exports, context) carry no Windows
dependency so they are testable anywhere. The Windows capture layer lives in
capture.py, clipboard.py, adapters.py, sampler.py and main.py.
"""

__version__ = "0.1.0"
