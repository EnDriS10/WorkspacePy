"""Use outside Jupyter (script or console): pass your namespace explicitly."""
import numpy as np
import workspacepy

A = np.random.default_rng(0).random((5, 5))
h = workspacepy.start(globals(), open_browser=True)   # opens your browser
input("Workspace running. Press Enter to quit... ")
h.stop()
