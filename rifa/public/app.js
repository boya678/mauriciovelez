/* ─── Auth ───────────────────────────────────────────────────────────────────── */
let authToken = sessionStorage.getItem('rifa_token') || '';

const lockOverlay = document.getElementById('lock-overlay');
const lockForm    = document.getElementById('lock-form');
const lockInput   = document.getElementById('lock-input');
const lockError   = document.getElementById('lock-error');

async function verificarPassword(password) {
  const res = await fetch('/api/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (res.ok) {
    const data = await res.json();
    return data.token;
  }
  return null;
}

lockForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  lockError.textContent = '';
  const password = lockInput.value.trim();
  const token = await verificarPassword(password).catch(() => null);
  if (token) {
    authToken = token;
    sessionStorage.setItem('rifa_token', token);
    lockOverlay.classList.add('hidden');
    cargarParticipantes();
  } else {
    lockError.textContent = 'Contraseña incorrecta. Intenta de nuevo.';
    lockInput.value = '';
    lockInput.focus();
  }
});

// Si ya hay token en sesión, validar y entrar directo
if (authToken) {
  verificarPassword(authToken).then(token => {
    if (token) {
      lockOverlay.classList.add('hidden');
      cargarParticipantes();
    } else {
      authToken = '';
      sessionStorage.removeItem('rifa_token');
    }
  }).catch(() => {});
}

/* ─── Helper fetch autenticado ───────────────────────────────────────────────── */
function fetchAuth(url) {
  return fetch(url, { headers: { 'Authorization': 'Bearer ' + authToken } });
}

/* ─── Estado global ──────────────────────────────────────────────────────────── */
let participantes = [];
let sorteando = false;

/* ─── Elementos del DOM ──────────────────────────────────────────────────────── */
const drumEl       = document.getElementById('drum-current');
const btnSortear   = document.getElementById('btn-sortear');
const btnLabel     = document.getElementById('btn-label');
const btnNuevo     = document.getElementById('btn-nuevo');
const countNumEl   = document.getElementById('count-num');
const subTextEl    = document.getElementById('sub-text');
const overlayEl    = document.getElementById('winner-overlay');
const winnerNameEl = document.getElementById('winner-name');
const winnerCodeEl = document.getElementById('winner-code');
const confettiEl   = document.getElementById('confetti-layer');

/* ─── Carga inicial ──────────────────────────────────────────────────────────── */
async function cargarParticipantes() {
  try {
    const res = await fetchAuth('/api/participantes');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    participantes = await res.json();

    countNumEl.textContent = participantes.length;

    if (participantes.length > 0) {
      btnLabel.textContent = 'SORTEAR';
      btnSortear.disabled  = false;
    } else {
      btnLabel.textContent = 'Sin participantes';
      subTextEl.textContent = 'No hay clientes tipo 3 con código VIP registrados.';
    }
  } catch {
    btnLabel.textContent   = 'Error de conexión';
    countNumEl.textContent = '0';
    subTextEl.textContent  = 'No se pudo conectar con el servidor.';
  }
}

/* ─── Utilidades ─────────────────────────────────────────────────────────────── */
function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function mostrarNombre(nombre) {
  drumEl.textContent = nombre;
}

/* ─── Confetti ───────────────────────────────────────────────────────────────── */
const CONFETTI_COLORS = ['#f5c518', '#ffe066', '#7c3aed', '#22c55e', '#ef4444', '#60a5fa'];

function lanzarConfetti() {
  confettiEl.innerHTML = '';
  const count = 60;
  for (let i = 0; i < count; i++) {
    const el = document.createElement('div');
    el.className = 'confetti-piece';
    el.style.left     = Math.random() * 100 + '%';
    el.style.background = CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)];
    el.style.animationDuration = (1.5 + Math.random() * 2) + 's';
    el.style.animationDelay   = (Math.random() * 0.8) + 's';
    el.style.transform = `rotate(${Math.random() * 360}deg)`;
    confettiEl.appendChild(el);
  }
  // Limpiar después de que terminen
  setTimeout(() => { confettiEl.innerHTML = ''; }, 3500);
}

/* ─── Sorteo ─────────────────────────────────────────────────────────────────── */
async function realizar() {
  if (sorteando || participantes.length === 0) return;
  sorteando = true;
  btnSortear.disabled = true;
  subTextEl.textContent = '⚡ Sorteando…';

  // 1. Pedir al servidor el ganador (RANDOM() en DB)
  let ganador;
  try {
    const res = await fetchAuth('/api/sorteo');
    if (!res.ok) throw new Error();
    ganador = await res.json();
  } catch {
    // Fallback: seleccionar client-side
    ganador = participantes[Math.floor(Math.random() * participantes.length)];
  }

  // 2. Animar el tambor (5 segundos, arranca rápido y va frenando)
  const pool  = shuffle(participantes);
  const TOTAL = 5000; // ms de animación
  const start = Date.now();
  let idx     = 0;

  function tick() {
    const elapsed  = Date.now() - start;
    const progress = Math.min(elapsed / TOTAL, 1);

    if (progress >= 1) {
      // Mostrar el nombre del ganador en el tambor y revelar
      mostrarNombre(ganador.nombre);
      setTimeout(() => revelarGanador(ganador), 350);
      return;
    }

    // Easing cuadrático: delay crece de 55ms → 420ms
    const eased = progress * progress;
    const delay = 55 + eased * 365;

    idx = (idx + 1) % pool.length;
    mostrarNombre(pool[idx].nombre);

    setTimeout(tick, delay);
  }

  tick();
}

/* ─── Revelar ganador ────────────────────────────────────────────────────────── */
function revelarGanador(ganador) {
  winnerNameEl.textContent = ganador.nombre;
  winnerCodeEl.textContent = ganador.codigo_vip;
  overlayEl.classList.add('visible');
  lanzarConfetti();
}

/* ─── Resetear ───────────────────────────────────────────────────────────────── */
function resetear() {
  overlayEl.classList.remove('visible');
  subTextEl.textContent = 'Haz clic en SORTEAR para seleccionar al ganador';
  mostrarNombre('Presiona SORTEAR');
  btnSortear.disabled = false;
  sorteando = false;
}

/* ─── Eventos ────────────────────────────────────────────────────────────────── */
btnSortear.addEventListener('click', realizar);
btnNuevo.addEventListener('click', resetear);

// Cerrar overlay al hacer clic fuera de la card
overlayEl.addEventListener('click', (e) => {
  if (e.target === overlayEl) resetear();
});

/* ─── Inicializar ────────────────────────────────────────────────────────────── */
// La carga se dispara desde el bloque de auth al validar el token
