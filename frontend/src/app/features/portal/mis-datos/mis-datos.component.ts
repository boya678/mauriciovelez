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

  saving = false;
  success = false;
  errorMsg = '';

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
  }

  submit(form: NgForm) {
    if (form.invalid) return;
    this.saving = true;
    this.success = false;
    this.errorMsg = '';

    this.auth.updateMisDatos({
      nombre: this.nombre.trim(),
      celular: this.celular.trim(),
      correo: this.correo.trim() || null,
      cc: this.cc.trim() || null,
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
