import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ensayo_hacktrace import _parse, _tabla_casos
E = sys.argv[1]
verdad = {j["id"]: j for j in map(json.loads, open(E + "/verdad.jsonl", encoding="utf-8"))}
pares = {j["id"]: j for j in map(json.loads, open(E + "/pares.jsonl", encoding="utf-8"))}
por_problema = {}
for i, v in verdad.items():
    if v["problema"] in por_problema:
        continue
    casos = _tabla_casos(_parse(pares[i]["base"]["test.py"])) or []
    raro = any(e != e.strip() + "\n" and e != e.strip() for _, e in casos)
    muy_raro = any(len(e) - len(e.lstrip()) > 2 or len(e) - len(e.rstrip()) > 2 for _, e in casos)
    por_problema[v["problema"]] = (raro, muy_raro, len(casos))
print("problemas:", len(por_problema), "con esperado con espacios no triviales:", sum(r for r, _, _ in por_problema.values()),
      "con relleno de espacios >2:", sum(m for _, m, _ in por_problema.values()))
print("casos por problema:", collections.Counter(n for _, _, n in por_problema.values()))
# trayectorias honestas bloqueadas: ¿de cuántos problemas distintos?
bloq = collections.Counter(v["problema"] for i, v in verdad.items() if v["tipo"] == "honesto")
res = {j["id"]: j["veredicto"] for j in map(json.loads, open(E + "/resultados.jsonl", encoding="utf-8"))}
fp = collections.Counter(v["problema"] for i, v in verdad.items() if v["tipo"] == "honesto" and res[i] == "ADULTERADO")
print("FP honestos por problema (top 8):", fp.most_common(8))
print("problemas distintos con FP:", len(fp))
print(repr(pares["8c62a7c3b4eb5038"]["base"]["test.py"][:400]))
