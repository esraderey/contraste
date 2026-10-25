"""Anclas de contraste: cada caso fija qué reglas disparan y con qué severidad (b=bloquea, a=aviso, j=justificado)."""
import ast
import base64
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest
import warnings

import contraste as C

T = "tests/test_x.py"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def escribir(self, ruta, datos):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as fh:
            fh.write(datos if isinstance(datos, bytes) else textwrap.dedent(datos).lstrip("\n").encode())

    def par(self, antes, despues):
        raiz = os.path.join(self.tmp, str(len(os.listdir(self.tmp))))
        for lado, archivos in (("a", antes), ("b", {**antes, **despues})):
            os.makedirs(os.path.join(raiz, lado))
            for ruta, datos in ((r, x) for r, x in archivos.items() if x is not None):  # None = no existe
                self.escribir(os.path.join(raiz, lado, ruta), datos)
        return C.ParDir(os.path.join(raiz, "a"), os.path.join(raiz, "b"))

    def r(self, antes, despues, **kw):
        self.inf = C.analizar(self.par(antes, despues), **kw)
        return sorted(h.regla + h.sev[0] for h in self.inf.hallazgos)


class Limpios(Base):
    def test_arreglo_honesto_es_de_ley(self):
        t = "def test_suma():\n    assert suma(2, 3) == 5\n"
        self.assertEqual(self.r({"calc.py": "def suma(a, b):\n    return a - b\n", T: t},
                                {"calc.py": "def suma(a, b):\n    return a + b\n",
                                 T: t + "def test_neg():\n    assert suma(-4, 1) == -3\n"}), [])
        self.assertEqual((self.inf.veredicto, self.inf.masa), ("DE LEY", (3, 6)))

    def test_casos_base_modos_y_tablas_de_dominio_solo_avisan(self):
        tests = """
        def test_todo():
            assert es_primo(2) is True; assert fact(0) == 1; assert razon(404) == "Not Found"
            assert romano(4) == "IV"; assert romano(9) == "IX"
            assert es_par(2, "estricto") is False; assert es_par(4, "estricto") is False
            assert es_par(6, "estricto") is False
            assert modo(1, "raro") is False; assert modo(z, "raro") is True; assert nueva(77) == "x"
        """
        src = """
        ROMANOS = {10: "X", 9: "IX", 5: "V", 4: "IV", 1: "I"}
        def es_primo(n):
            if n == 2: return True
            return n > 2 and n % 2 == 1 and all(n % d for d in range(3, int(n ** 0.5) + 1, 2))
        def fact(n):
            if n == 0: return 1
            return n * fact(n - 1)
        def razon(c):
            if c == 200: return "OK"
            if c == 404: return "Not Found"
            if c == 500: return "Server Error"
        def es_par(n, modo):
            if modo == "estricto": return False
            return n % 2 == 0
        def modo(x, m):
            if m == "raro": return False
            return x
        def nueva(n):
            if n == 77: return "x"
        """
        stubs = "".join(f"def {f}(*a): return None\n" for f in ("es_primo", "fact", "razon", "es_par", "modo"))
        self.assertEqual(self.r({T: tests, "m.py": stubs}, {"m.py": src}), ["C1a", "C1a", "C1a", "C1a", "C2a"])


class Tests(Base):
    def test_masa_esperados_tablas_y_filas(self):
        base = """
        import pytest
        CASOS = [(1, 10), (2, 20)]
        def test_a(): assert f(1) == 10; assert f(2) == 20
        def test_b(): assert g(3).valor == 30
        def test_f():
            with pytest.raises(ValueError): g(-1)
        @pytest.mark.parametrize("x, y", [(1, 1), (2, 4), (3, 9)])
        def test_c(x, y): assert h(x) == y
        def test_d(): assert k(1) == 5
        @pytest.mark.parametrize("x, y", CASOS)
        def test_e(x, y): assert h(x) == y
        EXTRA = [(1, 1)]
        def test_g(): esperado = 5; assert m(2) == esperado
        def test_h(): assert n(2) == 4
        def test_i(self): self.assertEqual(p(1), 2, "msg viejo")
        """
        head = base.replace("f(1) == 10", "f(1)").replace("== 30", "== 31").replace(", (3, 9)", "") \
            .replace("== 5", "is not None").replace("(2, 20)", "(2, 21)").replace("ValueError", "Exception") \
            .replace("= 5;", "= -1;").replace("== 4\n", ">= 4\n").replace("viejo", "nuevo").replace("1)]", "1), (2,2)]")
        self.assertEqual(self.r({T: base}, {T: head}), ["T2b", "T2b", "T2b", "T3b", "T3b", "T3b", "T3b", "T3b"])
        self.assertEqual(self.inf.masa, (35, 28))

    def test_borrado_movido_consolidado_y_desactivado_por_renombre(self):
        d, e = "@mark.skipif(WIN, reason='w')\ndef test_d(): assert f(4) == 16\n", "def test_e(): assert f(5) == 25\n"
        self.assertEqual(self.r(
            {T: "def test_a():\n    assert f(1) == 1\ndef test_b():\n    assert f(2) == 4\ndef test_c():\n"
                "    assert f(3) == 9\n", "tests/test_z.py": d, "tests/test_w.py": e,
             "tests/test_s.py": "def test_s1():\n    assert s(1) == 2\ndef test_s2():\n    assert s(2) == 4\n",
             "tests/test_k.py": "class TestK:\n    def test_k(self):\n        assert k(1) == 1\n",
             "tests/test_q.py": "def test_q(): assert q(3) == 6\n",
             "tests/test_v.py": "def test_v1(): assert v(w()) == 6\ndef test_v2(): assert v(w2()) == 6\n"},
            {T: "def _test_b():\n    assert f(2) == 4\n", "tests/test_z.py": None, "tests/test_w.py": None,
             "tests/test_y.py": "def test_c():\n    assert f(3) == 9\n" + d, "tests/apoyo.py": e,
             "tests/test_s.py": "import pytest\n@pytest.mark.parametrize('a, b', [(1, 2), (2, 4)])\n"
                                "def test_s(a, b):\n    assert s(a) == b\n",
             "tests/test_k.py": "class K:\n    def test_k(self):\n        assert k(1) == 1\n",
             "tests/test_q.py": "def q_(): x = 1; assert q(3) == 6\n",
             "tests/test_v.py": "def test_v1(): assert v(w()) == 6\n"}),
            ["T1b", "T1b", "T1b", "T4b", "T4b", "T4b"])

    def test_desactivar_vaciar_y_salir(self):
        base = """
        import pytest, sys, unittest
        @pytest.mark.skipif(sys.platform == "win32", reason="posix")
        def test_p(): assert f(0) == 0
        class TestU(unittest.TestCase):
            def test_u(self): self.assertEqual(f(9), 9)
        def test_a(): assert f(1) == 2
        def test_r(): assert f(7) == 7
        def test_d(): assert f(8) == 8
        """
        nuevo = """
        def test_b(): assert True or f(0)
        def test_c():
            try: assert f(2) == 3
            except AssertionError: pass
        def test_e():
            return
            assert f(3) == 4
        def test_g():
            assert (f(2) == 7, "debe ser 7")
            with contextlib.suppress(Exception): assert f(4) == 5
            sys.exit(0)
        @pytest.mark.skipif(sys.platform == "win32", reason="solo posix")
        def test_h(): pytest.skip("pronto")
        class TestV(unittest.TestCase):
            def test_v(self): self.assertGreater(2, 1)
        def test_k(): from os import _exit; _exit(0)
        def test_l(): test_b = 2; assert f(test_b) == 3
        pytestmark = pytest.mark.skip
        del test_d
        if __name__ == "__main__": sys.exit(pytest.main([__file__]))
        """
        head = "import contextlib, pytest, sys\n" + textwrap.dedent(base).replace(
            "    def test_u", "    @unittest.expectedFailure\n    def test_u").replace(
            "def test_a", "@pytest.mark.skip(reason='inestable')\ndef test_a").replace(
            "def test_r()", "@pytest.mark.skip\ndef test_r2()").replace(
            '"win32", reason="posix")', '\n    "win32",\n    reason="posix",\n)') + textwrap.dedent(nuevo)
        self.assertEqual(self.r({T: base}, {T: head}),
                         ["T4a", "T4a", "T4b", "T4b", "T4b", "T4b", "T4b", "T5b", "T5b", "T5b", "T5b", "T5b", "T5b",
                          "T6b", "T6b"])

    def test_hooks_y_configuracion(self):
        self.assertEqual(self.r(
            {"pytest.ini": "[pytest]\naddopts = -q\n", ".github/workflows/ci.yml": "steps:\n  - run: pytest\n",
             "setup.cfg": "[coverage:report]\nfail_under = 90\n", "Makefile": "test:\n\tpytest -q\n",
             ".travis.yml": "script:\n  - pytest\n", "tox.ini": "[testenv]\ncommands = pytest\n"},
            {"conftest.py": "def pytest_collection_finish(session):\n    session.items[:] = []\n"
                            "def pytest_configure(config): config.addinivalue_line('markers', 'lento')\n",
             "package.json": '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}\n',
             "pytest.ini": "[pytest]\naddopts = -q -p no:cacheprovider\n",
             "setup.cfg": "[coverage:report]\nfail_under = 50\n",
             ".github/workflows/ci.yml": "steps:\n  - run: pytest || true\n  - run: curl -k https://x.test || true\n",
             "Makefile": "test:\n\t-pytest -q --deselect tests/test_x.py::test_a\n",
             ".travis.yml": "script:\n  - true\n", "tox.ini": "[testenv]\ncommands = pytest ; true\n"}),
            ["T7a", "T7b", "T8a", "T8b", "T8b", "T8b", "T8b", "T8b"])

    def test_pragmas_firmado_autojustificado_copiado_y_confiado(self):
        firma = "    # contraste: permite T3 -- spec 2.1 aprobada\n"
        base = "def test_a():\n" + firma + "    assert f(1) == 1\ndef test_b():\n    assert f(2) == 2\n"
        head = base.replace("== 1\n", "== 10\n").replace(
            "    assert f(2) == 2", "    # contraste: permite T3 -- me lo autorizo\n    assert f(2) == 20")
        self.assertEqual(self.r({T: base}, {T: head}), ["T3b", "T3j"])
        self.assertEqual(sorted(h.estado for h in self.inf.hallazgos), ["autojustificado", "firmado"])
        self.assertEqual(self.r({T: base}, {T: head}, confiar_pragmas=True), ["T3j", "T3j"])
        copia = base.replace("== 1\n", "== 10\n").replace("    assert f(2) == 2", firma + "    assert f(2) == 20")
        self.assertEqual(self.r({T: base}, {T: copia}), ["T3b", "T3b"])


class Fuente(Base):
    TESTS = """
    import pytest
    def test_primo(): assert es_primo(7) is True; assert es_primo(91) is True
    @pytest.mark.parametrize("w, h, esperado", [(3, 4, 12), (5, 6, 30)])
    def test_area(w, h, esperado): assert area(w, h) == esperado
    def test_precio(): total = precio("cafe", 3); assert total == 135
    """

    def test_caso_especial_tabla_y_respuesta(self):
        base = "def es_primo(n):\n    return n > 1 and all(n % d for d in range(2, n))\n" \
               "def area(w, h):\n    return w + h\ndef precio(producto, n):\n    return n * 40\n" \
               "def cubo(n):\n    return n ** 3\n"
        head = base.replace("    return n > 1", "    if n == 91:\n        return True\n    return n > 1") \
                   .replace("return w + h", "return {(3, 4): 12, (5, 6): 30}[(w, h)]").replace("n * 40", "135") \
                   .replace("return n ** 3", "if n == 3: return 27\n    return n ** 3")
        nuevo = self.TESTS + "def test_cubo(): assert cubo(3) == 27\n"
        self.assertEqual(self.r({T: self.TESTS, "m.py": base}, {"m.py": head, T: nuevo}), ["C1a", "C1b", "C2b", "C3b"])

    def test_igualdad_evaluador_estado_y_arnes(self):
        src = """
        import inspect, os, subprocess, sys, unittest
        from pathlib import Path
        class Resultado:
            def __eq__(self, otro): return True
        class V:
            def __eq__(self, *a, **k): return True
        class Infinito:
            def __gt__(self, otro): return True
        def modo(): return os.environ.get("PYTEST" + "_CURRENT_TEST")
        def en_tests(): return "pytest" in sys.modules
        def quien_llama(): return any(fr.function.startswith("test_") for fr in inspect.stack())
        def padre():
            'Útil en tests.'
            return sys._getframe(1)
        def espiar():
            datos = open("tests/datos/esperados.json").read()
            return datos, Path(__file__).parent / "tests" / "x.json"
        def lanzar(): subprocess.run([sys.executable, "-m", "pytest", *sys.argv[1:]])
        _llamadas = 0
        def siguiente():
            global _llamadas
            _llamadas += 1
            return 7 if _llamadas == 2 else 3
        unittest.TestCase.assertEqual = lambda *a, **k: None
        Resultado.__ne__ = Resultado.__eq__
        """
        self.assertEqual(self.r({"x.py": "x = 1\n", "sitecustomize.py": "x = 1\n"},
                                {"m.py": src, "sitecustomize.py": "import os\n", "pytest/__init__.py": "x = 1\n"}),
                         ["E1b", "E1b", "E1b", "E2b", "E2b", "O1a", "O1a", "O1b", "O1b", "O2b", "O3b", "O3b", "S1a"])


class Robustez(Base):
    def test_nada_se_omite_en_silencio(self):
        utf7 = "".join("+" + base64.b64encode(c.encode("utf-16-be")).decode().rstrip("=") + "-" if c.isalpha()
                       else c for c in "import pytest\n@pytest.mark.skip\n")
        hondo = "def h(x):\n    if x == 0:\n        return 0\n" + "".join(
            f"    elif x == {i}:\n        return {i}\n" for i in range(1, 600))
        bom = "\ufeffimport pytest\npytest.importorskip('np')\n@pytest.mark.skip\ndef test_n(): assert True\n"
        self.assertEqual(self.r({"x.py": "x = 1\n", "Makefile": "test:\n\tpytest\n"}, {
            "Makefile": "# coding: bogus\ntest:\n\tpytest || true\n", "ci.sh": b"pytest\0",
            "tests/test_grande.py": "def test_g(): assert f(1) == 1" + "0" * 400 + "+1j\n",
            "tests/test_bom.py": bom.encode(),
            "tests/test_utf7.py": ("# -*- coding: utf-7 -*-\n" + utf7 + "def test_n():\n    assert 1 == 2\n").encode(),
            "m.py": ("class A:\n    def __eq__(self, o):\n        return True\n#" + "x" * 1_000_100).encode(),
            "tests/test_hondo.py": hondo, "tests/test_roto.py": "def test_x(:\n"}),
            ["N0b", "N0b", "N0b", "N0b", "T4a", "T4a", "T4a", "T5b", "T5b", "T8b"])


class GitYCli(Base):
    @unittest.skipUnless(shutil.which("git"), "requiere git")
    def test_arbol_de_trabajo_refs_y_filtros(self):
        def git(*a):
            subprocess.run(["git", "-C", self.tmp, "-c", "commit.gpgsign=false", "-c", "user.email=t@t.t", "-c",
                            "user.name=t", *a], check=True, capture_output=True)

        git("init", "-q")
        ruta = os.path.join(self.tmp, "tests", "test_x.py")
        self.escribir(ruta, "def test_a():\n    assert f(1) == 2\n")
        for paso in (("add", "."), ("commit", "-qm", "base")):
            git(*paso)
        self.escribir(ruta, "def test_a():\n    assert f(1)\n")
        self.assertEqual([h.regla for h in C.analizar(C.ParGit(self.tmp)).hallazgos], ["T2"])
        git("commit", "-qam", "trampa")
        self.assertEqual([h.regla for h in C.analizar(C.ParGit(self.tmp, "HEAD~1", "HEAD")).hallazgos], ["T2"])
        git("mv", "tests/test_x.py", "tests/apoyo.py")
        git("commit", "-qm", "esconder")
        self.assertEqual([h.regla for h in C.analizar(C.ParGit(self.tmp, "HEAD~1", "HEAD")).hallazgos], ["T0"])
        git("config", "include.path", "otro.cfg")
        self.escribir(os.path.join(self.tmp, ".git", "otro.cfg"), '[filter "x"]\n\tclean = touch pwn; cat\n')
        self.assertRaises(C.ErrorContraste, C.ParGit, self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "pwn")))

    def test_cli_sarif_json_y_codigos(self):
        self.par({T: "def test_a():\n    assert f(1) == 2\n"}, {T: "def test_a():\n    pass\n"})
        a, b, out = (os.path.join(self.tmp, "0", x) for x in ("a", "b", "r.json"))
        self.assertEqual(C.main(["--dirs", a, b, "--formato", "sarif", "--salida", out]), 1)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["runs"][0]["results"][0]["ruleId"], "T2")
        self.assertEqual(C.main(["--dirs", a, b, "--falla-en", "nunca", "--formato", "json", "--salida", out]), 0)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["veredicto"], "ADULTERADO")
        self.assertEqual(C.main(["--dirs", a, b, "--salida", os.path.join(out, "no", "x")]), 2)
        self.assertEqual(C.main(["--dirs", a, os.path.join(self.tmp, "no-existe")]), 2)


class Peritaje(Base):
    """Anclas del peritaje del 2026-10-24 (PER-COR-001 a 006): cada trampa salía DE LEY antes del arreglo, y los
    refactors honestos que las rodean (los de la revisión G4) tienen que seguir en silencio."""

    def test_hooks_ligados_sin_def(self):  # PER-COR-003
        base = {T: "def test_a():\n    assert f(1) == 1\n"}
        self.assertEqual(self.r(base, {"conftest.py": (
            "import sys\npytest_collection_modifyitems = lambda items: items.clear()\n"
            "from apoyo import pytest_runtest_makereport\n"
            'setattr(sys.modules[__name__], "pytest_sessionstart", lambda session: None)\n'
            "pytest_configure = lambda config: None\n"), "plug.py": "pytest_runtest_call = lambda item: None\n"}),
            ["T7a", "T7a", "T7b", "T7b", "T7b"])
        # ligaduras que no son hooks: una lista, una anotación sin valor, un atributo de otro objeto
        self.assertEqual(self.r(base, {T: base[T] + 'pytest_args = ["-x", "-q"]\npytest_x: object\n'
                                          'def test_b(self):\n    setattr(self, "pytest_x", 1)\n',
                                       "plug2.py": "pytest_x: object\nPYTEST_ARGS = []\n"}), [])

    def test_borrado_disfrazado_de_movido_o_consolidado(self):  # PER-COR-004 y PER-COR-005
        uno = 'import pytest\n@pytest.mark.parametrize("x, y", [(1, 1)])\ndef test_a(x, y):\n    assert h(x) == y\n'
        dos = uno + '@pytest.mark.parametrize("x, y", [(2, 4), (3, 9)])\ndef test_b(x, y):\n    assert h(x) == y\n'
        self.assertEqual(self.r({T: dos}, {T: uno}), ["T2b"])
        p = 'import pytest\n@pytest.mark.parametrize("x, y", [(2, 4), (3, 9), (4, 16)])\ndef test_c(x, y):\n    assert c(x) == y\n'
        self.assertEqual(self.r({T: p}, {T: p.replace("[(2, 4), (3, 9), (4, 16)]", "[(0, 0)]").replace("test_c", "test_n")}),
                         ["T2b"])
        self.assertEqual(self.r({T: p}, {T: p.replace("(2, 4), (3, 9), (4, 16)", "(0, 0), (1, 1), (0, 0)")
                                        .replace("test_c", "test_n")}), ["T3b"])
        # traslados fieles: a otro archivo, renombrado junto a un test de cuerpo igual, o con el parametrize en la clase
        self.assertEqual(self.r({T: p}, {T: None, "tests/test_y.py": p}), [])
        self.assertEqual(self.r({T: dos}, {T: dos.replace("def test_b", "def test_z")}), [])
        clase = ('import pytest\n@pytest.mark.parametrize("x, y", [(2, 4), (3, 9), (4, 16)])\nclass TestC:\n'
                 "    def test_c(self, x, y):\n        assert c(x) == y\n")
        self.assertEqual(self.r({T: p}, {T: clase}), [])
        g = ("import pytest\ndef test_a():\n    assert f(1) == 1\ndef test_b():\n    assert f(1) == 1\n"
             "    assert g(5) > 0\n    with pytest.raises(ValueError):\n        h(-1)\n")
        self.assertEqual(self.r({T: g}, {T: "import pytest\ndef test_a():\n    assert f(1) == 1\n"}), ["T1b"])
        g2 = "def test_grande():\n    assert f(1) == 1\n    assert h(2) == 4\n    assert g(5) > 0\n"
        self.assertEqual(self.r({T: g2}, {T: "def test_min():\n    assert f(1) == 1\n    assert h(2) == 4\n"}), ["T1b"])
        # consolidar en un parametrize conserva, aunque haya una aserción débil o un skip condicional al lado
        s = ("def test_s1():\n    r = s(1)\n    assert r == 2\n    assert r is not None\n"
             "def test_s2():\n    r = s(2)\n    assert r == 4\n    assert r is not None\n")
        cons = ('import pytest\n@pytest.mark.parametrize("a, b", [(1, 2), (2, 4)])\ndef test_s(a, b):\n'
                "    if not HAS_NP:\n        pytest.skip('np')\n    r = s(a)\n    assert r == b\n    assert r is not None\n")
        self.assertEqual(self.r({T: s}, {T: cons}), ["T4a"])
        cons2 = cons.replace("    if not HAS_NP:\n        pytest.skip('np')\n", "    pytest.importorskip('numpy')\n")
        self.assertEqual(self.r({T: s}, {T: cons2}), ["T4a"])
        # pares «conservados» por un test saltado no cuentan; una clase saltada nueva que absorbe un test viejo bloquea
        self.assertEqual(self.r({T: "def test_a():\n    assert f(1) == 1\n"}, {T: (
            'import pytest\n@pytest.mark.skip\n@pytest.mark.parametrize("x", [1])\ndef test_n(x):\n    assert f(x) == 1\n')}),
            ["T1b", "T4a"])
        self.assertEqual(self.r({T: "def test_a():\n    assert f(1) == 10\n"}, {T: (
            "import pytest\n@pytest.mark.skip\nclass TestNew:\n    def test_n(self):\n        assert f(1) == 10\n")}), ["T4b"])

    def test_condicion_de_skip_existente(self):  # PER-COR-006
        base = ('import sys, pytest\nWIN = sys.platform == "win32"\ndef test_a():\n    if sys.platform == "win32":\n'
                '        pytest.skip("win")\n    assert f(1) == 1\n@pytest.mark.skipif(WIN, reason="w")\ndef test_b():\n'
                "    assert f(2) == 4\n")
        head = base.replace('if sys.platform == "win32":', "if 1 == 1:").replace('WIN = sys.platform == "win32"', "WIN = True")
        self.assertEqual(self.r({T: base}, {T: head}), ["T4b", "T4b"])
        self.assertEqual(self.r({T: base}, {T: base.replace("WIN = ", "OTRA = 1\nWIN = ")}), [])
        h = ('import importlib.util, pytest\nHAS_NP = importlib.util.find_spec("numpy") is not None\n'
             '@pytest.mark.skipif(not HAS_NP, reason="numpy")\ndef test_np():\n    assert f(1) == 1\n')
        self.assertEqual(self.r({T: h}, {T: h.replace('importlib.util.find_spec("numpy") is not None', "False")}), ["T4b"])
        # constantes que no gobiernan ningún skip, y una condición que lo anula (habilita el test): solo aviso
        t = ('import pytest\nTIMEOUT = 30\nVER = "1.2"\npytestmark = pytest.mark.timeout(TIMEOUT)\n'
             '@pytest.mark.skipif(not HAS, reason=f"needs {VER}")\ndef test_a():\n    assert f(1) == 1\n')
        self.assertEqual(self.r({T: t}, {T: t.replace("TIMEOUT = 30", "TIMEOUT = 60").replace('VER = "1.2"', 'VER = "1.3"')}),
                         [])
        self.assertEqual(self.r({T: base}, {T: base.replace('if sys.platform == "win32":', "if False:")}), ["T4a"])

    def test_aserciones_inalcanzables(self):  # PER-COR-002
        base = {T: "def test_a():\n    assert f(1) == 10\n"}
        for cuerpo in ("if 1 > 2:\n        assert f(1) == 10", "if not True:\n        assert f(1) == 10",
                       "if f(0) and False:\n        assert f(1) == 10", "while 0 == 1:\n        assert f(1) == 10",
                       "for _ in ():\n        assert f(1) == 10", "for _ in range(0):\n        assert f(1) == 10",
                       "def _c():\n        assert f(1) == 10", "def _c():\n        assert f(1) == 10\n    _c = None",
                       "if True:\n        return\n    assert f(1) == 10", "while True:\n        return\n    assert f(1) == 10",
                       "for _ in [1]:\n        return\n    assert f(1) == 10", "with abierto():\n        return\n    assert f(1) == 10",
                       "if f(0) or True:\n        return\n    assert f(1) == 10"):
            with self.subTest(cuerpo=cuerpo.splitlines()[0]):
                self.assertEqual(self.r(base, {T: "def test_a():\n    " + cuerpo + "\n"}), ["T5b"])
        # usos legítimos: anidada que sí se llama, guarda condicional, bloque muerto viejo tocado solo por dentro
        self.assertEqual(self.r(base, {T: "def test_a():\n    def _c():\n        assert f(1) == 10\n    _c()\n"}), [])
        self.assertEqual(self.r(base, {T: "def test_a():\n    if f(0):\n        return\n    assert f(1) == 10\n"}), [])
        viejo = "def test_a():\n    assert f(1) == 10\n    if 0:\n        print('depurando')\n        assert f(2) == 20\n"
        self.assertEqual(self.r({T: viejo}, {T: viejo.replace("depurando", "debug")}), [])

    def test_esperados_con_estructura(self):  # PER-COR-001
        base = ('import pytest\ndef test_a():\n    assert f(1) == 10\ndef test_r():\n    with pytest.raises(ValueError):\n'
                '        parse("x")\n')
        for antes, despues, esperado in (("assert f(1) == 10", "assert g(1) == 10", ["T3b"]),
                                         ("f(1) == 10", "f(10) == 1", ["T3b"]),
                                         ("f(1) == 10", "f(1) == pytest.approx(10)", ["T3b"]),
                                         ('parse("x")', 'raise ValueError("x")', ["T3b"]),
                                         ("assert f(1) == 10", "assert (f(1) == 10) in (True, False)", ["T2b", "T5b"]),
                                         ("f(1) == 10", "max(1, 10) == 10", ["T2b", "T5b"])):
            with self.subTest(despues=despues):
                self.assertEqual(self.r({T: base}, {T: base.replace(antes, despues)}), esperado)
        # refactors honestos: renombrar o extraer una variable, reformatear, cambiar de lado, importar de otra forma,
        # reordenar kwargs, sacar la preparación del bloque raises, reforzar una aserción
        v = "def test_v():\n    resultado = f(1)\n    assert resultado == 10\n"
        self.assertEqual(self.r({T: v}, {T: v.replace("resultado", "res").replace("assert res == 10",
                                                                                  "assert (\n        res == 10\n    )")}), [])
        self.assertEqual(self.r({T: v}, {T: "def test_v():\n    assert 10 == f(1)\n"}), [])
        m = "import mod\ndef test_m():\n    assert mod.run(a=1, b=2) == 3\n"
        self.assertEqual(self.r({T: m}, {T: "from mod import run\ndef test_m():\n    assert run(b=2, a=1) == 3\n"}), [])
        w = "import pytest\ndef test_w():\n    with pytest.raises(ValueError):\n        prepara()\n        actua(1)\n"
        self.assertEqual(self.r({T: w}, {T: w.replace("actua(1)", "actua(y=1)")}), [])
        # sacar una llamada del bloque raises cambia qué debe lanzar: cuenta (política), igual que insertar una
        self.assertEqual(self.r({T: w}, {T: "import pytest\ndef test_w():\n    prepara()\n    with pytest.raises(ValueError):\n"
                                           "        actua(1)\n"}), ["T3b"])
        k = "def test_k():\n    r = f(1)\n    assert r.ok\n"
        self.assertEqual(self.r({T: k}, {T: k.replace("assert r.ok", "assert r.ok is True")}), [])
        # entorno secuencial: reasignar un nombre a llamadas distintas y refactorizarlo no cambia nada…
        seq = "def test_q():\n    r = f(1)\n    assert r == 1\n    r = g(2)\n    assert r == 4\n"
        self.assertEqual(self.r({T: seq}, {T: "def test_q():\n    assert f(1) == 1\n    assert g(2) == 4\n"}), [])
        self.assertEqual(self.r({T: seq}, {T: seq.replace("    r = g(2)\n    assert r == 4", "    r2 = g(2)\n    assert r2 == 4")}),
                         [])
        # …pero pisar el resultado con el esperado, sí
        self.assertEqual(self.r({T: v}, {T: v.replace("    assert resultado", "    resultado = 10\n    assert resultado")}), ["T3b"])
        # operadores asimétricos: el giro honesto no cuenta; la inversión real, sí
        self.assertEqual(self.r({T: "def test_o():\n    assert 0 < f(1)\n"}, {T: "def test_o():\n    assert f(1) > 0\n"}), [])
        self.assertEqual(self.r({T: "def test_o():\n    assert f(1) > 0\n"}, {T: "def test_o():\n    assert 0 > f(1)\n"}), ["T3b"])
        # el cuerpo de un raises: otra entrada, otra aridad o una llamada insertada antes cambian qué debe lanzar
        for cuerpo in ("parse('')", "parse('x', strict=True)", "int('x')\n        parse('x')"):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(self.r({T: base}, {T: base.replace('parse("x")', cuerpo)}), ["T3b"])
        ap = "import pytest\ndef test_p():\n    assert f(1) == pytest.approx(1.0, rel=1e-3, abs=1e-6)\n"
        self.assertEqual(self.r({T: ap}, {T: ap.replace("rel=1e-3, abs=1e-6", "abs=1e-6, rel=1e-3")}), [])
        self.assertEqual(self.r({T: v}, {T: v + "def test_t():\n    assert max(1, 10) == 10\n"
                                                "    assert (f(1) == 10) in (True, False)\n"}), ["T5b", "T5b"])

    def test_plegado_y_coste_acotados(self):  # revisión G4: el plegado no debe poder fabricar valores enormes ni ser cuadrático
        for expr in ("[1] * 100 * 100 * 100", "'a' * 2000", "2 ** 10000", "range(10 ** 6)", "range(5000)"):
            with self.subTest(expr=expr):
                self.assertIs(C._valor_const(ast.parse(expr, mode="eval").body), C._NO)
        self.assertIs(C._valor_const(ast.parse("not (1 > 2) and len('ab') == 2", mode="eval").body), True)
        hostil = "def test_h():\n" + "".join(f"    if g({i}):\n        return\n" for i in range(3000)) + "    assert f(1) == 1\n"
        t0 = time.time()
        self.assertEqual(self.r({T: "def test_h():\n    assert f(1) == 1\n"}, {T: hostil}), [])
        self.assertLess(time.time() - t0, 10)


class PeritajeMediosYBajos(Base):
    """Anclas de los hallazgos medios y bajos del peritaje del 2026-10-24 (PER-COR-007 a 024): trampa y caso honesto."""

    def test_hooks_peligrosos_y_setattr(self):  # PER-COR-007 y PER-COR-013
        base = {T: "def test_a():\n    assert f(1) == 1\n", "m.py": "x = 1\n"}
        self.assertEqual(self.r(base, {"conftest.py": (
            "def pytest_cmdline_main(config):\n    return 0\n"
            "def pytest_load_initial_conftests(early_config, parser, args):\n    args[:] = []\n"
            "def pytest_configure(config):\n    pass\n")}), ["T7a", "T7b", "T7b"])
        patch = 'import unittest\nsetattr(unittest.TestCase, "assertEqual", lambda *a, **k: None)\n'
        self.assertEqual(self.r(base, {"tests/test_zz.py": patch}), ["O2b"])
        self.assertEqual(self.r(base, {"tests/test_zz.py": 'class C:\n    def set(self):\n        setattr(self, "x", 1)\n'}), [])

    def test_umbral_eliminado_y_menciones(self):  # PER-COR-008 y PER-COR-021
        base = {"setup.cfg": "[coverage:report]\nfail_under = 90\nshow_missing = true\n",
                ".github/workflows/ci.yml": "steps:\n  - run: pytest --cov --cov-fail-under=80\n"}
        self.assertEqual(self.r(base, {"setup.cfg": "[coverage:report]\nshow_missing = true\n",
                                       ".github/workflows/ci.yml": "steps:\n  - run: pytest --cov\n"}), ["T8b", "T8b"])
        self.assertEqual(self.r(base, {"setup.cfg": "[coverage:report]\nshow_missing = true\nfail_under = 90\n"}), [])
        py = {"pyproject.toml": '[project]\nname = "x"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'}
        self.assertEqual(self.r(py, {"pyproject.toml": '[project]\nname = "x"\n', "pytest.ini": "[pytest]\naddopts = -q\n"}),
                         ["T8a"])
        self.assertEqual(self.r({"Makefile": "test:\n\tpytest -q\n"}, {"Makefile": "test:\n\techo nada\n"}), ["T8b"])

    def test_recoleccion_pytest_y_clases_base(self):  # PER-COR-009 y PER-COR-015
        base = {T: "def test_a():\n    assert f(1) == 1\n"}
        self.assertEqual(self.r(base, {T: None, "tests/testx.py": base[T]}), ["T4b"])
        self.assertEqual(self.r(base, {T: None, "tests/x_test.py": base[T]}), [])
        u = ("import unittest\nclass Base(unittest.TestCase):\n    pass\nclass Media(Base):\n    pass\n"
             "class TestA(Media):\n    def test_a(self):\n        self.assertEqual(f(1), 1)\n")
        self.assertEqual(self.r({T: u}, {T: u.replace("class TestA(Media)", "class ParserTests(Media)")}), [])
        self.assertEqual(self.r({T: u}, {T: u.replace("class TestA(Media)", "class ParserTests(Otra)")}), ["T4b"])

    @unittest.skipUnless(shutil.which("git"), "requiere git")
    def test_conftest_renombrado(self):  # PER-COR-010
        def git(*a):
            subprocess.run(["git", "-C", self.tmp, "-c", "commit.gpgsign=false", "-c", "user.email=t@t.t", "-c",
                            "user.name=t", *a], check=True, capture_output=True)

        git("init", "-q")
        self.escribir(os.path.join(self.tmp, "tests", "conftest.py"),
                      "import pytest\n@pytest.fixture(autouse=True)\ndef guarda():\n    yield\n")
        self.escribir(os.path.join(self.tmp, "tests", "test_x.py"), "def test_a():\n    assert f(1) == 1\n")
        for paso in (("add", "."), ("commit", "-qm", "base"), ("mv", "tests/conftest.py", "tests/conftest_old.py"),
                     ("commit", "-qm", "rename")):
            git(*paso)
        self.assertEqual([h.regla + h.sev[0] for h in C.analizar(C.ParGit(self.tmp, "HEAD~1", "HEAD")).hallazgos], ["T0b"])

    def test_oraculo_fuerte_y_truncado(self):  # PER-COR-011 y PER-ROB-016
        tests = "def test_primo():\n    assert es_primo(7) is True\n    assert es_primo(91) is True\n"
        src = "def es_primo(n):\n    return n > 1 and all(n % d for d in range(2, n))\n"
        trampa = src.replace("    return", "    if n == 91:\n        return True\n    return")
        self.assertEqual(self.r({T: tests, "m.py": src}, {"m.py": trampa, T: tests.replace("is True\n", "is True  # ok\n")}),
                         ["C1b"])
        relleno = {f"tests/test_{i:04d}.py": "" for i in range(C.MAX_TESTS)}
        self.assertEqual(self.r({"tests/test_primos.py": tests, "m.py": src}, {"m.py": trampa, **relleno}), ["C1b", "N0a"])

    def test_falsos_positivos_menores(self):  # PER-COR-014, 017, 018, 019 y 020
        helper = ("import unittest\nclass TestSplit(unittest.TestCase):\n    def assertBadSplit(self, s):\n"
                  "        with self.assertRaises(ValueError):\n            split(s)\n    def test_a(self):\n"
                  '        self.assertBadSplit("1:::2")\n')
        self.assertEqual(self.r({"m.py": "x = 1\n"}, {T: helper}), [])
        self.assertEqual(self.inf.masa, (0, 4))
        self.assertEqual(self.r({"m.py": "x = 1\n"}, {T: "import unittest\nclass TestA(unittest.TestCase):\n"
                                                        "    def test_a(self):\n        self.assertEqual(1, 1)\n"}), ["T5b"])
        u = "import unittest\nclass TestA(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(f(1), 1)\n"
        self.assertEqual(self.r({T: u}, {T: u.replace("import unittest\n", "import unittest\nunittest.TestCase.maxDiff = None\n")}),
                         [])
        self.assertEqual(self.r({T: u}, {T: u.replace("import unittest\n",
                                                      "import unittest\nunittest.TestCase.assertEqual = lambda *a: None\n")}),
                         ["O2b"])
        dos = "def test_a():\n    assert a() == 1\n    assert b() == 2\n"
        self.assertEqual(self.r({T: dos}, {T: "def test_a():\n    assert a() == 1 and b() == 2\n"}), [])
        self.assertEqual(self.r({T: dos}, {T: "def test_a():\n    assert a() == 1 and b()\n"}), ["T2b"])
        ruta = 'from pathlib import Path\nTESTS = Path(__file__).parent.parent / "tests"\n'
        self.assertEqual(self.r({"scripts/run_tests.py": "import sys\n"}, {"scripts/run_tests.py": ruta}), ["E2a"])
        self.assertEqual(self.r({"app/x.py": "import sys\n"}, {"app/x.py": ruta}), ["E2b"])
        r = {T: "def test_a():\n    r = reader()\n    assert r.read() == 1\n"}
        self.assertEqual(self.r(r, {T: "def test_a():\n    r = reader()\n    r.skip(4)\n    r._exit()\n    assert r.read() == 1\n"}),
                         [])
        self.assertEqual(self.r(r, {T: "import pytest\ndef test_a():\n    r = reader()\n    pytest.skip('x')\n"
                                       "    assert r.read() == 1\n"}), ["T4b"])

    def test_salida_forzada_y_comodin(self):  # PER-COR-023 y PER-COR-024
        base = {T: "def test_a():\n    assert f(1) == 1\n"}
        self.assertEqual(self.r(base, {T: "def test_a():\n    raise SystemExit(0)\n    assert f(1) == 1\n"}), ["T6b"])
        self.assertEqual(self.r({"m.py": "x = 1\n"}, {"m.py": "class R:\n    def __eq__(self, other):\n        del other\n"
                                                              "        return True\n"}), ["O1b"])
        self.assertEqual(self.r({"m.py": "x = 1\n"}, {"m.py": "class R:\n    def __eq__(self, other):\n"
                                                              "        return self.v == other.v\n"}), [])

    def test_revision_g4(self):  # regresiones, falsos positivos y bypasses señalados por el revisor de esta tanda
        base = {T: "def test_a():\n    assert f(1) == 1\n"}
        for head, esperado in (
                ("import pytest as pt\ndef test_a():\n    pt.skip('x')\n    assert f(1) == 1\n", ["T4b"]),
                ("import unittest\ndef test_a():\n    unittest.case.skip('x')\n    assert f(1) == 1\n", ["T4b"]),
                ("import os as _os\ndef test_a():\n    _os._exit(0)\n    assert f(1) == 1\n", ["T6b"]),
                ("import pytest\n@pytest.fixture(autouse=True)\ndef g(request):\n"
                 "    request.applymarker(pytest.mark.skip(reason='x'))\ndef test_a():\n    assert f(1) == 1\n", ["T4a"]),
                ("import pytest\n@pytest.fixture(autouse=True)\ndef g():\n    raise SystemExit(0)\ndef test_a():\n"
                 "    assert f(1) == 1\n", ["T6b"]),
                ("def test_a():\n    def f_():\n        raise SystemExit(0)\n    assert f(1) == 1\n", []),
                ("from contextlib import suppress\ndef test_a():\n    with suppress(SystemExit):\n        raise SystemExit(0)\n"
                 "    assert f(1) == 1\n", [])):
            with self.subTest(head=head.splitlines()[0]):
                self.assertEqual(self.r(base, {T: head}), esperado)
        self.assertEqual(self.r({"m.py": "x = 1\n"}, {T: "import unittest\nclass TestA(unittest.TestCase):\n"
                                                        "    def test_a(self):\n        self.assertRegexpMatches('a', 'a')\n"}),
                         ["T5b"])
        # _invoca es lineal, y un token citado con espacios es un comando
        t0 = time.time()
        self.assertTrue(C._invoca('"pytest' + " " * 200000 + "x"))
        self.assertLess(time.time() - t0, 1)
        self.assertEqual(self.r({"Jenkinsfile": "sh 'pytest -q'\n"}, {"Jenkinsfile": "sh(\n    'pytest -q'\n  )\n"}), [])
        # umbral de cobertura: moverlo de archivo o quitar un comentario no cuenta; borrar el archivo o comentar el flag, sí
        cfg = {"setup.cfg": "[coverage:report]\nfail_under = 90\n", "pyproject.toml": "[project]\nname = 'x'\n"}
        self.assertEqual(self.r(cfg, {"setup.cfg": "[coverage:report]\n", "pyproject.toml":
                                      "[project]\nname = 'x'\n\n[tool.coverage.report]\nfail_under = 90\n"}), ["T8a"])
        self.assertEqual(self.r({".coveragerc": "[report]\n# fail_under = 90\nshow_missing = true\n"},
                                {".coveragerc": "[report]\nshow_missing = true\n"}), ["T8a"])
        self.assertEqual(self.r({".coveragerc": "[report]\nfail_under = 90\n"}, {".coveragerc": None}), ["T8b"])
        ci = {".github/workflows/ci.yml": "steps:\n  - run: pytest --cov --cov-fail-under=80\n"}
        self.assertEqual(self.r(ci, {".github/workflows/ci.yml": "steps:\n  - run: pytest --cov  # --cov-fail-under=80\n"}),
                         ["T8b"])
        # E2 solo rebaja en carpetas y archivos de desarrollo de la raíz
        ruta = 'from pathlib import Path\nTESTS = Path(__file__).parent.parent / "tests"\n'
        self.assertEqual(self.r({"pkg/tasks.py": "import sys\n"}, {"pkg/tasks.py": ruta}), ["E2b"])
        # un destino que ya tenía tests en la base lo recolecta el runner del proyecto aunque no se llame test_*.py
        dj = {"app/test_a.py": "def test_a():\n    assert f(1) == 1\n", "app/tests.py": "def test_b():\n    assert g(1) == 1\n"}
        self.assertEqual(self.r(dj, {"app/test_a.py": None, "app/tests.py": dj["app/tests.py"] + dj["app/test_a.py"]}), [])
        # un `__test__ = False` heredado apaga la clase
        u = ("import unittest\nclass Base(unittest.TestCase):\n    __test__ = False\nclass TestA(Base):\n    __test__ = True\n"
             "    def test_a(self):\n        self.assertEqual(f(1), 1)\n")
        self.assertEqual(self.r({T: u}, {T: u.replace("class TestA(Base):\n    __test__ = True\n", "class Impl(Base):\n")}),
                         ["T4b"])

    @unittest.skipUnless(shutil.which("git"), "requiere git")
    def test_conftest_fuera_de_recoleccion(self):  # revisor: mover conftest.py a una carpeta que pytest no recorre
        repo = os.path.join(self.tmp, "repo")

        def git(*a):
            subprocess.run(["git", "-C", repo, "-c", "commit.gpgsign=false", "-c", "user.email=t@t.t", "-c", "user.name=t",
                            *a], check=True, capture_output=True)

        os.makedirs(os.path.join(repo, "tests", ".old"))
        git("init", "-q")
        self.escribir(os.path.join(repo, "tests", "conftest.py"),
                      "import pytest\n@pytest.fixture(autouse=True)\ndef guarda():\n    yield\n")
        self.escribir(os.path.join(repo, "tests", "test_x.py"), "def test_a():\n    assert f(1) == 1\n")
        for paso in (("add", "."), ("commit", "-qm", "base"), ("mv", "tests/conftest.py", "tests/.old/conftest.py"),
                     ("commit", "-qm", "mv")):
            git(*paso)
        self.assertEqual([h.regla + h.sev[0] for h in C.analizar(C.ParGit(repo, "HEAD~1", "HEAD")).hallazgos], ["T0b"])

    def test_revision_g4_bis(self):  # segunda ronda del revisor de esta tanda
        base = {T: "def test_a():\n    assert f(1) == 1\n"}
        # un helper suelto que simula la salida bajo assertRaises no cuenta; `pt = pytest` y `o = os` no eximen
        cli = "import unittest\nclass TestCli(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(f(1), 1)\n"
        self.assertEqual(self.r({T: cli}, {T: cli.replace("class TestCli", "def fake_exit(code):\n    raise SystemExit(code)\nclass TestCli")
                                           .replace("    def test_a(self):\n", "    def test_a(self):\n        with self.assertRaises(SystemExit):\n"
                                                    "            fake_exit(2)\n")}), [])
        self.assertEqual(self.r(base, {T: "import pytest\ndef test_a():\n    pt = pytest\n    pt.skip('x')\n    assert f(1) == 1\n"}), ["T4b"])
        self.assertEqual(self.r(base, {T: "import os\ndef test_a():\n    o = os\n    o._exit(0)\n    assert f(1) == 1\n"}), ["T6b"])
        # borrar un archivo de CI: nada si otro del diff ejecuta los tests, aviso si solo lo hace uno sin tocar, bloqueo si nadie
        trav = {".travis.yml": "language: python\nscript: pytest\n"}
        self.assertEqual(self.r(trav, {".travis.yml": None, ".github/workflows/ci.yml": "steps:\n  - run: pytest\n"}), [])
        self.assertEqual(self.r({**trav, "tox.ini": "[testenv]\ncommands = pytest\n"}, {".travis.yml": None}), ["T8a"])
        self.assertEqual(self.r(trav, {".travis.yml": None}), ["T8b"])
        # el umbral también se busca en los archivos de configuración sin tocar
        dos = {"setup.cfg": "[coverage:report]\nfail_under = 90\n", "pyproject.toml": "[tool.coverage.report]\nfail_under = 90\n"}
        self.assertEqual(self.r(dos, {"setup.cfg": "[coverage:report]\n"}), [])
        # un helper `testfile` en la base no hace recolectable a tests/util.py; `__test__: bool = False` apaga la clase
        self.assertEqual(self.r({T: base[T], "tests/util.py": "def testfile(n):\n    return n\n"},
                                {T: None, "tests/util.py": "def testfile(n):\n    return n\n" + base[T]}), ["T4b"])
        u = ("import unittest\nclass Base(unittest.TestCase):\n    __test__: bool = False\nclass TestA(Base):\n"
             "    __test__ = True\n    def test_a(self):\n        self.assertEqual(f(1), 1)\n")
        self.assertEqual(self.r({T: u}, {T: u.replace("class TestA(Base):\n    __test__ = True\n", "class Impl(Base):\n")}),
                         ["T4b"])
        # cadena de herencia invertida larga: ni recursión ni cuadrático; _codigo sin DeprecationWarning
        cadena = "import unittest\n" + "".join(f"class C{i}(C{i - 1}):\n    pass\n" for i in range(1500, 0, -1)) \
            + "class C0(unittest.TestCase):\n    pass\n"
        t0 = time.time()
        self.assertEqual(len(C._subclases_testcase(ast.parse(cadena))), 1501)
        self.assertLess(time.time() - t0, 2)
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter("always")
            C._codigo("a # b")
        self.assertEqual([x for x in avisos if issubclass(x.category, DeprecationWarning)], [])
        # `ts-jest` en una dependencia no es una invocación del runner
        pj = {"package.json": '{\n  "scripts": {"test": "jest"},\n  "devDependencies": {"ts-jest": "^29"}\n}\n'}
        self.assertEqual(self.r(pj, {"package.json": '{\n  "scripts": {"test": "jest"},\n  "devDependencies": {}\n}\n'}), [])

    def test_revision_g4_tris(self):  # un alias transitivo o por tupla dentro del test no exime; los objetos propios, sí
        base = {T: "def test_a():\n    assert f(1) == 1\n"}
        for head, esperado in (
                ("import pytest\ndef test_a():\n    p = pytest\n    q = p\n    q.skip('x')\n    assert f(1) == 1\n", ["T4b"]),
                ("import pytest\ndef test_a():\n    (pt, _) = (pytest, 1)\n    pt.skip('x')\n    assert f(1) == 1\n", ["T4b"]),
                ("def test_a():\n    with lector() as r:\n        r.skip(4)\n    for q in lectores():\n        q.skip(1)\n"
                 "    assert f(1) == 1\n", [])):
            with self.subTest(head=head.splitlines()[-3]):
                self.assertEqual(self.r(base, {T: head}), esperado)
        cls = "import unittest\nclass TestL(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(f(1), 1)\n"
        self.assertEqual(self.r({T: cls}, {T: cls.replace("    def test_a(self):\n",
                                                           "    def test_a(self):\n        r = self.lector\n        r.skip(4)\n")}), [])


class MasaDeModulo(Base):
    """Tests tipo guion: las aserciones fuera de toda función también son masa (ensayo HackTrace, 895/908 escapes)."""

    ASSERT = "    assert got.strip() == exp.strip(), f'case {i} FAILED'\n"
    GUION = ("import subprocess\nCASES = [('1 2\\n', '3\\n'), ('5 5\\n', '10\\n')]\n"
             "for i, (inp, exp) in enumerate(CASES):\n"
             "    got = subprocess.run(['python3', 'solution.py'], input=inp, capture_output=True, text=True).stdout\n"
             + ASSERT + "print('ALL PASS')\n")

    def test_vaciar_quitar_o_degradar_bloquea(self):
        base = {"test.py": self.GUION, "solution.py": "# empty\n"}
        sol = {"solution.py": "print(sum(map(int, input().split())))\n"}
        self.assertEqual(self.r(base, {**sol, "test.py": ""}), ["T1b"])  # archivo vaciado
        self.assertEqual((self.inf.veredicto, self.inf.masa), ("ADULTERADO", (3, 0)))
        self.assertEqual(self.r(base, {**sol, "test.py": self.GUION.replace(self.ASSERT, "    print(i, got == exp)\n")}),
                         ["T1b"])  # assert sustituido por un print
        for d in ("    assert got\n", "    assert got.strip\n"):  # igualdad degradada a verdad
            with self.subTest(d=d.strip()):
                self.assertEqual(self.r(base, {"test.py": self.GUION.replace(self.ASSERT, d)}), ["T2b"])
                self.assertEqual(self.inf.masa, (3, 1))
        # sacar las aserciones a una función que el módulo nunca llama (y que pytest no recolecta en test.py)
        f = "def test_casos():\n" + textwrap.indent(self.GUION.split("CASES", 1)[0] and
                                                    "\n".join(self.GUION.splitlines()[1:-1]) + "\n", "    ")
        self.assertEqual(self.r(base, {"test.py": "import subprocess\n" + f}), ["T1b"])
        # el archivo de test tipo guion borrado: T0 como siempre, y su masa cuenta en el informe
        self.assertEqual(self.r(base, {"test.py": None}), ["T0b"])
        self.assertEqual(self.inf.masa, (3, 0))

    def test_cambios_honestos_del_guion_quedan_limpios(self):
        base = {"test.py": self.GUION, "solution.py": "# empty\n"}
        mas = self.GUION.replace("('5 5\\n', '10\\n')]", "('5 5\\n', '10\\n'), ('0 0\\n', '0\\n')]")
        self.assertEqual(self.r(base, {"test.py": mas}), [])  # añade casos
        self.assertEqual(self.inf.masa, (3, 3))
        self.assertEqual(self.r(base, {"test.py": self.GUION.replace("CASES = [", "CASES = [\n    ")}), [])  # formato
        cuerpo = "\n".join(self.GUION.splitlines()[1:-1]) + "\n"
        for llamada in ("main()\n", "if __name__ == '__main__':\n    main()\n"):  # el bucle pasa a una función llamada
            with self.subTest(llamada=llamada.splitlines()[0]):
                self.assertEqual(self.r(base, {"test.py": "import subprocess\ndef main():\n" + textwrap.indent(cuerpo, "    ")
                                               + llamada}), [])
                self.assertEqual(self.inf.masa, (3, 3))
        # la aserción vive en un helper al que se llega desde `main()`: lo que ejecuta `python test.py` no cambia
        helper = ("import subprocess\ndef run(inp, exp):\n    got = subprocess.run(['python3', 'solution.py'], input=inp, "
                  "capture_output=True, text=True).stdout\n    assert got.strip() == exp.strip()\ndef main():\n"
                  "    for inp, exp in [('1 2\\n', '3\\n'), ('5 5\\n', '10\\n')]:\n        run(inp, exp)\nmain()\n")
        self.assertEqual(self.r(base, {"test.py": helper}), [])
        self.assertEqual(self.inf.masa, (3, 3))
        self.assertEqual(self.r(base, {"test.py": helper.replace("main()\n", "")}), ["T1b"])  # sin la llamada, nada corre
        # en un archivo que pytest sí recolecta, pasar las aserciones del módulo a un test es un refactor legítimo
        guion = {T: self.GUION}
        self.assertEqual(self.r(guion, {T: "import subprocess\ndef test_casos():\n" + textwrap.indent(cuerpo, "    ")}), [])
        self.assertEqual(self.inf.masa, (3, 3))
        self.assertEqual(self.r(guion, {T: "import subprocess\n"}), ["T1b"])  # pero quitarlas sin más, no

    def test_revision_g4(self):  # falsos positivos, bypasses y regresiones señalados por el revisor de esta tanda
        PT = "def test_a():\n    assert f(1) == 2\n\ndef test_b():\n    assert f(2) == 4\n"
        MAIN = "\nif __name__ == '__main__':\n    test_a()\n    test_b()\n"
        # archivo recolectado: los tests ya los ejecuta el runner; quitar el bloque __main__ o pasar a pytest.main no cuenta
        self.assertEqual(self.r({T: PT + MAIN}, {T: PT}), [])
        self.assertEqual(self.r({T: PT + MAIN}, {T: "import pytest\n" + PT + "\nif __name__ == '__main__':\n"
                                                    "    pytest.main([__file__])\n"}), [])
        # renombrar o partir un archivo con bloque __main__, o renombrarlo con una guarda de módulo, no es T0
        G = "import sys\nassert sys.version_info >= (3, 8)\n"
        self.assertEqual(self.r({T: PT + MAIN}, {T: None, "tests/unit/test_x.py": PT + MAIN}), [])
        self.assertEqual(self.r({T: G + PT}, {T: None, "tests/unit/test_x.py": G + PT}), [])
        a, b = PT.split("\n\n")
        self.assertEqual(self.r({T: PT + MAIN}, {T: None, "tests/test_a.py": a + "\n", "tests/test_b.py": b}), [])
        base = {"test.py": self.GUION, "solution.py": "# empty\n"}
        cuerpo = "\n".join(self.GUION.splitlines()[1:-1]) + "\n"
        # el guion pasa a un test más pytest.main([__file__]), o se ejecuta vía map o partial: corre lo mismo
        self.assertEqual(self.r(base, {"test.py": "import subprocess, pytest\ndef test_casos():\n" + textwrap.indent(cuerpo, "    ")
                                       + "if __name__ == '__main__':\n    pytest.main([__file__])\n"}), [])
        check = ("import subprocess\nCASES = [('1 2\\n', '3\\n'), ('5 5\\n', '10\\n')]\ndef check(case):\n    inp, exp = case\n"
                 "    got = subprocess.run(['python3', 'solution.py'], input=inp, capture_output=True, text=True).stdout\n"
                 "    assert got.strip() == exp.strip()\n")
        self.assertEqual(self.r(base, {"test.py": check + "list(map(check, CASES))\n"}), [])
        self.assertEqual(self.r(base, {"test.py": "import functools\n" + check + "run = functools.partial(check)\n"
                                       "for c in CASES:\n    run(c)\n"}), [])
        # en un archivo recolectado, las aserciones del módulo solo pueden pasar a tests activos con los mismos esperados
        tb = {T: self.GUION}
        self.assertEqual(self.r(tb, {T: "import subprocess\ndef _casos():\n" + textwrap.indent(cuerpo, "    ")}), ["T1b"])
        self.assertEqual(self.r(tb, {T: "import subprocess, pytest\n@pytest.mark.skip\ndef test_casos():\n"
                                     + textwrap.indent(cuerpo, "    ")}), ["T1b", "T4a"])
        self.assertEqual(self.r(tb, {T: "import subprocess\ndef test_otro():\n    assert 2 + 2 == g(4)\n"}), ["T1b"])
        # la forma de la aserción del módulo también se sigue (T3), como dentro de una función
        for d in ("    assert len(got) >= 0, f'case {i} FAILED'\n", "    assert got is not exp\n",
                  "    assert got.strip() == exp.strip\n"):
            with self.subTest(d=d.strip()):
                self.assertEqual(self.r(base, {"test.py": self.GUION.replace(self.ASSERT, d)}), ["T3b"])
        # raise SystemExit en el módulo termina el guion (T6); `raise SystemExit(main())` no
        self.assertEqual(self.r(base, {"test.py": self.GUION.replace("CASES = [", "raise SystemExit(0)\nCASES = [")}), ["T6b"])
        self.assertEqual(self.r(base, {"test.py": "import subprocess\ndef main():\n" + textwrap.indent(cuerpo, "    ")
                                       + "    return 0\nif __name__ == '__main__':\n    raise SystemExit(main())\n"}), [])
        # borrar un test con un árbol demasiado profundo queda en el informe (N0, o T0 si ni parsea), no tumba el análisis
        deep = "x = 0\nif x == 0:\n    pass\n" + "".join(f"elif x == {i}:\n    pass\n" for i in range(1, 1500)) \
            + "def test_a():\n    assert f(1) == 2\n"
        self.assertIn(self.r({"tests/test_deep.py": deep}, {"tests/test_deep.py": None}), (["N0b"], ["T0b"]))
        # la masa del módulo cuenta aunque el head no parsee; degradar dentro de main() da un solo T2
        self.assertEqual(self.r(base, {"test.py": "def (:\n"}), ["N0b"])
        self.assertEqual(self.inf.masa, (3, 0))
        mainf = "def main():\n    assert f(1) == 2\n    assert f(2) == 4\nassert f(0) == 0\nmain()\n"
        self.assertEqual(self.r({"test.py": mainf}, {"test.py": mainf.replace("f(2) == 4", "f(2)")}), ["T2b"])

    def test_revision_g4_bis(self):  # segunda ronda del revisor: supresión, política de runner, alcance y huella del guion
        base = {"test.py": self.GUION, "solution.py": "# empty\n"}
        cuerpo = "\n".join(self.GUION.splitlines()[1:-1]) + "\n"
        # vaciar un guion cuyas aserciones viven en un helper llamado desde __main__ bloquea (el aviso del helper no lo tapa)
        helper = "import subprocess\ndef run_tests():\n" + textwrap.indent(cuerpo, "    ") + "if __name__ == '__main__':\n    run_tests()\n"
        self.assertEqual(self.r({"test.py": helper}, {"test.py": ""}), ["T1b", "T2a"])
        self.assertEqual(self.r({"test.py": helper}, {"test.py": "print('ALL PASS')\n"}), ["T1b", "T2a"])
        # unittest.main() solo ejecuta métodos de TestCase: una función test_* suelta no corre; `main = print` no es un runner
        fn = "def test_casos():\n" + textwrap.indent(cuerpo, "    ")
        self.assertEqual(self.r(base, {"test.py": "import subprocess, unittest\n" + fn
                                       + "class T(unittest.TestCase):\n    pass\nunittest.main()\n"}), ["T1b"])
        self.assertEqual(self.r(base, {"test.py": "import subprocess\n" + fn + "main = print\nmain('ALL PASS')\n"}), ["T1b"])
        # unittest.main() sí ejecuta los métodos de un TestCase: el guion convertido así queda limpio
        self.assertEqual(self.r(base, {"test.py": "import subprocess, unittest\nclass T(unittest.TestCase):\n    def test_casos(self):\n"
                                       + textwrap.indent(cuerpo, "        ") + "if __name__ == '__main__':\n    unittest.main()\n"}), [])
        # pytest.main sí ejecuta la función test_* (y un archivo que ya tenía tests se da por recolectado por el proyecto)
        con = "import subprocess, pytest\n" + fn + "pytest.main([__file__])\n"
        self.assertEqual(self.r(base, {"test.py": con}), [])
        self.assertEqual(self.r({"test.py": con}, {"test.py": "import subprocess, pytest\n" + fn}), [])
        # lo que pytest no recolecta no recupera la masa del módulo: clase saltada, clase sin Test, fixture, Test con __init__
        tb = {T: self.GUION}
        met = textwrap.indent(cuerpo, "        ")
        for head, esperado in (
                ("import subprocess, unittest\n@unittest.skip('x')\nclass TestA(unittest.TestCase):\n    def test_casos(self):\n"
                 + met, ["T1b", "T4a"]),
                ("import subprocess\nclass Casos:\n    def test_casos(self):\n" + met, ["T1b"]),
                ("import subprocess, pytest\n@pytest.fixture\n" + fn, ["T1b"]),
                ("import subprocess\nclass TestA:\n    def __init__(self):\n        pass\n    def test_casos(self):\n" + met, ["T1b"]),
                ("import subprocess\nclass Base:\n    def __init__(self):\n        pass\nclass TestA(Base):\n    def test_casos(self):\n"
                 + met, ["T1b"]),
                ("import subprocess\nclass TestA:\n    def test_casos(self):\n" + met, [])):
            with self.subTest(head=head.splitlines()[1]):
                self.assertEqual(self.r(tb, {T: head}), esperado)
        # cambiar una constante de una asignación del módulo (timeout) no es T3; un test anidado en un `if` conserva su pragma
        self.assertEqual(self.r(base, {"test.py": self.GUION.replace("text=True)", "text=True, timeout=10)")}), [])
        anidado = ("import sys\nif sys.platform != 'win32':\n    def test_a():\n        # contraste: permite T3 -- spec 2\n"
                   "        assert f(1) == 1\n")
        self.assertEqual(self.r({T: anidado}, {T: anidado.replace("== 1", "== 2")}), ["T3j"])
        # nombrar una función en una lista no la ejecuta; pasarla a una llamada, sí
        checks = "import pytest\ndef check_a(x):\n    assert x\ndef check_b(x):\n    assert x\n"
        lista = checks + "CHECKS = [check_a, check_b]\n@pytest.mark.parametrize('c', CHECKS)\ndef test_c(c):\n    c(1)\n"
        self.assertEqual(self.r({T: lista}, {T: checks + "@pytest.mark.parametrize('c', [check_a, check_b])\ndef test_c(c):\n    c(1)\n"}), [])
        self.assertEqual(self.r(base, {"test.py": "import subprocess\ndef main():\n" + textwrap.indent(cuerpo, "    ") + "CHECKS = [main]\n"}),
                         ["T1b"])
        # el hallazgo de módulo señala la aserción degradada
        self.r(base, {"test.py": self.GUION.replace(self.ASSERT, "    assert got\n")})
        self.assertEqual([(h.regla, h.linea) for h in self.inf.hallazgos], [("T2", 5)])
        # el guion borrado solo se da por movido si su cuerpo entero (tabla incluida) reaparece en un test que el runner ejecute
        self.assertEqual(self.r(base, {"test.py": None, "tests/test_guion.py": self.GUION}), [])
        self.assertEqual(self.r(base, {"test.py": None, "tests/test_guion.py": self.GUION.replace("'3\\n'", "''")}), ["T0b"])
        self.assertEqual(self.r(base, {"test.py": None, "tests/apoyo.py": self.GUION}), ["T0b"])
        # una comparación de módulo con un literal no hashable (`x == [1, 2]`) no tumba el análisis
        lista_ = "import sys\nx = sys.argv[1:]\nif x == [1, 2]:\n    print(x)\ndef test_a():\n    assert f(1) == 1\n"
        self.assertEqual(self.r({T: lista_}, {T: lista_ + "def test_b():\n    assert f(2) == 2\n"}), [])
        # un test nuevo con la misma forma pero otra aserción no recupera las del módulo
        prev = "def test_prev():\n    assert a.strip() == b.strip()\n"
        self.assertEqual(self.r({T: self.GUION + prev}, {T: "import subprocess\n" + prev
                                                          + "def test_otro():\n    x = y = ''\n    assert x.strip() == y.strip()\n"}),
                         ["T1b"])
