import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ContactosService, Contacto } from '../../core/services/contactos.service';

@Component({
  selector: 'app-contactos',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './contactos.component.html',
  styleUrl: './contactos.component.scss',
})
export class ContactosComponent implements OnInit {
  items = signal<Contacto[]>([]);
  loading = signal(false);

  deleteTarget: Contacto | null = null;
  purgeVipConfirm = false;

  constructor(private svc: ContactosService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list().subscribe(data => {
      this.items.set(data);
      this.loading.set(false);
    });
  }

  confirmDelete(c: Contacto) { this.deleteTarget = c; }

  cancelDelete() { this.deleteTarget = null; }

  doDelete() {
    if (!this.deleteTarget) return;
    this.svc.delete(this.deleteTarget.id).subscribe(() => {
      this.items.update(list => list.filter(c => c.id !== this.deleteTarget!.id));
      this.deleteTarget = null;
    });
  }

  confirmPurgeVip() { this.purgeVipConfirm = true; }

  cancelPurgeVip() { this.purgeVipConfirm = false; }

  doPurgeVip() {
    this.svc.purgeVip().subscribe(() => {
      this.purgeVipConfirm = false;
      this.load();
    });
  }

  exportExcel() {
    this.svc.export().subscribe();
  }
}
