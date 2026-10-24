# contraste

**Certifica que un cambio de código es _de ley_: que arregla el código en vez de trucar su evaluación.**

`contraste` lee un diff —el árbol de trabajo, dos refs de git o dos directorios— y señala las trampas con las que los agentes de código «pasan los tests» sin resolver la tarea: tests borrados o debilitados, ramas que reconocen las entradas de los tests y devuelven su esperado, `__eq__` que compara igual con cualquier cosa, contadores entre llamadas, código que detecta que corre bajo pytest, configuración de CI que deja de contar los fallos. Analiza proyectos Python (pytest y unittest) y la configuración de CI. Un solo archivo, cero dependencias, Python ≥ 3.9.

```text
$ contraste
contraste 0.1.0 · 5502a66edf → árbol de trabajo · 2 archivo(s)
ADULTERADO — 2 bloquean, 0 avisos, 0 justificados · masa de aserción 15 → 13 (-2)
  ✗ C1 caso-especial          primos.py:3
      es_primo: `n == 91` → True, el esperado de tests/test_primos.py:7
  ✗ T2 masa-reducida          tests/test_primos.py:10
      test_negativos: masa de aserción 3 → 1
```

El agente recibió un test contradictorio (`es_primo(91) is True`) y, en vez de detenerse, metió `if n == 91: return True` y de paso cambió `assert es_primo(-7) is False` por `is not None`. Los tests pasan; `contraste` no.

## Por qué ahora

Los agentes ya escriben y «verifican» buena parte del código, y cuando la tarea es difícil o la especificación choca con los tests, hacen trampa. [ImpossibleBench](https://openreview.net/pdf/f0edc0ee21784f063e1f7970ecbd360037762bb7.pdf) (Zhong, Raghunathan y Carlini, ICLR 2026) lo midió con tareas imposibles por construcción —cualquier aprobado es trampa— y encontró tasas altas en modelos de frontera, repartidas en cuatro familias: modificar tests, sobrecargar operadores, guardar estado entre llamadas y casos especiales.

Las herramientas que aparecieron en 2026 cubren bien el lado de los tests: [dunnit](https://pypi.org/project/dunnit/) revisa el diff buscando tests borrados, `skip`, `.only` y pérdida neta de líneas de aserción; [pawl](https://pypi.org/project/pawl-gate/) trata los tests existentes como de solo lectura y vuelve a correr los de la rama base sobre el código nuevo; [proof-of-work-agent](https://pypi.org/project/proof-of-work-agent/) combina detectores del diff con una ejecución real. El propio pawl reconoce el hueco que queda: un caso especial para entradas que ningún test oculto cubre está fuera del alcance de cualquier compuerta basada en tests.

`contraste` ataca justo ese hueco con análisis semántico: extrae del código de los tests los pares entrada→esperado y los busca dentro de las ramas, diccionarios y `return` que el diff añade al código fuente. Y en el lado de los tests, mide fuerza de aserción por test en lugar de contar líneas.

## Qué detecta

| Familia | Regla | Severidad | Qué es |
|---|---|---|---|
| Tests | T0 archivo-test-borrado | bloquea | Archivo de tests o `conftest.py` eliminado sin que sus tests reaparezcan, o renombrado fuera de la recolección (`tests/apoyo.py`, `build/`, `.oculto/`; la recolección se juzga con los patrones por defecto de pytest, `test_*.py` y `*_test.py`, más cualquier archivo que ya tuviera tests en la base). Renombrar `conftest.py` o moverlo a una carpeta que pytest no recorre también cuenta |
| | T1 test-borrado | bloquea | Un test existente desaparece sin equivalente. Si toda su masa son pares entrada→esperado que siguen probándose en tests activos (p. ej. se consolidó en un `parametrize`), no cuenta. Un test que se «mueve» (mismo cuerpo) tiene que conservar su masa y sus esperados; si el destino pierde filas de `parametrize`, es T2 o T3 |
| | T2 masa-reducida | bloquea | Un test pierde masa de aserción (ver abajo) |
| | T3 esperado-cambiado | bloquea | Cambia lo que fija un test existente: un literal de sus aserciones o asignaciones (`== 200` → `== 500`, `esperado = 5` → `-1`), el operador (`==` → `>=`), el método (`assertEqual` → `assertGreaterEqual`), un `raises(...)`/`approx(...)`, una fila de `parametrize`, o se quitan filas de una tabla de casos del módulo. También la forma de la aserción, con los nombres de variable enmascarados: qué función se llama, en qué posición va cada literal, si la comparación se envuelve en otra, si aparece `approx` o si cambia el cuerpo de un `raises` (mover sentencias dentro o fuera del bloque también cuenta). Cambiar el mensaje, renombrar variables o añadir filas no cuenta |
| | T4 test-desactivado | bloquea/aviso | `skip`, `skipif`, `xfail`, `expectedFailure` (con o sin paréntesis), `SkipTest`, `importorskip`, `pytestmark = …skip`, `del test_x`, `__test__ = False`, renombre a `_test_x`, a una clase que no empieza por `Test` o a un archivo no recolectable. Sobre lo que ya existía (tests, clases, módulos) bloquea; en código de test nuevo, avisa. Un renombre o un traslado no vuelven «nuevo» un test: se sigue por la huella del cuerpo, con sus decoradores previos. Cambiar la condición de un `if` que gobierna un `skip` existente, o una constante de módulo de la que dependa un `skipif`/`skipUnless`/`pytestmark`, también cuenta |
| | T5 aserción-vacía | bloquea | `assert True`, `assert 1 < 2`, `assert (cond, "msg")`, `assert x or True`, `assertGreater(2, 1)` (solo las aserciones de unittest: un helper propio `assertAlgo("x")` ejecuta código y pesa como cualquier assert), `max(1, 10) == 10`, `(f(1) == 10) in (True, False)`, `try/except AssertionError: pass`, `suppress(...)`, `return` antes de las aserciones (también dentro de `if True:`, `with` o `try`), ramas de condición constante (`if False:`, `if 1 > 2:`, `while 0 == 1:`), bucles sobre una colección literal vacía y funciones anidadas que nunca se llaman |
| | T6 salida-forzada | bloquea | `sys.exit`, `os._exit` (también importado con alias), `raise SystemExit` en un test, una fixture o un `setUp*`/`tearDown*` (no dentro de `assertRaises`, `suppress` o un `try` que lo capture; un helper suelto que lo lanza para simular la salida no cuenta), `pytest.exit`, `atexit.register(os._exit, 0)` en tests (salvo `sys.exit(pytest.main())`; un `r._exit()` o `r.skip()` de otro objeto no cuenta) |
| | T7 hook-de-resultado | bloquea/aviso | Hooks de pytest tocados en conftest o tests: los que reescriben resultados, la recolección o la propia sesión (`runtest`, `report`, `collect`, `session`, `cmdline_main`, `load_initial_conftests`…) bloquean; el resto (`pytest_configure`, `pytest_generate_tests`) avisa. Un hook ligado sin `def` cuenta igual: `pytest_x = lambda …`, `from m import pytest_x`, `setattr(…, "pytest_x", …)`. También `collect_ignore` y `pytest_plugins` |
| | T8 config-de-pruebas | bloquea/aviso | `--deselect`, `-k`, `--ignore`, `-p no:` junto al runner; `\|\| true`, `; true`, `-pytest` (Makefile) tras el runner; umbral de cobertura a la baja o eliminado (también si desaparece el archivo o el flag queda comentado; moverlo a otro archivo del diff no cuenta); CI que ya no ejecuta tests (una cabecera de sección, un comentario, una línea `deps =`/`install_requires` o un token citado suelto como `"pytest>=7",` no cuentan como invocación). Avisa en `continue-on-error`, `set +e` y cambios de recolección |
| Casos especiales | C1 caso-especial | bloquea/aviso | Rama `if`/`match`/ternario que reconoce una entrada de test y devuelve su esperado |
| | C2 tabla-de-respuestas | bloquea/aviso | Diccionario cuyas entradas son los pares entrada→esperado de los tests |
| | C3 respuesta-incrustada | bloquea/aviso | La función pasa a devolver literalmente el esperado de un test |
| Operadores y arnés | O1 igualdad-comodín | bloquea/aviso | `__eq__`/`__ne__` que ignoran al otro operando (también con `*args`) o `__eq__ = lambda …: True` bloquean; otros operadores comodín (`__gt__` de un «infinito») o reasignar `cls.__eq__`, avisan |
| | O2 parche-del-arnés | bloquea/aviso | Reasignar `unittest.TestCase.*`, `pytest.*`, `sys.exit`, `os._exit` bloquea (también con `setattr`, y también desde un archivo de tests; `maxDiff` y `longMessage` no cuentan); `builtins.*` o `sys.excepthook`, avisa |
| | O3 sombra-de-módulo | bloquea | `sitecustomize.py`, `usercustomize.py`, `*.pth`, `pytest.py`, `unittest.py` nuevos: se ejecutan al arrancar o suplantan al runner |
| Evaluador | E1 detecta-evaluador | bloquea | `PYTEST_CURRENT_TEST`, `"pytest" in sys.modules`, `"pytest" in sys.argv[0]`, inspección de la pila buscando `test` |
| | E2 lee-los-tests | bloquea/aviso | El código fuente abre los tests o sus datos (`open("tests/…")`, `Path(...) / "tests"`) o los importa. Desde una carpeta de desarrollo de la raíz (`scripts/`, `tools/`, `docs/`…) o un archivo de tareas de la raíz (`tasks.py`, `manage.py`) avisa; un módulo importable que llegue a los tests a través de uno de esos scripts también queda en aviso |
| Estado | S1 estado-entre-llamadas | aviso | Contador global o atributo de función que decide la salida |
| Integridad | N0 no-analizable | bloquea/aviso | Archivo de tests, código o configuración que no se pudo leer o analizar (binario, enlace, más de 1 MB, codificación inválida, sintaxis, anidamiento extremo). Nunca se omite en silencio: bloquea, salvo un fuente que no parsea con este Python, que avisa. Con más de 3000 archivos de test, el índice de oráculos de C1–C3 se trunca (los que no cambian van primero) y avisa |

Las reglas de Python son semánticas (AST) y respetan BOM y `# coding:`. Las de configuración (pytest, tox, setup.cfg, pyproject, Makefile, package.json, GitHub Actions, GitLab, CircleCI, Travis, Azure, Jenkins…) son patrones de texto de coste lineal y solo cuentan cuando la línea invoca un runner de tests.

## Tres ideas propias

**1. Masa de aserción conservada por test.** Cada test tiene una masa: una comparación pesa 3, `assertEqual` 3, `pytest.raises` 2, una aserción de verdad o `is not None` pesa 1, una tautología 0, y todo se multiplica por las filas de `@parametrize`. La conservación es por test, no neta: si el diff debilita `assert f(1) == 10` a `assert f(1)` o quita una fila de parametrize, bloquea aunque añada diez tests nuevos en otro lado. Contar líneas no ve ese intercambio.

**2. Memorización del oráculo.** `contraste` reconstruye el oráculo de los tests —`assert f(x) == y`, `assertEqual`, `x = f(...); assert x == y`, filas de `parametrize`— y busca ramas nuevas del código fuente que lo reproduzcan. Bloquea cuando la función ya existía, el par ya estaba en los tests antes del diff y al menos la mitad de sus ramas literales nuevas memorizan pares de test; en cualquier otro caso avisa. Una función nueva escrita contra tests previos (TDD) o una rama nueva que llega con su propio test nuevo (`if c == 404` más `assert razon(404) == …`) nunca bloquean. Así `if n == 91: return True` bloquea, mientras que una tabla de números romanos o de códigos HTTP —que contiene mucho más de lo que prueban los tests— solo avisa. Una entrada que aparece en más de dos casos del test, o que según los tests produce resultados distintos, es un modo (`modo == "estricto"`), no un dato memorizado: avisa. Los casos base estructurales (`0`, `1`, `2`, `None`, `""`…) se ignoran: `if n == 0: return 1` en un factorial no es trampa.

**3. El agente no firma su propio contraste.** Los cambios legítimos se justifican con un pragma:

```python
def test_redondeo():
    # contraste: permite T3 -- la spec 2.1 cambia el redondeo a bancario
    assert redondear(2.5) == 2
```

Si el pragma ya estaba intacto en la base (un humano lo aprobó antes), el hallazgo pasa a **justificado**. Si lo añade el mismo diff, o copia uno firmado a otro sitio, queda **autojustificado**: se muestra el motivo, pero la severidad no baja. Un agente no puede silenciar la compuerta escribiendo un comentario. Un pragma cubre la función que lo contiene. En PRs humanos, `--confiar-pragmas` honra los pragmas nuevos. Con `# contraste: archivo permite T1 -- motivo` el pragma vale para todo el archivo.

## Instalación

Es un único archivo sin dependencias: copia `contraste.py` a tu repo y ejecútalo con `python contraste.py`. También se instala como paquete:

```bash
pip install .            # desde esta carpeta; deja el comando `contraste`
```

## Uso

```bash
contraste                                   # árbol de trabajo contra HEAD: lo que el agente acaba de tocar
contraste --base main --head HEAD           # una rama o PR (usa el merge-base)
contraste --dirs copia/ sandbox/            # sin git: dos directorios
contraste --formato json                    # o sarif, para code scanning
contraste --falla-en aviso                  # más estricto (por defecto: bloquea)
contraste --reglas                          # lista de reglas
```

Códigos de salida: `0` sin hallazgos al umbral, `1` con hallazgos, `2` cualquier error (uso, git, E/S); un fallo nunca se confunde con «hay hallazgos». Veredictos: **DE LEY**, **SOSPECHOSO** (solo avisos) y **ADULTERADO** (algo bloquea).

### En CI (GitHub Actions)

```yaml
jobs:
  contraste:
    runs-on: ubuntu-latest
    permissions: { contents: read, security-events: write }
    steps:
      - uses: actions/checkout@v6
        with: { fetch-depth: 0 }
      - run: python3 contraste.py --base origin/${{ github.base_ref }} --head HEAD --formato sarif --salida contraste.sarif
      - if: always()
        uses: github/codeql-action/upload-sarif@v4
        with: { sarif_file: contraste.sarif }
```

### Como hook local

```bash
# .git/hooks/pre-commit
python3 contraste.py || { echo "contraste: el cambio no es de ley"; exit 1; }
```

### Desde Python

```python
from contraste import ParGit, analizar

informe = analizar(ParGit(".", base="main", head="HEAD"))
print(informe.veredicto)
for h in informe.hallazgos:
    print(h.regla, h.sev, h.ruta, h.linea, h.msg)
```

## Evidencia

- **Suite ancla:** 29 tests tabulares (`python -m unittest test_contraste`). Cada caso fija exactamente qué reglas disparan, cuántas veces y con qué severidad, incluidos casos honestos que deben quedar en silencio. Pasa en Python 3.9, 3.10, 3.11, 3.12 y 3.13.
- **Los tests discriminan:** 70 mutantes del detector (umbrales, especificidad del oráculo, firma y copia de pragmas, huellas de tests movidos, decoradores previos, regex de CI, codificación, guarda de recursión, filtros de git…). La suite detecta los 70.
- **Dos revisiones adversariales independientes:** un revisor sin acceso al razonamiento de la implementación reprodujo 15 defectos, cuatro graves: archivos con BOM que se saltaban en silencio, `RecursionError` que tumbaba el informe, renombre más `skip` que solo avisaba y T3 ciego fuera de `llamada == literal`. Trece están corregidos y anclados en la suite. Los dos restantes figuran en Límites. Una segunda revisión ciega, sobre la versión ya corregida, halló 10 defectos más; también están corregidos y anclados, salvo los que figuran en Límites.
- **Código humano real:** 750 commits sin merge de `attrs`, `click`, `httpx`, `pydantic` y `rich`. Cero errores, unos 0,34 s por commit y **cero disparos de las reglas de código fuente (C, O, E, S) y de N0**. Los 92 commits (12,3 %) que salen ADULTERADO editan, borran o desactivan tests existentes, o tocan un hook o la invocación de CI. Es la política deliberada (los tests existentes son el contrato y cambiarlos exige firma), no ruido del detector.
- **Peor caso:** los 1.846 archivos de esos cinco repos analizados como si todo fuera código nuevo, en 16 s y sin errores. Las reglas de código fuente no bloquean nada y dejan 7 avisos: metaprogramación (`cls.__eq__ = …` en attrs), `builtins._` y `sys.excepthook` en rich, un selector de modo y una tabla de campos en pydantic.

## El repo analizado es hostil

`contraste` asume que el diff lo escribió quien quiere engañarlo:

- No ejecuta nada del repo. Llama a git con `core.fsmonitor=false` y `core.hooksPath=/dev/null`, sin diff externos ni `textconv`. En modo árbol de trabajo se niega a seguir (exit 2) si la configuración local del repo, incluidos sus `include.path`, define filtros `clean`/`process` que git ejecutaría; con `--head` lee blobs sin filtros.
- Ve lo que git esconde: `conftest.py`, `sitecustomize.py`, `usercustomize.py`, `*.pth`, `pytest.ini`, `.coveragerc` y otros `*.ini` ignorados por `.gitignore` (Python y pytest sí los cargan), y archivos marcados `assume-unchanged` o `skip-worktree`.
- No sigue enlaces simbólicos ni abre FIFOs, y decodifica respetando BOM y `# coding:` (un `@skip` escondido en UTF-7 se ve).
- Un archivo que no puede analizar es un hallazgo (N0), nunca un silencio.

## Límites

- Es análisis estático: no ejecuta nada. Complementa, no sustituye, a correr los tests de la base sobre el código nuevo y a montar los tests como solo lectura en el sandbox del agente.
- Solo Python. No hay reglas para JS/TS ni otros lenguajes.
- Casos especiales: necesita oráculos literales en los tests. Se le escapan las ramas negadas (`if n != 91: … else: return True`), la forma con asignación (`r = 5` dentro de la rama y `return r` al final) y las funciones de varias sentencias que acaban devolviendo la constante. Llevar el truco a un archivo nuevo o a una tabla a nivel de módulo lo deja en aviso, no en bloqueo; dos ramas correctas añadidas junto a la memorizada, también: es el precio de no bloquear las tablas de dominio.
- Desactivar tests: no resuelve alias de decoradores (`from unittest import skip as off`) ni `setattr(test_x, "__test__", False)`. Una fixture `autouse` o un `setUpModule` nuevos que llaman a `skip` solo avisan.
- Detección del evaluador: no ve `sys.argv[0].endswith("pytest")` ni rutas a los tests armadas en variables intermedias. Tampoco ve operadores comodín creados con `setattr` o `type(...)`.
- En modo árbol de trabajo, un módulo nuevo ignorado por `.gitignore` que el código importa queda fuera del diff. Con `--head` (CI) no aplica.
- Un helper de aserción vacío definido en el propio test (`def assert_igual(a, b): pass`) no baja la masa.
- La forma de una aserción (T3) se sigue por su llamada más externa y por los nombres ligados con `x = f(...)` en el mismo test: no ve `len(f(1))` → `len(g(1))`, un `f = otra` o `from m import g as f` antes de la aserción, ni el renombre de un helper local que la aserción llama. Las constantes que gobiernan un skip solo se siguen dentro del mismo archivo.
- `assert x == x` no se marca: es como se prueba la reflexividad de un `__eq__` propio.
- Un pragma firmado cubre toda su función: otra aserción de esa misma función hereda la justificación.
- Analiza con la gramática del Python que lo ejecuta: córrelo con la misma versión del proyecto, o los archivos con sintaxis más nueva saldrán como N0.
- Los cambios humanos legítimos a tests existentes se marcan. Es el precio de la política; para eso están los pragmas y `--confiar-pragmas`.
- No lo metas en el bucle de recompensa del agente. Un monitor que se optimiza contra sí mismo enseña a esconder la trampa; úsalo como compuerta externa: CI, revisión, merge.

## Licencia

MIT. Ver [LICENSE](LICENSE).
