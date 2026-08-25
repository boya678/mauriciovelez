import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ConferenciaConfig, ConferenciaVipConfig, NumeroRelampagoConfig, ServiciosAdminService } from '../../core/services/servicios-admin.service';

@Component({
  selector: 'app-servicios',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './servicios.component.html',
  styleUrl: './servicios.component.scss',
})
export class ServiciosComponent implements OnInit {
  loading = signal(false);
  savingRelampago = signal(false);
  savingConferencia = signal(false);
  savingConferenciaVip = signal(false);
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

  constructor(private svc: ServiciosAdminService) {}

  ngOnInit(): void {
    this.cargar();
  }

  cargar() {
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
                this.loading.set(false);
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
}
