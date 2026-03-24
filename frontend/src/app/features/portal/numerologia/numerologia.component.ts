import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth.service';
import { environment } from '../../../../environments/environment';

export interface NumeroData {
  numero: string;
  numero_metodo: string;
  fecha_asignacion: string;
  vigencia_hasta: string;
  dias_restantes: number;
}

export interface MisNumerosResponse {
  nombre: string;
  es_vip: boolean;
  numero_libre: NumeroData;
  numero_vip?: NumeroData;
}

export interface AciertoCliente {
  numero: string;
  fecha: string;
  tipo: string;
  loteria: string;
  resultado: string;
}

@Component({
  selector: 'app-numerologia',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './numerologia.component.html',
  styleUrl: './numerologia.component.scss',
})
export class NumerologiaComponent implements OnInit {
  clienteNombre: string;
  loading = true;
  error: string | null = null;
  data: MisNumerosResponse | null = null;

  aciertos: AciertoCliente[] = [];
  loadingAciertos = true;

  constructor(private authService: AuthService, private http: HttpClient) {
    this.clienteNombre = authService.getCliente()?.nombre ?? 'Visitante';
  }

  ngOnInit(): void {
    const token = this.authService.getToken();
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http
      .get<MisNumerosResponse>(`${environment.apiUrl}/numerologia/mis-numeros`, { headers })
      .subscribe({
        next: (res) => { this.data = res; this.loading = false; },
        error: () => { this.error = 'No se pudo cargar tu número. Intenta de nuevo.'; this.loading = false; },
      });

    this.http
      .get<AciertoCliente[]>(`${environment.apiUrl}/numerologia/mis-aciertos`, { headers })
      .subscribe({
        next: (res) => { this.aciertos = res; this.loadingAciertos = false; },
        error: () => { this.loadingAciertos = false; },
      });
  }

  digitos(numero: string): string[] {
    return numero.split('');
  }

  tipoLabel(tipo: string): string {
    const map: Record<string, string> = {
      exacto: 'Exacto',
      directo_devuelto: 'Directo devuelto',
      tres_orden: '3 en orden',
      tres_desorden: '3 devuelto',
    };
    return map[tipo] ?? tipo;
  }
}

