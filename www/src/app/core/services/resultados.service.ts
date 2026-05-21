import { Injectable } from '@angular/core';

export interface ResultadoLoteria {
  loteria: string;
  numero: string;
  serie?: string;
  fecha: string;          // ISO
  horario?: string;       // p.ej "Noche"
  region?: string;
  destacada?: boolean;
}

export interface ResultadoChance {
  juego: string;
  numero: string;
  horario: 'Día' | 'Tarde' | 'Noche';
  fecha: string;
}

export interface FrecuenciaNumero {
  numero: string;
  ocurrencias: number;
  ultimaAparicion: string;
  tendencia: 'up' | 'down' | 'flat';
}

export interface AnalisisItem {
  titulo: string;
  resumen: string;
  categoria: string;
  fecha: string;
  minutosLectura: number;
}

const HOY = new Date();
const ISO = (d: Date) => d.toISOString();
const ago = (h: number) => {
  const d = new Date(HOY);
  d.setHours(d.getHours() - h);
  return ISO(d);
};

/** Genera un offset estable a partir de una fecha (yyyy-mm-dd) */
const seedFromDate = (yyyymmdd: string): number => {
  let h = 0;
  for (let i = 0; i < yyyymmdd.length; i++) h = (h * 31 + yyyymmdd.charCodeAt(i)) | 0;
  return Math.abs(h);
};

/** Combina una fecha (yyyy-mm-dd) con una hora local (hh:mm) → ISO */
const isoAt = (yyyymmdd: string, hh: number, mm: number): string => {
  const [y, mo, d] = yyyymmdd.split('-').map(Number);
  const dt = new Date(y, (mo || 1) - 1, d || 1, hh, mm, 0, 0);
  return dt.toISOString();
};

@Injectable({ providedIn: 'root' })
export class ResultadosService {
  /* ─── Resultados por fecha (unificado loterías + chances) ─── */
  getResultadosPorFecha(fechaISO: string): { loterias: ResultadoLoteria[]; chances: ResultadoChance[] } {
    const seed = seedFromDate(fechaISO);
    const rnd = (i: number, mod: number) => ((seed + i * 9301 + 49297) % 233280) % mod;
    const pad4 = (n: number) => String(n).padStart(4, '0');
    const pad3 = (n: number) => String(n).padStart(3, '0');

    const loteriasBase = [
      { loteria: 'Lotería de Bogotá',       region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería de Boyacá',       region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería del Cauca',       region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería de Cundinamarca', region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería del Meta',        region: 'Nacional', h: 20, m: 30 },
      { loteria: 'Lotería de Medellín',     region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería del Valle',       region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería del Quindío',     region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería del Huila',       region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Lotería del Tolima',      region: 'Nacional', h: 22, m: 30 },
      { loteria: 'Baloto',                  region: 'Nacional', h: 23, m: 0  },
      { loteria: 'MiLoto',                  region: 'Nacional', h: 23, m: 0  },
    ];

    const loterias: ResultadoLoteria[] = loteriasBase.map((b, i) => {
      const isBaloto = b.loteria === 'Baloto';
      const isMiLoto = b.loteria === 'MiLoto';
      let numero: string;
      if (isBaloto) {
        const nums = [3, 7, 12, 19, 27].map((x) => pad4(((rnd(i + x, 43) + 1)))).map(s => s.slice(-2));
        const sb = pad4(rnd(i + 99, 16) + 1).slice(-2);
        numero = nums.join('-') + ' + ' + sb;
      } else if (isMiLoto) {
        numero = [2, 5, 8, 14, 17].map((x) => pad4(rnd(i + x, 39) + 1).slice(-2)).join('-');
      } else {
        numero = pad4(rnd(i, 10000));
      }
      return {
        loteria: b.loteria,
        numero,
        serie: isBaloto || isMiLoto ? undefined : pad3(rnd(i + 13, 300) + 1),
        fecha: isoAt(fechaISO, b.h, b.m),
        region: b.region,
        destacada: i < 4,
      };
    });

    const chancesBase: Array<{ juego: string; h: number; m: number; horario: 'Día' | 'Tarde' | 'Noche' }> = [
      { juego: 'Astro Sol',      h: 14, m: 30, horario: 'Día' },
      { juego: 'Paisita Día',    h: 13, m: 0,  horario: 'Día' },
      { juego: 'Caribeña Día',   h: 14, m: 30, horario: 'Día' },
      { juego: 'Pijao de Oro',   h: 14, m: 30, horario: 'Día' },
      { juego: 'Sinuano Día',    h: 14, m: 30, horario: 'Día' },

      { juego: 'Cafeterito',     h: 18, m: 0,  horario: 'Tarde' },
      { juego: 'Paisita Tarde',  h: 18, m: 30, horario: 'Tarde' },
      { juego: 'Dorado Tarde',   h: 16, m: 0,  horario: 'Tarde' },

      { juego: 'Astro Luna',     h: 21, m: 0,  horario: 'Noche' },
      { juego: 'Caribeña Noche', h: 22, m: 30, horario: 'Noche' },
      { juego: 'Sinuano Noche',  h: 22, m: 30, horario: 'Noche' },
      { juego: 'Pijao Noche',    h: 22, m: 30, horario: 'Noche' },
      { juego: 'Dorado Noche',   h: 21, m: 30, horario: 'Noche' },
    ];

    const chances: ResultadoChance[] = chancesBase.map((c, i) => ({
      juego: c.juego,
      numero: pad4(rnd(i + 31, 10000)),
      horario: c.horario,
      fecha: isoAt(fechaISO, c.h, c.m),
    }));

    return { loterias, chances };
  }

  /* ─── Loterías destacadas / recientes ─── */
  getLoteriasDestacadas(): ResultadoLoteria[] {
    return [
      { loteria: 'Lotería de Bogotá',     numero: '4827', serie: '142', fecha: ago(2),  region: 'Nacional', destacada: true },
      { loteria: 'Lotería de Boyacá',     numero: '9134', serie: '087', fecha: ago(4),  region: 'Nacional', destacada: true },
      { loteria: 'Lotería del Cauca',     numero: '3580', serie: '201', fecha: ago(6),  region: 'Nacional' },
      { loteria: 'Lotería de Cundinamarca', numero: '1276', serie: '054', fecha: ago(8), region: 'Nacional' },
      { loteria: 'Lotería del Meta',      numero: '7402', serie: '189', fecha: ago(10), region: 'Nacional' },
      { loteria: 'Lotería de Medellín',   numero: '6018', serie: '073', fecha: ago(12), region: 'Nacional' },
      { loteria: 'Baloto',                numero: '08-14-22-31-43 + 09', fecha: ago(20), region: 'Nacional', destacada: true },
      { loteria: 'MiLoto',                numero: '03-09-17-25-31',      fecha: ago(24), region: 'Nacional' },
    ];
  }

  /* ─── Chances por horario ─── */
  getChancesHoy(): ResultadoChance[] {
    return [
      { juego: 'Astro Sol',     numero: '4123', horario: 'Día',   fecha: ago(8) },
      { juego: 'Paisita Día',   numero: '8765', horario: 'Día',   fecha: ago(9) },
      { juego: 'Caribeña Día',  numero: '3091', horario: 'Día',   fecha: ago(10) },
      { juego: 'Pijao de Oro',  numero: '5274', horario: 'Día',   fecha: ago(11) },

      { juego: 'Cafeterito',    numero: '6938', horario: 'Tarde', fecha: ago(5) },
      { juego: 'Paisita Tarde', numero: '2147', horario: 'Tarde', fecha: ago(6) },
      { juego: 'Sinuano Día',   numero: '7820', horario: 'Tarde', fecha: ago(7) },

      { juego: 'Astro Luna',    numero: '9416', horario: 'Noche', fecha: ago(1) },
      { juego: 'Caribeña Noche',numero: '1058', horario: 'Noche', fecha: ago(2) },
      { juego: 'Sinuano Noche', numero: '4783', horario: 'Noche', fecha: ago(3) },
      { juego: 'Pijao Noche',   numero: '3625', horario: 'Noche', fecha: ago(4) },
    ];
  }

  /* ─── Frecuencias (números calientes / fríos) ─── */
  getFrecuencias(): FrecuenciaNumero[] {
    return [
      { numero: '4827', ocurrencias: 18, ultimaAparicion: ago(2),  tendencia: 'up' },
      { numero: '1276', ocurrencias: 15, ultimaAparicion: ago(8),  tendencia: 'up' },
      { numero: '6018', ocurrencias: 14, ultimaAparicion: ago(12), tendencia: 'flat' },
      { numero: '9134', ocurrencias: 13, ultimaAparicion: ago(4),  tendencia: 'up' },
      { numero: '3580', ocurrencias: 11, ultimaAparicion: ago(6),  tendencia: 'down' },
      { numero: '7402', ocurrencias: 10, ultimaAparicion: ago(10), tendencia: 'flat' },
      { numero: '5274', ocurrencias:  9, ultimaAparicion: ago(11), tendencia: 'down' },
      { numero: '2147', ocurrencias:  8, ultimaAparicion: ago(6),  tendencia: 'down' },
    ];
  }

  /* ─── Estadísticas KPI ─── */
  getKpis() {
    return {
      sorteosHoy: 24,
      loteriasActivas: 16,
      numerosAnalizados: 12480,
      actualizadoHace: '2 min',
    };
  }

  /* ─── Análisis ─── */
  getAnalisis(): AnalisisItem[] {
    return [
      {
        titulo: 'Frecuencia de dígitos en loterías de Colombia',
        resumen: 'Análisis estadístico de los dígitos más recurrentes en los últimos 90 sorteos de las loterías nacionales.',
        categoria: 'Estadística',
        fecha: ago(48),
        minutosLectura: 5,
      },
      {
        titulo: 'Comportamiento histórico del Baloto',
        resumen: 'Estudio sobre los patrones de aparición de combinaciones en los sorteos del Baloto a lo largo del último año.',
        categoria: 'Análisis',
        fecha: ago(96),
        minutosLectura: 7,
      },
      {
        titulo: 'Tendencias semanales del Chance',
        resumen: 'Cómo varían las series de tres y cuatro cifras a lo largo de la semana en los principales juegos de chance.',
        categoria: 'Tendencias',
        fecha: ago(168),
        minutosLectura: 4,
      },
      {
        titulo: 'Metodología de medición de frecuencias',
        resumen: 'Documento técnico sobre el modelo utilizado para clasificar números como calientes, fríos o neutrales.',
        categoria: 'Metodología',
        fecha: ago(240),
        minutosLectura: 6,
      },
    ];
  }
}
