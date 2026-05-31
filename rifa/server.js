const express = require('express');
const { Pool } = require('pg');
const path = require('path');

const app = express();

const RIFA_PASSWORD = 'MV-Rifa-2026';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }, // Azure PostgreSQL requiere SSL
});

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Health check
app.get('/health', (_req, res) => res.json({ status: 'ok' }));

// Autenticación — verifica contraseña y devuelve token de sesión
app.post('/api/auth', (req, res) => {
  const { password } = req.body || {};
  if (password === RIFA_PASSWORD) {
    // El token de sesión ES la contraseña (simple, stateless)
    return res.json({ token: RIFA_PASSWORD });
  }
  res.status(401).json({ error: 'Contraseña incorrecta' });
});

// Middleware: rutas protegidas requieren Authorization: Bearer <token>
function requireAuth(req, res, next) {
  const auth = req.headers['authorization'] || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  if (token !== RIFA_PASSWORD) {
    return res.status(401).json({ error: 'No autorizado' });
  }
  next();
}

// Todos los participantes (para la animación del tambor)
app.get('/api/participantes', requireAuth, async (_req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT nombre, codigo_vip
       FROM clientes
       WHERE tipo_cliente = 3
         AND codigo_vip IS NOT NULL
       ORDER BY nombre`
    );
    res.json(rows);
  } catch (err) {
    console.error('[DB ERROR]', err.message);
    res.status(500).json({ error: 'Error consultando participantes' });
  }
});

// Ganador aleatorio (selección server-side con RANDOM())
app.get('/api/sorteo', requireAuth, async (_req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT nombre, codigo_vip
       FROM clientes
       WHERE tipo_cliente = 3
         AND codigo_vip IS NOT NULL
       ORDER BY RANDOM()
       LIMIT 1`
    );
    if (!rows.length) {
      return res.status(404).json({ error: 'Sin participantes' });
    }
    res.json(rows[0]);
  } catch (err) {
    console.error('[DB ERROR]', err.message);
    res.status(500).json({ error: 'Error realizando sorteo' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`[Rifa] Servidor corriendo en http://localhost:${PORT}`));
