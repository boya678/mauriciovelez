import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ConferenciaConfig, ConferenciaVipConfig, NumeroRelampagoConfig, RelampagoPersonalizadoConfig, RifaEnumeradaConfig, RifaEnumeradaLote, ServiciosAdminService, TablaNumerologicaConfig, VipConfig } from '../../core/services/servicios-admin.service';

@Component({
  selector: 'app-servicios',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './servicios.component.html',
  styleUrl: './servicios.component.scss',
})
export class ServiciosComponent implements OnInit, OnDestroy {
  loading = signal(false);
  savingRe = signal(false);
  subiendoBaseRe = signal(false);
  cargandoExcelRe = signal(false);
  enviandoRe = signal(false);
  exportandoRe = signal(false);
  loteRe = signal<RifaEnumeradaLote | null>(null);
  incluirRepetidosRe = false;
  reDesde = '';
  reHasta = '';
  private pollRe: ReturnType<typeof setInterval> | null = null;
  savingRelampago = signal(false);
  savingConferencia = signal(false);
  savingConferenciaVip = signal(false);
  savingVip = signal(false);
  savingRelampagoPers = signal(false);
  exportandoRifa = signal(false);
  savingTablaNum = signal(false);
  subiendoFotoTablaNum = signal(false);
  exportandoTablaNum = signal(false);
  tablaNumDesde = '';
  tablaNumHasta = '';
  rifaDesde = '';
  rifaHasta = '';
  ok = signal('');
  error = signal('');

  config: NumeroRelampagoConfig = {
    activo: false,
    valor: 0,
    numero: '',
  };

  conferencia: ConferenciaConfig = {
    activo: false,
    valor: 0,
    fecha_aviso: '',
    link_youtube: '',
  };

  conferenciaVip: ConferenciaVipConfig = {
    activo: false,
    valor: 0,
    fecha_aviso: '',
    link_youtube: '',
  };

  vip: VipConfig = {
    activo: false,
    valor: 0,
  };

  relampagoPers: RelampagoPersonalizadoConfig = {
    activo: false,
    valor: 0,
    vigencia_dias: 1,
    rifa_activo: false,
    rifa_descripcion: '',
  };

  tablaNum: TablaNumerologicaConfig = {
    activo: false,
    valor: 0,
    tiene_foto: false,
  };

  rifaEnum: RifaEnumeradaConfig = {
    activo: false,
    valor: 0,
    cantidad: 1,
    tiene_base: false,
  };

  constructor(private svc: ServiciosAdminService) {}

  ngOnInit(): void {
    this.cargar();
  }

  ngOnDestroy(): void {
    this.detenerPollRe();
  }

  cargar() {
    this.cargarRifaEnum();
    this.loading.set(true);
    this.error.set('');
    this.ok.set('');
    this.svc.getNumeroRelampago().subscribe({
      next: (cfg) => {
        this.config = { ...cfg };
        this.svc.getConferencia().subscribe({
          next: (conf) => {
            this.conferencia = { ...conf };
            this.svc.getConferenciaVip().subscribe({
              next: (confVip) => {
                this.conferenciaVip = { ...confVip };
                this.svc.getVip().subscribe({
                  next: (vip) => {
                    this.vip = { ...vip };
                    this.svc.getRelampagoPersonalizado().subscribe({
                      next: (rp) => {
                        this.relampagoPers = { ...rp };
                        this.svc.getTablaNumerologica().subscribe({
                          next: (tn) => {
                            this.tablaNum = { ...tn };
                            this.loading.set(false);
                          },
                          error: () => {
                            this.loading.set(false);
                            this.error.set('No fue posible cargar la configuración de tabla numerológica.');
                          },
                        });
                      },
                      error: () => {
                        this.loading.set(false);
                        this.error.set('No fue posible cargar la configuración de número relámpago personalizado.');
                      },
                    });
                  },
                  error: () => {
                    this.loading.set(false);
                    this.error.set('No fue posible cargar la configuración de VIP.');
                  },
                });
              },
              error: () => {
                this.loading.set(false);
                this.error.set('No fue posible cargar la configuración de conferencia VIP.');
              },
            });
          },
          error: () => {
            this.loading.set(false);
            this.error.set('No fue posible cargar la configuración de conferencia.');
          },
        });
      },
      error: () => {
        this.loading.set(false);
        this.error.set('No fue posible cargar la configuración de servicios.');
      },
    });
  }

  cargarRifaEnum() {
    this.svc.getRifaEnumerada().subscribe({
      next: (cfg) => (this.rifaEnum = { ...cfg }),
      error: () => this.error.set('No fue posible cargar la configuración de rifa enumerada.'),
    });
    this.svc.getUltimoLoteRifaEnumerada().subscribe({
      next: (lote) => this.setLoteRe(lote),
      error: () => this.setLoteRe(null),
    });
  }

  private setLoteRe(lote: RifaEnumeradaLote | null) {
    this.loteRe.set(lote);
    if (lote?.estado === 'enviando') this.iniciarPollRe();
    else this.detenerPollRe();
  }

  private iniciarPollRe() {
    if (this.pollRe) return;
    this.pollRe = setInterval(() => {
      const lote = this.loteRe();
      if (!lote) {
        this.detenerPollRe();
        return;
      }
      this.svc.getLoteRifaEnumerada(lote.id).subscribe({ next: (l) => this.setLoteRe(l) });
    }, 3000);
  }

  private detenerPollRe() {
    if (this.pollRe) clearInterval(this.pollRe);
    this.pollRe = null;
  }

  boletasAEnviarRe(lote: RifaEnumeradaLote): number {
    const celulares = lote.validas - (this.incluirRepetidosRe ? 0 : lote.ya_recibieron);
    return Math.max(0, celulares) * Math.max(1, Number(this.rifaEnum.cantidad || 1));
  }

  guardarRifaEnum() {
    this.savingRe.set(true);
    this.error.set('');
    this.ok.set('');
    const payload = {
      activo: !!this.rifaEnum.activo,
      valor: Math.max(0, Number(this.rifaEnum.valor || 0)),
      cantidad: Math.min(100, Math.max(1, Number(this.rifaEnum.cantidad || 1))),
    };
    this.svc.updateRifaEnumerada(payload).subscribe({
      next: (cfg) => {
        this.rifaEnum = { ...cfg };
        this.savingRe.set(false);
        this.ok.set('Configuración de Rifa enumerada guardada.');
      },
      error: (err) => {
        this.savingRe.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }

  onBaseRifaEnum(event: Event) {
    const input = event.target as HTMLInputElement;
    const archivo = input.files?.[0];
    if (!archivo) return;
    this.error.set('');
    this.ok.set('');
    if (archivo.type !== 'image/jpeg' && archivo.type !== 'image/png') {
      input.value = '';
      this.error.set('La imagen debe ser JPG o PNG.');
      return;
    }
    this.subiendoBaseRe.set(true);
    this.svc.subirBaseRifaEnumerada(archivo).subscribe({
      next: (cfg) => {
        this.rifaEnum = { ...this.rifaEnum, tiene_base: cfg.tiene_base };
        this.subiendoBaseRe.set(false);
        input.value = '';
        this.ok.set('Imagen base de Rifa enumerada guardada.');
      },
      error: (err) => {
        this.subiendoBaseRe.set(false);
        input.value = '';
        this.error.set(err?.error?.detail || 'No fue posible subir la imagen.');
      },
    });
  }

  onExcelRifaEnum(event: Event) {
    const input = event.target as HTMLInputElement;
    const archivo = input.files?.[0];
    if (!archivo) return;
    this.error.set('');
    this.ok.set('');
    if (!archivo.name.toLowerCase().endsWith('.xlsx')) {
      input.value = '';
      this.error.set('El archivo debe ser un Excel .xlsx.');
      return;
    }
    this.cargandoExcelRe.set(true);
    this.svc.cargarExcelRifaEnumerada(archivo).subscribe({
      next: (lote) => {
        this.setLoteRe(lote);
        this.cargandoExcelRe.set(false);
        input.value = '';
      },
      error: (err) => {
        this.cargandoExcelRe.set(false);
        input.value = '';
        this.error.set(err?.error?.detail || 'No fue posible leer el Excel.');
      },
    });
  }

  enviarRifaEnum() {
    const lote = this.loteRe();
    if (!lote) return;
    const total = this.boletasAEnviarRe(lote);
    if (!confirm(`Se enviarán ${total} boletas por WhatsApp. ¿Continuar?`)) return;
    this.enviandoRe.set(true);
    this.error.set('');
    this.ok.set('');
    this.svc.enviarLoteRifaEnumerada(lote.id, this.incluirRepetidosRe).subscribe({
      next: (l) => {
        this.setLoteRe(l);
        this.enviandoRe.set(false);
      },
      error: (err) => {
        this.enviandoRe.set(false);
        this.error.set(err?.error?.detail || 'No fue posible iniciar el envío.');
      },
    });
  }

  descargarRifaEnum() {
    this.exportandoRe.set(true);
    this.error.set('');
    this.svc.exportarRifaEnumerada(this.reDesde || undefined, this.reHasta || undefined).subscribe({
      next: (blob: Blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `rifa_enumerada_${this.reDesde || 'inicio'}_a_${this.reHasta || 'fin'}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        this.exportandoRe.set(false);
      },
      error: () => {
        this.exportandoRe.set(false);
        this.error.set('No fue posible descargar el Excel.');
      },
    });
  }

  guardarTablaNum() {
    this.savingTablaNum.set(true);
    this.error.set('');
    this.ok.set('');

    const payload = {
      activo: !!this.tablaNum.activo,
      valor: Math.max(0, Number(this.tablaNum.valor || 0)),
    };

    this.svc.updateTablaNumerologica(payload).subscribe({
      next: (cfg) => {
        this.tablaNum = { ...cfg };
        this.savingTablaNum.set(false);
        this.ok.set('Configuración de Tabla numerológica guardada.');
      },
      error: (err) => {
        this.savingTablaNum.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }

  onFotoTablaNum(event: Event) {
    const input = event.target as HTMLInputElement;
    const archivo = input.files?.[0];
    if (!archivo) return;
    this.error.set('');
    this.ok.set('');

    if (archivo.type !== 'image/jpeg') {
      input.value = '';
      this.error.set('La foto debe ser JPG.');
      return;
    }

    this.subiendoFotoTablaNum.set(true);
    this.svc.subirFotoTablaNumerologica(archivo).subscribe({
      next: (cfg) => {
        this.tablaNum = { ...this.tablaNum, tiene_foto: cfg.tiene_foto };
        this.subiendoFotoTablaNum.set(false);
        input.value = '';
        this.ok.set('Foto de Tabla numerológica guardada.');
      },
      error: (err) => {
        this.subiendoFotoTablaNum.set(false);
        input.value = '';
        this.error.set(err?.error?.detail || 'No fue posible subir la foto.');
      },
    });
  }

  descargarTablaNum() {
    this.exportandoTablaNum.set(true);
    this.error.set('');
    this.svc.exportarTablaNumerologica(this.tablaNumDesde || undefined, this.tablaNumHasta || undefined).subscribe({
      next: (blob: Blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `tabla_numerologica_${this.tablaNumDesde || 'inicio'}_a_${this.tablaNumHasta || 'fin'}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        this.exportandoTablaNum.set(false);
      },
      error: () => {
        this.exportandoTablaNum.set(false);
        this.error.set('No fue posible descargar las entregas.');
      },
    });
  }

  guardarRelampago() {
    this.savingRelampago.set(true);
    this.error.set('');
    this.ok.set('');

    const payload: NumeroRelampagoConfig = {
      activo: !!this.config.activo,
      valor: Math.max(0, Number(this.config.valor || 0)),
      numero: (this.config.numero || '').trim(),
    };

    this.svc.updateNumeroRelampago(payload).subscribe({
      next: (cfg) => {
        this.config = { ...cfg };
        this.savingRelampago.set(false);
        this.ok.set('Configuración de Número relámpago guardada.');
      },
      error: (err) => {
        this.savingRelampago.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }

  guardarRelampagoPers() {
    this.savingRelampagoPers.set(true);
    this.error.set('');
    this.ok.set('');

    const payload: RelampagoPersonalizadoConfig = {
      activo: !!this.relampagoPers.activo,
      valor: Math.max(0, Number(this.relampagoPers.valor || 0)),
      vigencia_dias: Math.max(1, Number(this.relampagoPers.vigencia_dias || 1)),
      rifa_activo: !!this.relampagoPers.rifa_activo,
      rifa_descripcion: (this.relampagoPers.rifa_descripcion || '').trim(),
    };

    this.svc.updateRelampagoPersonalizado(payload).subscribe({
      next: (cfg) => {
        this.relampagoPers = { ...cfg };
        this.savingRelampagoPers.set(false);
        this.ok.set('Configuración de Número relámpago personalizado guardada.');
      },
      error: (err) => {
        this.savingRelampagoPers.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }

  descargarNumerosRifa() {
    this.exportandoRifa.set(true);
    this.error.set('');
    this.svc.exportarNumerosRifa(this.rifaDesde || undefined, this.rifaHasta || undefined).subscribe({
      next: (blob: Blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `numeros_rifa_${this.rifaDesde || 'inicio'}_a_${this.rifaHasta || 'fin'}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        this.exportandoRifa.set(false);
      },
      error: () => {
        this.exportandoRifa.set(false);
        this.error.set('No fue posible descargar los números entregados.');
      },
    });
  }

  guardarConferencia() {
    this.savingConferencia.set(true);
    this.error.set('');
    this.ok.set('');

    const payload: ConferenciaConfig = {
      activo: !!this.conferencia.activo,
      valor: Math.max(0, Number(this.conferencia.valor || 0)),
      fecha_aviso: (this.conferencia.fecha_aviso || '').trim(),
      link_youtube: (this.conferencia.link_youtube || '').trim(),
    };

    this.svc.updateConferencia(payload).subscribe({
      next: (cfg) => {
        this.conferencia = { ...cfg };
        this.savingConferencia.set(false);
        this.ok.set('Configuración de Conferencia guardada.');
      },
      error: (err) => {
        this.savingConferencia.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }

  guardarConferenciaVip() {
    this.savingConferenciaVip.set(true);
    this.error.set('');
    this.ok.set('');

    const payload: ConferenciaVipConfig = {
      activo: !!this.conferenciaVip.activo,
      valor: Math.max(0, Number(this.conferenciaVip.valor || 0)),
      fecha_aviso: (this.conferenciaVip.fecha_aviso || '').trim(),
      link_youtube: (this.conferenciaVip.link_youtube || '').trim(),
    };

    this.svc.updateConferenciaVip(payload).subscribe({
      next: (cfg) => {
        this.conferenciaVip = { ...cfg };
        this.savingConferenciaVip.set(false);
        this.ok.set('Configuración de Conferencia VIP guardada.');
      },
      error: (err) => {
        this.savingConferenciaVip.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }

  guardarVip() {
    this.savingVip.set(true);
    this.error.set('');
    this.ok.set('');

    const payload: VipConfig = {
      activo: !!this.vip.activo,
      valor: Math.max(0, Number(this.vip.valor || 0)),
    };

    this.svc.updateVip(payload).subscribe({
      next: (cfg) => {
        this.vip = { ...cfg };
        this.savingVip.set(false);
        this.ok.set('Configuración de VIP guardada.');
      },
      error: (err) => {
        this.savingVip.set(false);
        this.error.set(err?.error?.detail || 'No fue posible guardar la configuración.');
      },
    });
  }
}
