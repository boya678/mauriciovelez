import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NgForm } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService, Cliente } from '../../../core/services/auth.service';

@Component({
  selector: 'app-mis-datos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './mis-datos.component.html',
  styleUrl: './mis-datos.component.scss',
})
export class MisDatosComponent implements OnInit {
  nombre = '';
  celular = '';
  correo = '';
  cc = '';
  bdDia = 0;
  bdMes = 0;
  bdAnio = 0;

  meses = [
    { v: 1, n: 'Enero' }, { v: 2, n: 'Febrero' }, { v: 3, n: 'Marzo' },
    { v: 4, n: 'Abril' }, { v: 5, n: 'Mayo' }, { v: 6, n: 'Junio' },
    { v: 7, n: 'Julio' }, { v: 8, n: 'Agosto' }, { v: 9, n: 'Septiembre' },
    { v: 10, n: 'Octubre' }, { v: 11, n: 'Noviembre' }, { v: 12, n: 'Diciembre' },
  ];
  anios = Array.from({ length: 91 }, (_, i) => new Date().getFullYear() - 1 - i);

  saving = false;
  success = false;
  errorMsg = '';

  diasParaMes(mes: number, anio: number): number[] {
    const max = (mes && anio) ? new Date(anio, mes, 0).getDate() : 31;
    return Array.from({ length: max }, (_, i) => i + 1);
  }

  onMesChange() {
    const max = (this.bdMes && this.bdAnio) ? new Date(this.bdAnio, this.bdMes, 0).getDate() : 31;
    if (this.bdDia > max) this.bdDia = 0;
  }

  onAnioChange() { this.onMesChange(); }

  constructor(private auth: AuthService, private router: Router) {}

  ngOnInit() {
    const c = this.auth.getCliente();
    if (!c?.vip) {
      this.router.navigate(['/portal/numerologia']);
      return;
    }
    this.nombre = c.nombre ?? '';
    this.celular = c.celular ?? '';
    this.correo = c.correo ?? '';
    this.cc = c.cc ?? '';
    if (c.fecha_nacimiento) {
      const [ay, am, ad] = c.fecha_nacimiento.split('-').map(Number);
      this.bdAnio = ay; this.bdMes = am; this.bdDia = ad;
    }
  }

  submit(form: NgForm) {
    if (form.invalid) return;
    this.saving = true;
    this.success = false;
    this.errorMsg = '';

    const fechaNacimiento = (this.bdDia && this.bdMes && this.bdAnio)
      ? `${this.bdAnio}-${this.bdMes.toString().padStart(2, '0')}-${this.bdDia.toString().padStart(2, '0')}`
      : null;

    this.auth.updateMisDatos({
      nombre: this.nombre.trim(),
      celular: this.celular.trim(),
      correo: this.correo.trim() || null,
      cc: this.cc.trim() || null,
      fecha_nacimiento: fechaNacimiento,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.success = true;
      },
      error: (err) => {
        this.saving = false;
        this.errorMsg = err?.error?.detail ?? 'Error al guardar los datos';
      },
    });
  }
}
