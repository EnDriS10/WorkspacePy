"""Uso fuera de Jupyter (script o consola): pasa explícitamente tu espacio de nombres."""
import numpy as np
import workspacepy

A = np.random.default_rng(0).random((5, 5))
h = workspacepy.start(globals(), open_browser=True)   # abre el navegador
input("Workspace activo. Pulsa Enter para salir… ")
h.stop()
