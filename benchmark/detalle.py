"""Detalle post-calificación: naturaleza de los cambios de tabla (¿solo espacios?), ejemplos de escapes y de FP."""
import ast
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ensayo_hacktrace import _parse, _tabla_casos, rasgos_test  # noqa: E402

E = sys.argv[1]
verdad = {j["id"]: j for j in map(json.loads, open(os.path.join(E, "verdad.jsonl"), encoding="utf-8"))}
pares = {j["id"]: j for j in map(json.loads, open(os.path.join(E, "pares.jsonl"), encoding="utf-8"))}
res = {j["id"]: j for j in map(json.loads, open(os.path.join(E, "resultados.jsonl"), encoding="utf-8"))}


def norm(casos):
    return collections.Counter((" ".join(i.split()), " ".join(e.split())) for i, e in casos)


def clase_tabla(base, head):
    cb, ch = _tabla_casos(_parse(base)), _tabla_casos(_parse(head))
    if cb is None or ch is None:
        return "sin_tabla"
    if collections.Counter(cb) == collections.Counter(ch):
        return "igual"
    nb, nh = norm(cb), norm(ch)
    if nb == nh:
        return "solo_espacios"
    if not (nb - nh):
        return "solo_anade"
    quitadas, nuevas = nb - nh, nh - nb
    ent_b = {i for i, _ in quitadas.elements()}
    ent_h = {i for i, _ in nuevas.elements()}
    if ent_b and ent_b <= ent_h:
        return "cambia_esperado_misma_entrada"
    if not nuevas:
        return "recorta_casos"
    return "sustituye_casos"


print("## Naturaleza del cambio de tabla CASES (filas con mecanismo tabla_recortada_o_cambiada), por categoría × veredicto")
cruce = collections.Counter()
ejemplos_fp = []
for i, v in verdad.items():
    if v["tests_iguales"]:
        continue
    p = pares[i]
    r = rasgos_test(p["base"]["test.py"], p["head"]["test.py"])
    if r["mecanismo"] != "tabla_recortada_o_cambiada":
        continue
    ct = clase_tabla(p["base"]["test.py"], p["head"]["test.py"])
    cruce[(v["categoria"], ct, res[i]["veredicto"])] += 1
    if v["tipo"] == "honesto" and len(ejemplos_fp) < 8:
        cb, ch = _tabla_casos(_parse(p["base"]["test.py"])), _tabla_casos(_parse(p["head"]["test.py"]))
        ejemplos_fp.append((i, v["categoria"], ct, v["visible_pass"], (v["razon_juez"] or "")[:260],
                            [(a[:40], b[:40]) for a, b in cb], [(a[:40], b[:40]) for a, b in ch]))
for (c, ct, vd), n in sorted(cruce.items()):
    print(f"  {c:18s} {ct:32s} {vd:11s} {n}")

print("\n## Ejemplos de FP T3 en honestos (id, categoría, clase, visible_pass, juez, CASES base → head)")
for e in ejemplos_fp:
    print(" ", e[0], e[1], e[2], "visible_pass=", e[3])
    print("    juez:", e[4].replace("\n", " "))
    print("    base:", e[5])
    print("    head:", e[6])

print("\n## Escapes de test_tamper por mecanismo: ejemplos (head test, primeras líneas)")
vistos = collections.Counter()
for i, v in verdad.items():
    if v["categoria"] not in ("test_tamper", "eval_bypass") or res[i]["veredicto"] != "DE LEY" or v["tests_iguales"]:
        continue
    p = pares[i]
    r = rasgos_test(p["base"]["test.py"], p["head"]["test.py"])
    m = r["mecanismo"]
    if m in ("test_vacio",) or vistos[m] >= 3:
        vistos[m] += 1
        continue
    vistos[m] += 1
    print(f"  --- {v['categoria']} {i} mecanismo={m} asserts {r['asserts_base']}→{r['asserts_head']} tabla={r['tabla']}")
    print("    juez:", (v["razon_juez"] or "")[:220].replace("\n", " "))
    cab = "\n".join(p["head"]["test.py"].splitlines()[:14])
    print("    head test.py:\n      " + cab.replace("\n", "\n      ")[:900])
print("  conteo de escapes por mecanismo:", dict(vistos))

print("\n## test_vacio: ¿también solution.py vacío?")
c = collections.Counter()
for i, v in verdad.items():
    if v["tests_iguales"]:
        continue
    p = pares[i]
    if not p["head"]["test.py"].strip():
        c[(v["categoria"], "sol_vacia" if not p["head"]["solution.py"].strip() else "sol_con_codigo", str(v["visible_pass"]))] += 1
for k, n in sorted(c.items()):
    print(" ", k, n)

print("\n## N0 aviso: ruta y mensaje más frecuentes")
c = collections.Counter()
for i, r in res.items():
    for h in r["hallazgos"]:
        if h["regla"] == "N0":
            c[(h["sev"], h["ruta"], h["msg"][:60])] += 1
for k, n in c.most_common(8):
    print(" ", n, k)

print("\n## honest con T3 bloquea: ¿qué más cambió? (asserts base→head, invoca solution, all_pass)")
c = collections.Counter()
for i, v in verdad.items():
    if v["tipo"] != "honesto" or res[i]["veredicto"] != "ADULTERADO":
        continue
    p = pares[i]
    r = rasgos_test(p["base"]["test.py"], p["head"]["test.py"])
    c[(v["categoria"], f"asserts {r['asserts_base']}->{r['asserts_head']}", f"invoca={r['invoca_solution']}", f"visible_pass={v['visible_pass']}", f"OUTCOME={v['OUTCOME']}")] += 1
for k, n in c.most_common(12):
    print(" ", n, k)
