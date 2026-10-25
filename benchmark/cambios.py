import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ensayo_hacktrace import rasgos_test
E1, E2 = sys.argv[1], sys.argv[2]
verdad = {j["id"]: j for j in map(json.loads, open(E1 + "/verdad.jsonl", encoding="utf-8"))}
pares = {j["id"]: j for j in map(json.loads, open(E1 + "/pares.jsonl", encoding="utf-8"))}
r1 = {j["id"]: j for j in map(json.loads, open(E1 + "/resultados.jsonl", encoding="utf-8"))}
r2 = {j["id"]: j for j in map(json.loads, open(E2 + "/resultados.jsonl", encoding="utf-8"))}
trans = collections.Counter((verdad[i]["categoria"], r1[i]["veredicto"], r2[i]["veredicto"]) for i in r1 if r1[i]["veredicto"] != r2[i]["veredicto"])
print("## transiciones de veredicto v1 -> v2")
for k, n in sorted(trans.items()):
    print("  ", n, k)
print("\n## honestos que pasan a ADULTERADO")
for i in r1:
    v = verdad[i]
    if v["tipo"] == "honesto" and r1[i]["veredicto"] != "ADULTERADO" and r2[i]["veredicto"] == "ADULTERADO":
        p = pares[i]; rs = rasgos_test(p["base"]["test.py"], p["head"]["test.py"])
        print("  ", i, v["categoria"], rs["mecanismo"], "asserts", rs["asserts_base"], "->", rs["asserts_head"], [h["regla"] + ":" + h["msg"][:60] for h in r2[i]["hallazgos"]])
        print("     juez:", (v["razon_juez"] or "")[:250].replace("\n", " "))
        print("     head test.py:", repr(p["head"]["test.py"][:500]))
print("\n## test_tamper que siguen escapando, por mecanismo y ejemplo")
esc = collections.defaultdict(list)
for i in r2:
    v = verdad[i]
    if v["categoria"] == "test_tamper" and r2[i]["veredicto"] == "DE LEY":
        p = pares[i]; rs = rasgos_test(p["base"]["test.py"], p["head"]["test.py"]) if not v["tests_iguales"] else {"mecanismo": "tests_iguales"}
        esc[rs["mecanismo"]].append(i)
for m, ids in sorted(esc.items(), key=lambda kv: -len(kv[1])):
    print("  ", len(ids), m)
    for i in ids[:2]:
        p = pares[i]
        print("     ", i, "juez:", (verdad[i]["razon_juez"] or "")[:200].replace("\n", " "))
        print("      head test.py:", repr(p["head"]["test.py"][:420]))
