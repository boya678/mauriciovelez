import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ContactosService, Contact } from '../../../core/services/contactos.service';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-contactos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './contactos.component.html',
  styleUrl: './contactos.component.scss',
})
export class ContactosComponent implements OnInit {
  private svc = inject(ContactosService);
  private auth = inject(AuthService);

  contacts = signal<Contact[]>([]);
  loading = signal(false);
  exporting = signal(false);
  search = '';

  ngOnInit() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.svc.list(this.search).subscribe({
      next: data => { this.contacts.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  async exportExcel() {
    this.exporting.set(true);
    try {
      const token = this.auth.getToken();
      const tenant = this.auth.getTenantSlug();
      const res = await fetch(this.svc.exportUrl(), {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant-ID': tenant,
        },
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'contactos.xlsx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      this.exporting.set(false);
    }
  }
}

