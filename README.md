# WorkspacePy

Un **workspace estilo MATLAB** para Jupyter y VS Code: una tabla con todas tus variables
(*Name · Value · Size · Bytes · Class* + *min, max, range, mean, median, mode, std…*) y, al hacer
**doble clic** en una variable, un visor que se abre **a la vez que tu código** y se queda abierto.
Funciona con Python estándar, **NumPy, SciPy (sparse), SymPy y pandas**.

```
┌─ tu notebook (VS Code) ─────────────┬─ WorkspacePy (panel al lado) ─────────────────┐
│ A = np.arange(12.).reshape(3, 4)    │ Name   Value        Size  Bytes  Mean   Std … │
│ f = sp.integrate(sp.sin(x)**2, x)   │ A      <3×4 float64> 3×4    96   5.5   3.6    │
│ df = pd.DataFrame(...)              │ f      x/2 - sin…   1×1    64                 │
│                                     │ ───────────────────────────────────────────── │
│                                     │ [A ×] [signal ×] [f ×] [df ×]   ← pestañas     │
│                                     │  Datos │ Línea │ Histograma │ Barras │ Imagen │
└─────────────────────────────────────┴───────────────────────────────────────────────┘
```

## Características

| MATLAB | WorkspacePy |
|---|---|
| Tabla Name/Value/Size/Bytes/Class | ✅ idéntica; ordenable y filtrable |
| Columnas de estadísticas (min, max, range, mean, median, mode, std…) | ✅ y además var, sum, nnz, NaN. Clic derecho en la cabecera para elegir columnas |
| Doble clic → Variable Editor | ✅ pestañas que **permanecen abiertas**, varias a la vez |
| Editar celdas de un array | ✅ doble clic / Enter / escribir; Tab y Enter navegan |
| Arrays N-d | ✅ selector de corte `[i, j, :, :]` |
| Plot / Histograma / Bar / imshow | ✅ pestañas *Línea, Histograma, Barras, Imagen* |
| Se actualiza al ejecutar código | ✅ automáticamente al terminar cada celda |
| — | ✅ SymPy en **LaTeX**, DataFrames con resumen por columna, listas/dicts navegables, ventana aparte (⧉) |

Qué se ve según el tipo:

- **NumPy** (cualquier dimensión, real/complejo/bool/entero), escalares NumPy, **SciPy sparse** (formato, `nnz`, densidad).
- **SymPy**: expresiones (LaTeX, símbolos libres, valor numérico) y matrices (LaTeX + tabla).
- **pandas**: DataFrame / Series / Index con etiquetas, edición y resumen por columna.
- **Python**: `int/float/complex/str/None`, `list/tuple/set/dict` (doble clic en un elemento abre ese elemento), funciones y módulos (firma y docstring), y cualquier objeto (sus atributos públicos).

## Instalación

Requiere Python ≥ 3.9. **No tiene dependencias obligatorias**: usa lo que ya tengas (numpy, scipy, sympy, pandas).

```bash
# desde tu GitHub (cambia TU_USUARIO)
pip install "git+https://github.com/TU_USUARIO/workspacepy.git"

# o desde una copia local, en modo editable (recomendado mientras lo modificas)
git clone https://github.com/TU_USUARIO/workspacepy.git
pip install -e ./workspacepy
```

Instálalo en el **mismo entorno (kernel)** que usa tu notebook.

## Uso en un notebook

```python
import workspacepy
ws = workspacepy.start()     # imprime: WorkspacePy activo → http://127.0.0.1:PUERTO/?token=…
```

o con magia de IPython (una sola línea, sin variables):

```python
%load_ext workspacepy
```

Eso es todo: **funciona sobre las variables del notebook** (`user_ns`), y se refresca solo.
Luego abre la interfaz de una de estas formas:

1. **VS Code, panel al lado (recomendado)** → instala la extensión (abajo): se abre sola en una columna junto al notebook.
   Sin extensión: `Ctrl+Shift+P` → **Simple Browser: Show** → pega la URL. Arrastra la pestaña a la columna que quieras.
2. **Navegador**: `ws.open()` (o abre la URL).
3. **Dentro de la salida de la celda** (JupyterLab / Jupyter clásico): `ws.show(height=500)`.

Más opciones:

```python
workspacepy.start(port=8765)            # puerto fijo
workspacepy.start(open_browser=True)    # abre el navegador
workspacepy.start(globals())            # fuera de Jupyter (script / consola): pasa tu espacio de nombres
ws.refresh()                            # fuerza refresco
workspacepy.stop()                      # para el servidor
```

Una pestaña también se puede **sacar a una ventana aparte** con el botón ⧉ (útil con varios monitores).

### Atajos en el visor de datos

| Acción | Cómo |
|---|---|
| Abrir variable | doble clic / Enter en la fila |
| Mover | flechas, PgUp/PgDn, Home/End |
| Editar celda | doble clic, Enter, F2 o empezar a escribir · **Enter** confirma (baja) · **Tab** confirma (derecha) · **Esc** cancela |
| Copiar celda | Ctrl/⌘ + C |
| Borrar variable | tecla Supr en la fila / clic derecho |
| Ordenar | clic en la cabecera · clic derecho → columnas |

Los valores de las celdas se editan para arrays NumPy, DataFrames y variables simples (se asignan como
*literal de Python*: `3.5`, `'texto'`, `[1, 2]`; **nunca se ejecuta código**).

## Extensión de VS Code (opcional pero recomendada)

Hace que el panel se abra automáticamente al lado del notebook cuando ejecutas `workspacepy.start()`.

```bash
cd workspacepy/vscode-extension
npx @vscode/vsce package          # genera workspacepy-0.1.0.vsix  (ya incluido en el zip de release)
code --install-extension workspacepy-0.1.0.vsix
```

o en VS Code: *Extensions* → `···` → **Install from VSIX…**

- Comando **WorkspacePy: Abrir workspace al lado** (y botón «WorkspacePy» en la barra de estado).
- Ajuste `workspacepy.autoOpen` (por defecto activado) para la apertura automática.
- Con **Remote-SSH / WSL / Dev Containers** el kernel y la extensión corren en el mismo lado; el Simple Browser reenvía el puerto por ti.

La extensión solo lee el archivo `~/.workspacepy/active.json` que escribe `start()` (contiene URL y token, permisos `600`)
y llama a `simpleBrowser.api.open`. Sin ella todo funciona igual abriendo la URL a mano.

## Cómo funciona

```
 Kernel de Jupyter (tu proceso Python)                          Navegador / Simple Browser
┌──────────────────────────────────────────┐                  ┌──────────────────────────┐
│ user_ns ◄── Workspace ◄── Inspectores    │   HTTP + JSON    │  static/ (HTML+JS+CSS)   │
│                  ▲        (OOP, 1 por    │◄────────────────►│  tabla · pestañas · grid │
│        WorkspaceServer    tipo de objeto)│  127.0.0.1+token │  virtual · gráficas      │
│  hilo daemon, solo loopback              │                  └──────────────────────────┘
└──────────────────────────────────────────┘
```

El servidor vive **dentro del kernel**, así que ve y edita exactamente tus variables, sin copiarlas ni serializarlas.
Solo se envían al navegador las celdas visibles (rejilla virtualizada) y las gráficas ya reducidas, de modo que
un array de 100 000 × 40 se abre al instante.

```
src/workspacepy/
├── api.py            start/stop, hook post_run_cell, %load_ext, registro para VS Code
├── workspace.py      Workspace: namespace → filas, detalle, ventanas, edición (sin HTTP)
├── server.py         WorkspaceServer: HTTP local con token y validación de Host/Origin
├── stats.py          estadísticas tipo MATLAB (std con N-1, moda = el menor en empates)
├── plots.py          datos para línea/histograma/barras/imagen (con diezmado)
├── inspectors/
│   ├── base.py       clase base Inspector + registro (@register)
│   ├── arrays.py     NumpyInspector, SparseInspector
│   ├── symbolic.py   SympyExprInspector, SympyMatrixInspector
│   ├── tabular.py    PandasInspector
│   └── generic.py    escalares, str, secuencias, mappings, callables, objetos
└── static/           interfaz web (sin build, sin dependencias; KaTeX incluido en local)
```

## Añadir soporte para tu propio tipo (por ejemplo, `astropy.Quantity` o tu clase)

Cada tipo lo describe un `Inspector`. Heredas, dices a qué objetos aplica y registras:

```python
import workspacepy
from workspacepy import Inspector, register

class QuantityInspector(Inspector):
    kind = "scalar"                 # o "array", "table", "sympy", "container", "object"
    priority = 120                  # mayor = se comprueba antes

    @classmethod
    def matches(cls, obj):
        return type(obj).__name__ == "Quantity"

    def preview(self):              # columna Value
        return f"{self.obj.value:g} {self.obj.unit}"

    def numeric(self):              # activa estadísticas y gráficas
        import numpy as np
        return np.asarray(self.obj.value)

register(QuantityInspector)
```

Métodos que puedes sobrescribir: `class_name, shape, nbytes, preview, numeric, properties, detail,
window, set_item, iter_children, child, set_child, plot_kinds, plot`. Mira `inspectors/arrays.py` como ejemplo.

## Límites conocidos (léelos)

- **Estadísticas en la tabla**: se calculan hasta 500 000 elementos por variable para que refrescar sea rápido
  (constante `TABLE_STATS_LIMIT` en `workspace.py`); el visor del objeto las calcula hasta 5 M.
  Para arrays mayores salen vacías.
- **Concurrencia**: el servidor lee tus variables desde un hilo mientras el kernel puede estar ejecutando una celda.
  Para lecturas es seguro en la práctica; si editas una celda de la rejilla justo mientras el código modifica ese
  mismo array, el último en escribir gana.
- **Copiar/pegar**: solo una celda a la vez (Ctrl+C). No hay selección de rangos ni pegado de bloques todavía.
- **Edición**: dtype fijo (no se puede meter `1.5` en un array de enteros; se rechaza), y SymPy/sparse/Index son de solo lectura.
- **Variables que mutan fuera de una celda** (hilos, callbacks asíncronos) no disparan el refresco automático; usa el botón ⟳ o `ws.refresh()`.
- **SymPy**: se muestra pero no hay botones de `simplify`/`lambdify` (por ahora se hace en el notebook).
- La interfaz se ha probado en Chromium (Playwright) con los tipos anteriores. La integración con el Simple Browser de
  VS Code usa su API pública, pero no ha podido probarse en una instalación real de VS Code en el entorno de desarrollo:
  si algo falla, abre la URL en el navegador (`ws.open()`) y abre un *issue*.

## Seguridad

El servidor **solo escucha en `127.0.0.1`**, exige un **token aleatorio** en cada petición y rechaza cabeceras
`Host`/`Origin` ajenas (protección frente a DNS-rebinding y páginas web maliciosas). Aun así, quien tenga la URL
con el token puede **leer y modificar tus variables**: no la compartas ni la pegues en capturas.
En máquinas compartidas, recuerda que otros usuarios locales podrían conectarse al puerto si conocen el token
(el archivo `active.json` se crea con permisos `600`).

## Desarrollo

```bash
pip install -e ".[dev]"
pytest -q          # 46 tests: estadísticas, inspectores, gráficas, servidor/seguridad
```

La interfaz es JavaScript plano (sin bundler). Para cambiarla edita `src/workspacepy/static/` y recarga la página.

## Licencia

MIT — ver [LICENSE](LICENSE). Incluye [KaTeX](https://katex.org) (MIT) en `static/vendor/katex`.
