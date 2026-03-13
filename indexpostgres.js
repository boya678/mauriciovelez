const express = require('express');
const cron = require('node-cron');
const { Pool } = require('pg');
const jwt = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const dayjs = require("dayjs");
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const xlsx = require('xlsx');
const nodemailer = require('nodemailer');
const moment = require('moment');

today = moment().format('YYYY-MM-DD');
console.log(today);

const app = express();
app.use(cors());
const PORT = process.env.PORT || 3000;

// --- CONFIG POSTGRES ---
const pool = new Pool({
  user: process.env.PGUSER || "postgres",
  host: process.env.PGHOST || "transferiadb.postgres.database.azure.com",
  database: process.env.PGDATABASE || "numeros",
  password: process.env.PGPASSWORD || "Ardilla1*",
  port: process.env.PGPORT || 5432,
  ssl: true
});

// Funciones helper para queries
async function dbRun(sql, params = []) {
  return pool.query(sql, params);
}
async function dbGet(sql, params = []) {
  const res = await pool.query(sql, params);
  return res.rows[0] || null;
}
async function dbAll(sql, params = []) {
  const res = await pool.query(sql, params);
  return res.rows;
}

// Exportar todas las tablas a SQL
async function exportAllTablesToSQL() {
  const tablesRes = await dbAll(
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
  );
  const tables = tablesRes.map(t => t.tablename);

  let sqlDump = '';

  for (const table of tables) {
    const rows = await dbAll(`SELECT * FROM ${table}`);
    if (rows.length === 0) continue;

    const columns = Object.keys(rows[0]);
    for (const row of rows) {
      const values = columns.map(col => {
        const value = row[col];
        if (value === null || value === undefined) return 'NULL';
        if (typeof value === 'number') return value;
        return `'${value.toString().replace(/'/g, "''")}'`;
      });
      sqlDump += `INSERT INTO ${table} (${columns.join(', ')}) VALUES (${values.join(', ')});\n`;
    }
  }

  const filename = path.join(__dirname, 'backup.sql');
  fs.writeFileSync(filename, sqlDump);
  return filename;
}

// Nodemailer
const transporter = nodemailer.createTransport({
  host: "mail5009.site4now.net",
  port: 465,
  auth: {
    user: 'julian.velez@t-evolvers.com',
    pass: 'Javb2010@',
  },
  secure: true,
  tls: {
    servername: "mail5009.site4now.net"
  }
});

app.use(express.json());

// Función para generar Excel
async function poblarLoterias() {
  try {
    const loterias = await dbAll("SELECT * from loterias");
    let numbers = await dbAll('SELECT * FROM numbers WHERE assigned = false');
    for (loteria of loterias) {
      const selected = numbers[Math.floor(Math.random() * numbers.length)].number;
      const finalNumber = Math.floor(Math.random() * 9).toString() + selected.toString();
      dbRun("update loterias set numero=$2 where nombre=$1", [loteria.nombre, finalNumber])
    }
  } catch (error) {
    console.error('Error al poblar loterias', error);
  }
}

// Función para generar Excel
async function generateExcel() {
  today = moment().format('YYYY-MM-DD');
  const query1 = `
    SELECT 
      u.id AS cedula,
      u.username AS nombre,
      u.phone AS celular,
      nh.number AS numero,
      nh.date AS fecha,
      nh.lotery AS loteria
    FROM numbers_historic nh
    INNER JOIN users u ON nh.id_user = u.id
    ORDER BY nh.date
  `;

  const query2 = `SELECT * FROM usersaux`;

  const query3 = `SELECT * FROM loterias`;

  try {
    const data1 = await dbAll(query1);
    const data2 = await dbAll(query2);
    const data3 = await dbAll(query3);

    const wb = xlsx.utils.book_new();

    const ws1 = xlsx.utils.json_to_sheet(data1.length ? data1 : [{}]);
    xlsx.utils.book_append_sheet(wb, ws1, 'numeros dados');

    const ws3 = xlsx.utils.json_to_sheet(data3.length ? data3 : [{}]);
    xlsx.utils.book_append_sheet(wb, ws3, 'numeros loterias');

    const ws2 = xlsx.utils.json_to_sheet(data2.length ? data2 : [{}]);
    xlsx.utils.book_append_sheet(wb, ws2, 'datos de usuarios');

    const excelFilePath = `${today}.xlsx`;

    // 👇 esta es la forma correcta
    xlsx.writeFile(wb, excelFilePath);

    return excelFilePath;
  } catch (error) {
    console.error('Error al generar el archivo Excel:', error);
  }
}

async function sendEmail(filePath) {
  today = moment().format('YYYY-MM-DD');
  try {
    const mailOptions = {
      from: 'julian.velez@t-evolvers.com',
      to: 'boya678@gmail.com,mauricioveleznumerologo@gmail.com',
      subject: 'informe de numeros y clientes ' + today,
      text: 'Adjunto encontrarás el archivo Excel solicitado.',
      attachments: [
        { path: filePath }
      ],
    };

    const info = await transporter.sendMail(mailOptions);
    console.log('Correo electrónico enviado:', info.response);
  } catch (error) {
    console.error('Error al enviar el correo electrónico:', error);
  }
}

// Función para asignar número
const asignarNumero = async (id, date, lotery) => {
  await dbRun('DELETE FROM numbers_users WHERE id_user = $1 and lotery = $2', [id, lotery]);

  let numbers = await dbAll('SELECT * FROM numbers WHERE assigned = false');
  if (numbers.length === 0) {
    await dbRun('UPDATE numbers SET assigned = false');
    numbers = await dbAll('SELECT * FROM numbers WHERE assigned = false');
  }

  const selected = numbers[Math.floor(Math.random() * numbers.length)].number;
  const finalNumber = Math.floor(Math.random() * 9).toString() + selected.toString();

  await dbRun('UPDATE numbers SET assigned = true WHERE number = $1', [selected]);
  await dbRun('INSERT INTO numbers_users (number, id_user, date, lotery) VALUES ($1, $2, $3, $4)', [finalNumber, id, date, lotery]);
  await dbRun('INSERT INTO numbers_historic (number, id_user, date, lotery) VALUES ($1, $2, $3, $4)', [finalNumber, id, new Date().toISOString().split('T')[0], lotery]);

  return true;
};

// Rutas
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '.', 'index.html'));
});

// Rutas
app.get('/registro', (req, res) => {
  res.sendFile(path.join(__dirname, '.', 'registro.html'));
});

// Rutas
app.get('/consulta', (req, res) => {
  res.sendFile(path.join(__dirname, '.', 'consulta.html'));
});

app.post('/numerologia/search', async (req, res) => {
  const { phone, password } = req.body;
  try {
    if (password == 'victoriosos2025*@') {
      await dbRun('select * from users_enabled', []);
      return res.status(200).json(await dbAll('select * from users_enabled', []));
    } else {
      return res.status(401).json({});
    }
  } catch (error) {
    return res.status(200).json({});
  }

});


app.post('/numerologia/register', async (req, res) => {
  const { phone, password } = req.body;
  try {
    if (password == 'victoriosos2025*@') {
      await dbRun(
        'INSERT INTO users_enabled (phone) VALUES ($1)',
        [phone]
      );
      return res.status(200).json({ resultado: "Registro Exitoso" });
    } else {
      return res.status(401).json({});
    }
  } catch (error) {
    return res.status(200).json({ resultado: "número ya está registrado." });
  }

});

app.post('/numerologia/login', async (req, res) => {
  const { phone, username, lotery } = req.body;

  try {
    try {
      await dbRun(
        'INSERT INTO users (id, phone, username, balance, is_enable) VALUES ($1, $2, $3, $4, $5)',
        [uuid(), phone, username, 0, 1]
      );
    } catch (error) {
      await dbRun('DELETE FROM usersaux WHERE phone=$1 and username=$2', [phone, username]);
      await dbRun('INSERT INTO usersaux (phone, username) VALUES ($1, $2)', [phone, username]);
    }
    //se agrega para que siempre entre
    try {
      await dbRun(
        'INSERT INTO users_enabled (phone) VALUES ($1)',
        [phone]
      );
    } catch (error) {

    }
    const user_enabled = await dbGet('SELECT * FROM users_enabled WHERE phone = $1', [phone]);
    if (!user_enabled) {
      return res.status(404).json({});
    } else if (!user_enabled.date) {
      await dbRun('UPDATE users_enabled set date = $2 WHERE phone = $1 ', [phone, dayjs(new Date()).format("YYYY-MM-DD")])
    }

    const user = await dbGet('SELECT * FROM users WHERE phone = $1', [phone]);
    const id = user.id;

    const today = dayjs(new Date()).add(-5, "h");
    let dategenerated = dayjs();

    try {
      const userNumber = await dbGet('SELECT * FROM numbers_users WHERE id_user = $1 and lotery = $2', [id, lotery]);

      if (!userNumber || dayjs(today.format('YYYY-MM-DD')).diff(userNumber.date, 'day') > 15) {
        await asignarNumero(id, dategenerated.format('YYYY-MM-DD'), lotery);
      }

      const assigned = await dbGet('SELECT * FROM numbers_users WHERE id_user = $1 and lotery = $2', [id, lotery]);
      const lotteries = await dbAll('SELECT * FROM loterias', []);
      res.status(200).json({
        number: String(assigned.number),
        numberMethod: String(assigned.number)[0] + String(assigned.number)[3] + String(assigned.number)[2] + String(assigned.number)[1],
        date: dayjs(assigned.date).format("YYYY-MM-DD"),
        lotteries: lotteries
      });
    } catch (error) {
      console.error(error);
      res.status(500).json({ error: 'Error en el servidor.' });
    }
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Error en el servidor. o numero telefono ya existe' });
  }
});

app.get('/numerologia/export-sql', async (req, res) => {
  try {
    const filePath = await exportAllTablesToSQL();
    res.download(filePath, 'backup.sql');
  } catch (error) {
    console.error('Error al exportar la base de datos:', error);
    res.status(500).json({ error: 'Error al generar el archivo SQL.' });
  }
});

// Cronjob
cron.schedule('0 8 * * *', async () => {
  console.log('⏰ Ejecutando exportación de Excel...');
  const file = await generateExcel();
  await sendEmail(file);
});

cron.schedule('20 8 * * *', async () => {
  console.log('⏰ Ejecutando poblacion de loterias.');
  await poblarLoterias();
});

cron.schedule('10 8 * * *', async () => {
  console.log('Eliminando usuarios.');
  users = await dbAll("SELECT * FROM users_enabled e,users u WHERE date<$1 and e.phone = u.phone", [dayjs(new Date()).add(-3, "d").format('YYYY-MM-DD')])
  for (const user of users) {
    await dbRun('DELETE FROM numbers_users WHERE id_user = $1', [user.id])
    await dbRun('DELETE FROM users_enabled WHERE phone = $1', [user.phone])
  }
  console.log('Eliminacion terminada.');
});

app.listen(PORT, () => {
  console.log(`Servidor en ejecución en http://localhost:${PORT}`);
});
