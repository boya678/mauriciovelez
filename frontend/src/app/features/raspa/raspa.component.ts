import { Component, OnInit, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

@Component({
  selector: 'app-raspa',
  standalone: true,
  templateUrl: './raspa.component.html',
  styleUrl: './raspa.component.scss',
})
export class RaspaComponent implements OnInit {
  texto = signal('');

  constructor(private route: ActivatedRoute) {}

  ngOnInit(): void {
    const param = this.route.snapshot.paramMap.get('texto') ?? '';
    this.texto.set(decodeURIComponent(param));
  }
}
