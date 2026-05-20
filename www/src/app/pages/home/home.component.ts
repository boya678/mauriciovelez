import {
  Component,
  OnInit,
  OnDestroy,
  AfterViewInit,
  ElementRef,
  ViewChild,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  signal,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { LoteriasService, LoteriaResultado } from '../../core/services/loterias.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, DatePipe],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('heroBg', { static: true }) heroBgRef!: ElementRef<HTMLDivElement>;

  /* ── Estado ─────────────────────────────────────────── */
  navScrolled = signal(false);
  menuOpen    = signal(false);

  selectedDate = '';
  resultados:  LoteriaResultado[] = [];
  cargando    = false;
  error       = '';
  buscado     = false;

  readonly currentYear = new Date().getFullYear();

  readonly pillars = [
    {
      icon: 'calculate',
      title: 'Numerología Personal',
      desc: 'Descifra tu número de camino de vida, expresión y alma. Entiende tu misión en esta existencia.',
    },
    {
      icon: 'casino',
      title: 'Análisis de Loterías',
      desc: 'Interpretación numerológica de los resultados para entender los ciclos y patrones del universo.',
    },
    {
      icon: 'auto_awesome',
      title: 'Guía Espiritual',
      desc: 'Acompañamiento en momentos de decisión con las herramientas que te da la ciencia de los números.',
    },
    {
      icon: 'event_note',
      title: 'Años Personales',
      desc: 'Identifica el año personal en el que te encuentras y toma decisiones alineadas con tu ciclo vital.',
    },
  ];

  /* ── Lifecycle hooks ────────────────────────────────── */
  private scrollHandler!: () => void;
  private resizeHandler!: () => void;
  private observer?: IntersectionObserver;

  constructor(
    private loterias: LoteriasService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.selectedDate = this.hoy();
    this.buscar();
  }

  ngAfterViewInit(): void {
    this.initParallax();
    this.initReveal();
  }

  ngOnDestroy(): void {
    window.removeEventListener('scroll', this.scrollHandler);
    window.removeEventListener('resize', this.resizeHandler);
    this.observer?.disconnect();
  }

  /* ── Parallax ───────────────────────────────────────── */
  private initParallax(): void {
    const bg = this.heroBgRef.nativeElement;
    this.scrollHandler = () => {
      const y = window.scrollY;
      this.navScrolled.set(y > 40);
      bg.style.transform = `translateY(${y * 0.35}px)`;
    };
    window.addEventListener('scroll', this.scrollHandler, { passive: true });
  }

  /* ── Reveal on scroll ───────────────────────────────── */
  private initReveal(): void {
    this.observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('is-visible');
            this.observer?.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    );
    document.querySelectorAll('.reveal').forEach((el) => this.observer!.observe(el));
  }

  /* ── Menú hamburguesa ───────────────────────────────── */
  toggleMenu(): void { this.menuOpen.update((v) => !v); }
  closeMenu(): void  { this.menuOpen.set(false); }

  /* ── Loterías ───────────────────────────────────────── */
  buscar(): void {
    if (!this.selectedDate) return;
    this.cargando  = true;
    this.error     = '';
    this.resultados = [];
    this.buscado   = false;
    this.cdr.markForCheck();

    this.loterias.getResultados(this.selectedDate).subscribe({
      next: (data) => {
        this.resultados = data;
        this.buscado   = true;
        this.cargando  = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.error    = 'No fue posible obtener los resultados. Intenta de nuevo.';
        this.buscado  = true;
        this.cargando = false;
        this.cdr.markForCheck();
      },
    });
  }

  /* ── Helpers ────────────────────────────────────────── */
  hoy(): string {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  formatFecha(iso: string): string {
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
  }
}
