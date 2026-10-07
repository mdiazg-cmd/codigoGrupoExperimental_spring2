# Pruebas PA-01 a PA-04 (Sprint 1) - ejecutar con: python pruebas_sprint1.py
import os
import tempfile
import unittest
import app as miapp


class PruebasSprint1(unittest.TestCase):
    def setUp(self):
        self.fd, self.ruta = tempfile.mkstemp(suffix=".db")
        miapp.app.config["DB"] = self.ruta
        miapp.app.config["TESTING"] = True
        miapp.init_db()
        self.c = miapp.app.test_client()

    def tearDown(self):
        os.close(self.fd)
        os.remove(self.ruta)

    def entrar(self, usuario, clave="Clave123*"):
        return self.c.post("/login", data={"usuario": usuario, "clave": clave})

    def crear(self, titulo="Falla", desc="No enciende", cat="Hardware"):
        return self.c.post("/solicitudes/nueva",
                           data={"titulo": titulo, "descripcion": desc, "categoria": cat})

    # PA-01: autenticación y roles (HU01)
    def test_pa01_login(self):
        r = self.entrar("solicitante1")
        self.assertEqual(r.status_code, 302)
        r1 = self.entrar("noexiste", "xxx")
        r2 = self.entrar("solicitante1", "mala")
        self.assertEqual(r1.status_code, 401)
        self.assertEqual(r1.data, r2.data)  # mismo mensaje: no revela si existe
        self.entrar("solicitante1")
        self.assertEqual(self.c.get("/solicitudes/nueva").status_code, 200)
        self.c.get("/logout")
        self.assertEqual(self.c.get("/inicio").status_code, 302)
        self.entrar("solicitante1")
        self.assertEqual(self.c.post("/solicitudes/1/prioridad", data={"prioridad": "Alta", "justificacion": "urgente", "fecha_objetivo": "2099-01-01"}).status_code, 403)

    # PA-02: crear solicitud (HU02)
    def test_pa02_crear(self):
        self.entrar("solicitante1")
        self.assertEqual(self.crear(titulo="").status_code, 400)
        self.assertEqual(self.crear(desc="").status_code, 400)
        self.assertEqual(self.crear(cat="").status_code, 400)
        self.assertEqual(self.crear().status_code, 302)
        r = self.c.get("/solicitudes/1")
        self.assertIn(b"Nuevo", r.data)
        self.assertIn(b"solicitante1", r.data)

    # PA-03: ver solo las propias (HU03)
    def test_pa03_propias(self):
        self.entrar("solicitante1")
        self.crear(titulo="De uno")
        self.c.get("/logout")
        self.entrar("solicitante2")
        self.crear(titulo="De dos")
        lista = self.c.get("/solicitudes").data
        self.assertIn(b"De dos", lista)
        self.assertNotIn(b"De uno", lista)
        self.assertEqual(self.c.get("/solicitudes/1").status_code, 404)

    # PA-04: priorizar (HU04)
    def test_pa04_priorizar(self):
        self.entrar("solicitante1")
        self.crear()
        r = self.c.post("/solicitudes/1/prioridad", data={"prioridad": "Alta", "justificacion": "urgente", "fecha_objetivo": "2099-01-01"})
        self.assertEqual(r.status_code, 403)  # solicitante no puede
        self.c.get("/logout")
        self.entrar("coord1")
        self.c.post("/solicitudes/1/prioridad", data={"prioridad": "Alta", "justificacion": "urgente", "fecha_objetivo": "2099-01-01"})
        self.assertIn(b"Alta", self.c.get("/solicitudes/1").data)
        self.assertIn(b"Sin definir", self.c.get("/solicitudes/1").data)  # historial
        self.c.post("/solicitudes/1/prioridad", data={"prioridad": "Urgentisima"})
        self.assertNotIn(b"Urgentisima", self.c.get("/solicitudes/1").data)
        for o in ("prioridad", "estado", "fecha"):
            self.assertEqual(self.c.get("/solicitudes?orden=" + o).status_code, 200)


if __name__ == "__main__":
    unittest.main()
