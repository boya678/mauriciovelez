import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { RifasService, RifaPublic } from '../../core/services/rifas.service';

@Component({
  selector: 'app-rifa-banner',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    @if (rifa()) {
      <a class="rifa-banner" routerLink="/portal/rifa">
        <span class="rifa-banner__icon material-icons-round">confirmation_number</span>
        <div class="rifa-banner__body">
          <span class="rifa-banner__label">¡Evento activo!</span>
          <span class="rifa-banner__titulo">{{ rifa()!.titulo }}</span>
          <span class="rifa-banner__dates">
            {{ rifa()!.fecha_inicio | date:'d MMM' }} – {{ rifa()!.fecha_fin | date:'d MMM yyyy' }}
          </span>
        </div>
        <span class="rifa-banner__arrow material-icons-round">chevron_right</span>
      </a>
    }
  `,
  styles: [`
    .rifa-banner {
      display: flex;
      align-items: center;
      gap: .85rem;
      background: linear-gradient(135deg, #1565c0 0%, #1976d2 100%);
      color: #fff;
      border-radius: 12px;
      padding: .9rem 1.1rem;
      margin-bottom: 1.25rem;
      text-decoration: none;
      box-shadow: 0 4px 14px rgba(25,118,210,.3);
      transition: opacity .15s, box-shadow .15s;
      cursor: pointer;

      &:hover {
        opacity: .93;
        box-shadow: 0 6px 18px rgba(25,118,210,.4);
      }

      &__icon {
        font-size: 2rem;
        flex-shrink: 0;
        opacity: .9;
      }

      &__body {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-width: 0;
      }

      &__label {
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
        opacity: .8;
      }

      &__titulo {
        font-size: 1rem;
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      &__dates {
        font-size: .8rem;
        opacity: .75;
        margin-top: .1rem;
      }

      &__arrow {
        font-size: 1.6rem;
        opacity: .7;
        flex-shrink: 0;
      }
    }
  `],
})
export class RifaBannerComponent implements OnInit {
  rifa = signal<RifaPublic | null>(null);

  constructor(private rifasService: RifasService) {}

  ngOnInit(): void {
    this.rifasService.getActiva().subscribe({
      next: (r) => this.rifa.set(r),
      error: () => {},
    });
  }
}
