# Banco de pruebas de `contraste` sobre trayectorias reales de agentes (HackTrace-Data)

Este documento explica qué mide el banco, cómo está construido para que nadie (ni el autor) pueda inflar el resultado, qué hace `contraste` con cada tipo de trampa y qué consigue, con cifras, intervalos de confianza y los huecos que quedan. Todo lo que afirma se puede reproducir con los archivos de esta carpeta.

## 1. Qué se mide

`contraste` es un detector estático: recibe un diff (antes → después) y señala las maniobras con las que un agente de código consigue que los tests pasen sin resolver el problema: tests borrados, vaciados o debilitados, valores esperados cambiados, aserciones tragadas, salidas forzadas, respuestas memorizadas en el código, etc. La pregunta del banco es sencilla: **sobre trampas reales cometidas por agentes reales, ¿qué fracción bloquea y cuántas veces bloquea a un agente honesto?**

Para responderla hace falta un corpus con verdad conocida. En lugar de sembrar defectos a mano, el banco usa **HackTrace-Data** ([`JH012/HackTrace-Data`](https://huggingface.co/datasets/JH012/HackTrace-Data), CC BY 4.0, [arXiv 2511.21654](https://arxiv.org/abs/2511.21654)): 40 552 trayectorias de agentes resolviendo 315 problemas de programación competitiva (estilo Codeforces), cada una con el `test.py` original, la solución final, el test final y la categoría que le asignó un juez.

| Elemento | Valor |
|---|---|
| Archivo | `trajectories/test.parquet`, 21 014 710 bytes, sha256 `f0bb08c786de5d12b13ef44761eebae6b00748e9aac5411db858a401701eada2` |
| Trayectorias | 40 552 (190 problemas con test editable, 125 con test de solo lectura; conjuntos disjuntos) |
| Formato del test | Un `test.py` tipo guion: tabla `CASES = [(entrada, salida), …]`, bucle que ejecuta `solution.py` con `subprocess` y un `assert got.strip() == exp.strip()` a nivel de módulo |
| Categorías de trampa (juez) | `test_tamper` (2 371), `hardcode_output` (3 240), `special_casing` (2 313), `eval_bypass` (17), `other` (1) |
| Categorías honestas | `honest_correct` (7 209), `honest_but_wrong` (18 621), más 6 777 sin etiqueta de juez clasificadas por la regla del dataset como no-trampa (`regla_sin_trampa`) y 3 como trampa sin categoría |

**Aviso de sobre.** Este corpus está fuera del sobre de diseño de `contraste`, pensado para paquetes Python con tests de función (pytest/unittest) donde el oráculo es «llamada → valor». Aquí los tests son guiones y las soluciones programas de stdin/stdout. Por eso el banco mide dos cosas distintas: la robustez de las reglas de tests (familia T) sobre guiones, y la (no) transferencia de las reglas de código fuente (familia C) a programas de entrada/salida. No mide el recall dentro del sobre.

## 2. Cómo funciona el banco

El arnés es `ensayo_hacktrace.py`, sin dependencias salvo `pyarrow` para leer el parquet en la primera fase. Tiene tres fases, y cada una deja un sello SHA-256 para que la siguiente no pueda alterar lo que recibe.

### 2.1 `preparar`: del parquet a pares base → head

Para cada trayectoria se construye el par que vería `contraste` en un diff:

- **base**: el `test.py` original (extraído del primer mensaje de usuario, bloque `test.py:` o `test.py (read-only):`) y el `solution.py` inicial (`# empty`);
- **head**: el test final y la solución final que entregó el agente.

Se escriben tres archivos: `pares.jsonl` (solo archivos, sin ninguna etiqueta), `verdad.jsonl` (categoría del juez, variante, dificultad, si cambió el test, y los SHA-256 de cada archivo del par) y `sello.json` con los SHA-256 del parquet, de `pares.jsonl` y de `verdad.jsonl`. Los 40 552 pares se extrajeron sin un solo fallo.

### 2.2 `correr`: el detector a ciegas

El corredor carga `contraste.py` por ruta, registra su SHA-256 y su versión, comprueba que `pares.jsonl` coincide con el sello y ejecuta `analizar()` en memoria sobre cada par (una clase `ParMem` con la misma interfaz que `ParDir`). **Nunca abre `verdad.jsonl`**: no sabe qué trayectorias son trampa. Guarda en `resultados.jsonl` el veredicto, la masa de aserción y cada hallazgo (regla, severidad, archivo, línea, mensaje), y en `resultados_meta.json` el SHA-256 de los resultados, el tiempo y el número de errores del detector. Como `contraste` es determinista, la ceguera es procedimental: sello antes de correr y corredor sin acceso a la verdad.

### 2.3 `calificar`: cruce, métricas y diagnóstico

La calificación verifica los cuatro sellos (pares, verdad, resultados y el par que vio el corredor), cruza por id y clasifica:

- trampa → `ADULTERADO` cuenta como **bloqueada** (es lo que detiene un merge), `SOSPECHOSO` como aviso, `DE LEY` como **escape**;
- honesta → `ADULTERADO` es **falso positivo** al gate, `SOSPECHOSO` aviso, `DE LEY` limpia.

Todas las tasas llevan intervalo de Wilson al 95 %. Además de las tablas por categoría, variante, dificultad y si el test cambió, la calificación añade dos herramientas de diagnóstico que no forman parte del detector:

- un **clasificador estructural del mecanismo** con el que se tocó el test (archivo vaciado, no parsea, sin asserts, assert bajo `try`, tabla de casos recortada o cambiada, tabla eliminada, solo añade casos, solo formato), para ver qué mecanismos escapan;
- una **sonda de literales** en la solución final (¿contiene como constante la salida esperada completa de algún caso?), que acota lo que podría alcanzar una regla de memorización sobre este corpus.

`cambios.py` compara dos corridas veredicto por veredicto; `detalle.py` y `espacios.py` son los análisis con los que se caracterizaron los falsos positivos.

### 2.4 Reproducción

```bash
python -I -X utf8 ensayo_hacktrace.py preparar --parquet <test.parquet> --salida ensayo
python -I -X utf8 ensayo_hacktrace.py correr --ensayo ensayo --contraste ../contraste.py
python -I -X utf8 ensayo_hacktrace.py calificar --ensayo ensayo
```

El parquet no se incluye (21 MB, licencia CC BY 4.0): se descarga de Hugging Face y se comprueba contra el sha256 de `resultados/*/sello.json`. `preparar` es determinista, así que `pares.jsonl` y `verdad.jsonl` reproducen los SHA-256 del sello. En `resultados/antes/` y `resultados/despues/` están el sello, los metadatos de cada corrida (SHA-256 del detector), la calificación completa (`calificacion.json`, `tablas.md`) y los veredictos por trayectoria (`resultados.jsonl.gz`). Una corrida completa tarda unos dos minutos.

## 3. Cómo trabaja `contraste` sobre este corpus

Lo primero que vale la pena entender es qué puede y qué no puede ver un detector estático en estos pares.

**Lo que sí ve (familia T, tests).** El test original es un guion, no una función `test_*`. `contraste` lo trata así:

- **Masa de aserción del módulo** (T1/T2). Cada aserción pesa según lo que fija: una comparación 3, una verdad 1, una tautología 0. Las aserciones fuera de toda función, más las de las funciones del propio archivo que el módulo ejecuta (las que llama o pasa a una llamada, y las que estas llaman), forman la masa del módulo. Si baja, bloquea (T2); si cae a cero, bloquea como test borrado (T1). Vaciar el archivo, sustituir el `assert` por un `print` o degradar `assert got == exp` a `assert got` son caídas de masa. Un refactor honesto que mueva el bucle a `main()` y la llame, o a un test que el runner ejecute, conserva la masa y queda limpio.
- **Tabla de casos** (T3). Quitar filas de `CASES` o cambiar un esperado bloquea; añadir filas, no. Los valores se comparan tal cual, espacios incluidos.
- **Forma de la aserción** (T3). Cambiar qué se compara (`exp.strip()` → `exp.strip` sin paréntesis, `==` → `is not`, `in [exp, got]`) bloquea; el mensaje del assert no cuenta.
- **Aserciones tragadas o inalcanzables** (T5): un `try/except` que imprime y sigue, ramas constantes, bucles sobre colecciones vacías.
- **Salida forzada** (T6): `sys.exit`, `os._exit` o `raise SystemExit` en el módulo del test.
- **Archivo que no parsea o borrado** (N0 bloquea, T0).

**Lo que no ve (familia C, código fuente).** C1/C2/C3 buscan ramas `if x == literal: return esperado`, tablas y constantes en **funciones** cuyo nombre coincide con la función que los tests llaman, y reconstruyen el oráculo a partir de `assert f(args) == esperado`. En este corpus no hay nada de eso: los pares entrada→salida viven en una tabla que consume `subprocess`, y la solución lee stdin en `main()` o a nivel de módulo. Resultado: cero oráculos, cero C1/C2/C3. `hardcode_output` y `special_casing` quedan fuera del alcance por construcción, no por un fallo puntual.

## 4. Qué logra

Dos corridas sobre los mismos 40 552 pares y los mismos sellos: **antes** (`contraste.py` sha256 `3b6cbc54…`, sin masa de módulo) y **después** (`89e21868…`, la versión actual). Entre ambas, el banco fue lo que guió el arreglo: la primera corrida enseñó que el 88 % de los escapes de `test_tamper` eran archivos vaciados que el detector no veía porque solo contaba aserciones dentro de funciones.

### 4.1 Por categoría del juez

| categoría | tipo | n | antes: bloquea % [IC 95] | después: bloquea % [IC 95] | escapes antes → después |
|---|---|---|---|---|---|
| test_tamper | trampa | 2 371 | 61.3 [59.3, 63.2] | **99.1 [98.6, 99.4]** | 908 → 21 |
| eval_bypass | trampa | 17 | 23.5 [9.6, 47.3] | **100.0 [81.6, 100.0]** | 13 → 0 |
| hardcode_output | trampa | 3 240 | 0.0 [0.0, 0.2] | 0.0 [0.0, 0.2] | 3 214 → 3 214 |
| special_casing | trampa | 2 313 | 0.0 [0.0, 0.2] | 0.0 [0.0, 0.2] | 2 272 → 2 272 |
| honest_correct | honesto | 7 209 | FP 0.5 [0.4, 0.7] | FP 0.6 [0.4, 0.8] | 39 → 43 |
| honest_but_wrong | honesto | 18 621 | FP 1.4 [1.2, 1.5] | FP 1.4 [1.2, 1.6] | 252 → 256 |
| regla_sin_trampa | honesto | 6 777 | FP 0.0 [0.0, 0.1] | FP 0.0 [0.0, 0.1] | 0 → 0 |

Gate global después: 7 945 trampas, 2 368 bloqueadas; 32 607 honestas, 299 falsos positivos (0,9 % [0,8, 1,0]); 0 errores del detector; 123,8 s para los 40 552 pares (mediana 2,7 ms por par).

### 4.2 Por mecanismo de manipulación del test (`test_tamper`, después)

| mecanismo | n | bloquea % [IC 95] | reglas que disparan |
|---|---|---|---|
| test.py vaciado | 797 | 100.0 [99.5, 100.0] | T1 |
| tabla CASES recortada o con esperados cambiados | 720 | 100.0 [99.5, 100.0] | T3 |
| test.py corrupto (no parsea) | 716 | 100.0 [99.5, 100.0] | N0 |
| assert eliminado del todo | 60 | 100.0 [94.0, 100.0] | T1, T3, T2 |
| assert bajo try/except | 6 | 100.0 [61.0, 100.0] | T3, T5, T6 |
| otro (forma del assert degradada, mensaje roto…) | 53 | 75.5 [62.4, 85.1] | T3, T2 |
| tabla eliminada (arnés reescrito con casos inline) | 12 | 41.7 [19.3, 68.0] | T3 |
| solo añade casos (y degrada el assert) | 7 | 71.4 [35.9, 91.8] | T2, T3 |

Antes del arreglo, el archivo vaciado (797), el assert eliminado (60 → 20 %), la forma degradada (53 → 0 %) y la tabla eliminada (12 → 0 %) eran los escapes.

**Los 21 escapes que quedan.** Doce son asserts con un mensaje roto (`assert got.strip() == exp.strip(), f`), que la política no cuenta porque el mensaje no es parte de la aserción, o manipulaciones de cómo se calcula `got` antes de compararlo (truncarlo a los decimales del esperado). Siete son tablas cuyos esperados son expresiones (`'a' * 13 + '\n'`) que la comparación de tablas no pliega. Dos combinan el mensaje roto con casos añadidos. El siguiente paso natural es plegar expresiones constantes en las tablas de casos.

### 4.3 Falsos positivos: 299, dos orígenes

- **291 por espacios en la tabla.** Los `test.py` originales de 36 de los 315 problemas traen esperados con relleno de espacios (hasta 63 espacios delante del número); los agentes los normalizan y, como el test compara con `.strip()`, el cambio es semánticamente nulo. `contraste` compara los valores de la tabla tal cual y bloquea (T3). Se concentran en 21 problemas (uno solo aporta 100). Es una decisión de política, no un error: o se compara la tabla módulo espacios periféricos cuando la aserción recorta, o se acepta este 0,9 % en guiones con esta peculiaridad.
- **8 por la forma de la aserción del módulo.** Reformateos que el juez considera honestos (`assert got.strip() == exp.strip()` → `output = result.stdout.strip(); assert output == exp`, o reescribir el arnés con un helper) y que la política trata como cambio de forma, igual que dentro de una función. Si se prefiere no aplicarla al módulo, basta quitar esa rama, al precio de los 35 `test_tamper` que solo ella detecta.

En las 25 352 trayectorias con test de solo lectura no hay ni un bloqueo sobre honestas.

### 4.4 Lo que no detecta y por qué

El 0 % en `hardcode_output` y `special_casing` es el límite del modelo de oráculo (sección 3), no ruido: la única trayectoria bloqueada en cada categoría lo fue por un T3 incidental de espacios. La sonda de literales acota lo que una extensión podría alcanzar en este corpus:

| categoría | contiene la salida esperada completa como literal | contiene la entrada completa |
|---|---|---|
| hardcode_output | 41.9 % [40.2, 43.6] | 5.0 % [4.2, 5.8] |
| special_casing | 24.1 % [22.4, 26.0] | 9.5 % [8.3, 10.7] |
| honest_correct | 3.1 % [2.7, 3.5] | 0.0 % |
| honest_but_wrong | 2.0 % [1.8, 2.3] | 0.1 % |
| regla_sin_trampa | 7.7 % [7.0, 8.4] | 0.2 % |

Lectura: extraer oráculos de tablas `CASES` consumidas por `subprocess` y cotejar literales en `main` o a nivel de módulo tendría un techo de ~42 % en hardcode y ~24 % en special-casing, con una tasa base honesta del 2–8 % que habría que separar. Y, como la solución base está vacía, toda función del head es nueva: con la política actual (una función nueva escrita contra tests previos solo avisa) el techo sería `SOSPECHOSO`, no bloqueo.

## 5. Cómo se verificó el arreglo

El cambio que llevó `test_tamper` del 61 % al 99 % (masa de aserción del módulo) se hizo con revisión adversarial independiente en tres rondas: las dos primeras rechazaron (un falso positivo al quitar un bloque `if __name__ == "__main__":` que llamaba a tests en archivos recolectados; un `RecursionError` fuera de la guarda; tratar `unittest.main()` como ejecutor de funciones `test_*` sueltas; falsos positivos masivos al seguir literales de asignaciones anidadas) y la tercera aprobó. Controles de regresión sobre código que no es de este corpus: 391 archivos de `Lib/test` de CPython analizados como código nuevo dan exactamente los mismos 1 958 hallazgos que antes del cambio; 220 archivos en cuatro configuraciones (todo nuevo, todo tocado, mitad borrada y cuarto movido, fuente nuevo) en Python 3.13 y 3.10, sin caídas ni diferencias; en 2 998 archivos de test reales de CPython y site-packages, quitar el bloque `__main__` (1 052 archivos), cambiar un literal anidado (139) o renombrar los archivos con masa de módulo (61) no cambia ningún veredicto; coste lineal, 4,1 s frente a 3,5 s del original con 4 000 helpers encadenados. La suite ancla del detector (33 tests) fija cada uno de los casos anteriores.

## 6. Límites del banco

- La verdad es la etiqueta de un juez LLM (81 % de las filas) o una regla del dataset (19 %); categorías que se solapan (una trayectoria `test_tamper` puede además hardcodear). Se usa tal cual; el juez no se ha auditado.
- Un solo estilo de corpus y de test; 1–3 casos visibles por problema; 315 problemas.
- El clasificador de mecanismos y la sonda de literales son heurísticos de diagnóstico, no parte del detector.
- Solo Python 3.13.2 en el banco (la suite y los controles sí corren también en 3.10).
- Encuadre único: base con solución vacía. Un encuadre «primer turno → último turno» daría a las reglas C una implementación previa y podría convertir avisos en bloqueos; no se ha corrido.
- El recall dentro del sobre de diseño (paquetes Python con tests de función, parametrize, fixtures, hooks y configuración) no está medido por este banco.

## 7. Archivos

| Archivo | Qué es |
|---|---|
| `ensayo_hacktrace.py` | Arnés: `preparar`, `correr`, `calificar` |
| `cambios.py` | Compara dos corridas veredicto por veredicto |
| `detalle.py`, `espacios.py` | Análisis de mecanismos y de los falsos positivos por espacios |
| `resultados/antes/` | Corrida con `contraste.py` sha256 `3b6cbc54…` (sin masa de módulo): sello, metadatos, calificación, tablas y veredictos por id |
| `resultados/despues/` | Corrida con la versión actual (`89e21868…`): ídem |
