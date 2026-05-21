import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService, Aliado } from '../../../core/services/auth.service';

@Component({
  selector: 'app-mis-datos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './mis-datos.component.html',
  styleUrl: './mis-datos.component.scss',
})
export class MisDatosComponent implements OnInit {
  aliado = signal<Aliado | null>(null);
  loading = signal(false);
  saving = signal(false);
  successMsg = signal('');
  errorMsg = signal('');

  // Editable fields
  nombre = '';
  correo = '';
  cc = '';

  constructor(private auth: AuthService) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading.set(true);
    this.auth.getPerfil().subscribe({
      next: a => {
        this.aliado.set(a);
        this.nombre = a.nombre ?? '';
        this.correo = a.correo ?? '';
        this.cc = a.cc ?? '';
        this.loading.set(false);
      },
      error: () => {
        const a = this.auth.getAliado();
        if (a) {
          this.aliado.set(a);
          this.nombre = a.nombre ?? '';
          this.correo = a.correo ?? '';
          this.cc = a.cc ?? '';
        }
        this.loading.set(false);
      },
    });
  }

  save(): void {
    this.successMsg.set('');
    this.errorMsg.set('');
    const n = this.nombre.trim();
    if (!n) { this.errorMsg.set('El nombre es requerido'); return; }

    this.saving.set(true);
    this.auth.updatePerfil({
      nombre: n,
      correo: this.correo.trim() || null,
      cc: this.cc.trim() || null,
    }).subscribe({
      next: a => {
        this.aliado.set(a);
        this.successMsg.set('Datos actualizados correctamente');
        this.saving.set(false);
      },
      error: err => {
        this.errorMsg.set(err.error?.detail ?? 'Error al guardar los datos');
        this.saving.set(false);
      },
    });
  }

  get saldoFmt(): string {
    const s = this.aliado()?.saldo ?? 0;
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(s);
  }
}
