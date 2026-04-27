import { Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore } from '../case.store';

@Component({
  selector: 'app-status-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './status-bar.component.html',
  styleUrl: './status-bar.component.scss',
})
export class StatusBarComponent {
  protected readonly store = inject(CaseStore);

  protected readonly activeName = computed(() => {
    const t = this.store.activeTab();
    if (!t) return 'No tab';
    return t.title;
  });

  protected readonly docCount = computed(() => this.store.documents().length);
}
