# Pruebas PA-05 a PA-08 (Sprint 2) - ejecutar con: python pruebas_sprint2.py
import os
import sqlite3
import tempfile
import unittest
import app as miapp

# ids de los usuarios semilla
AGENTE1, AGENTE2, AGENTE3_INACTIVO, SOLICITANTE1 = 3, 4, 5, 1


class Base(unittest.TestCase):
    def setUp(self):
        self.fd, self.ruta = tempfile.mkstemp(suffix=".db")
        miapp.app.config["DB"] = self.ruta
        miapp.app.config["TESTING"] = True
        miapp.init_db()
        self.c = miapp.app.test_client()

    def tearDown(self):
        os.close(self.fd)
        os.remove(self.ruta)

    def entrar(self, usuario):
        self.c.get("/logout")
        self.c.post("/login", data={"usuario": usuario, "clave": "Clave123*"})

    def crear(self, usuario="solicitante1", titulo="Falla impresora"):
        self.entrar(usuario)
        self.c.post("/solicitudes/nueva",
                    data={"titulo": titulo, "descripcion": "No imprime", "categoria": "Hardware"})

    def asignar(self, sid, aid):
        self.entrar("coord1")
        return self.c.post("/solicitudes/%d/asignar" % sid, data={"agente_id": aid})

    def estado(self, sid, usuario, nuevo):
        self.entrar(usuario)
        return self.c.post("/solicitudes/%d/estado" % sid, data={"estado": nuevo})

    def pagina(self, sid):
        return self.c.get("/solicitudes/%d" % sid).data.decode()


class PruebasSprint2(Base):
    # PA-05: asignación (HU05)
    def test_pa05_asignar(self):
        self.crear()
        self.asignar(1, AGENTE3_INACTIVO)       # inactivo: no debe asignar
        self.assertNotIn("Asignada", self.pagina(1))
        self.asignar(1, SOLICITANTE1)           # no es agente
        self.assertNotIn("Asignada", self.pagina(1))
        self.asignar(1, AGENTE1)
        p = self.pagina(1)
        self.assertIn("Asignada", p)
        self.assertIn("asignación", p)          # queda en el historial
        self.entrar("agente1")
        self.assertIn("Se te asignó la solicitud #1", self.c.get("/inicio").data.decode())
        r = self.c.post("/solicitudes/1/asignar", data={"agente_id": AGENTE2})
        self.assertEqual(r.status_code, 403)    # el agente no asigna

    # PA-06: comentarios (HU06)
    def test_pa06_comentarios(self):
        self.crear()
        self.asignar(1, AGENTE1)
        self.entrar("agente1")
        self.c.post("/solicitudes/1/comentar", data={"texto": "   "})
        self.assertNotIn("(trabajo)", self.pagina(1))
        self.c.post("/solicitudes/1/comentar", data={"texto": "Revisando el equipo"})
        self.assertIn("Revisando el equipo", self.pagina(1))
        self.entrar("solicitante1")             # visible para el solicitante
        self.assertIn("Revisando el equipo", self.pagina(1))
        self.entrar("agente2")                  # agente no asignado
        self.assertEqual(self.c.get("/solicitudes/1").status_code, 404)
        # no hay forma de editar: ni ruta ni base de datos
        self.assertEqual(self.c.post("/comentarios/1", data={"texto": "x"}).status_code, 404)
        db = sqlite3.connect(self.ruta)
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("UPDATE comentarios SET texto = 'cambiado' WHERE id = 1")
        db.close()

    # PA-07: cambios de estado (HU07)
    def test_pa07_estados(self):
        self.crear()
        self.asignar(1, AGENTE1)
        self.estado(1, "agente1", "Resuelta")   # salto inválido
        self.assertNotIn("Resuelta", self.pagina(1).split("Historial")[0].split("<b>Estado:</b>")[1][:20])
        self.estado(1, "agente1", "En atención")
        self.estado(1, "agente1", "Resuelta")
        p = self.pagina(1)
        self.assertIn("Resuelta", p)
        self.assertIn("En atención", p)         # historial completo
        self.estado(1, "agente2", "En atención")  # otro agente no puede
        self.assertEqual(self.c.post("/solicitudes/1/estado", data={"estado": "En atención"}).status_code, 404)

    # PA-08: confirmar o reabrir (HU08)
    def test_pa08_confirmar_reabrir(self):
        self.crear()
        self.asignar(1, AGENTE1)
        self.entrar("solicitante1")             # aún no está Resuelta
        self.c.post("/solicitudes/1/confirmar")
        self.assertNotIn("Cerrada", self.pagina(1).split("Historial")[0])
        self.estado(1, "agente1", "En atención")
        self.estado(1, "agente1", "Resuelta")
        self.entrar("solicitante1")
        self.c.post("/solicitudes/1/reabrir", data={"motivo": ""})   # sin motivo
        self.assertNotIn("Reabierta", self.pagina(1).split("Historial")[0])
        self.c.post("/solicitudes/1/reabrir", data={"motivo": "Sigue fallando"})
        p = self.pagina(1)
        self.assertIn("Reabierta", p)
        self.assertIn("Sigue fallando", p)
        self.estado(1, "agente1", "En atención")
        self.estado(1, "agente1", "Resuelta")
        self.crear("solicitante2", "Otra")
        self.assertEqual(self.c.post("/solicitudes/1/confirmar").status_code, 404)  # ajena
        self.entrar("solicitante1")
        self.c.post("/solicitudes/1/confirmar")
        self.assertIn("Cerrada", self.pagina(1))


if __name__ == "__main__":
    unittest.main()
