import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { ShiftReport, SectionMatchReport } from '../models/template-shift.models';
import { TemplateShiftService } from '../services/template-shift.service';

interface MatchGroup {
  label: string;
  entries: SectionMatchReport[];
}

@Component({
  selector: 'app-template-shift-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './template-shift-page.component.html',
  styleUrls: ['./template-shift-page.component.scss'],
})
export class TemplateShiftPageComponent {
  private readonly service = inject(TemplateShiftService);

  readonly oldFd = signal<File | null>(null);
  readonly template = signal<File | null>(null);
  readonly plan = signal<File | null>(null);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly report = signal<ShiftReport | null>(null);
  readonly downloadUrl = signal<string | null>(null);
  readonly downloadName = signal<string>('fisa_disciplinei_migrated.docx');

  pickFile(target: 'oldFd' | 'template' | 'plan', event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    if (target === 'oldFd') this.oldFd.set(file);
    if (target === 'template') this.template.set(file);
    if (target === 'plan') this.plan.set(file);
  }

  canMigrate(): boolean {
    return !!this.oldFd() && !!this.template() && !this.loading();
  }

  migrate(): void {
    const oldFd = this.oldFd();
    const template = this.template();
    if (!oldFd || !template) return;

    this.loading.set(true);
    this.errorMessage.set(null);
    this.report.set(null);
    const previous = this.downloadUrl();
    if (previous) URL.revokeObjectURL(previous);
    this.downloadUrl.set(null);

    this.service.migrate(oldFd, template, this.plan()).subscribe({
      next: (result) => {
        this.report.set(result.report);
        this.downloadName.set(result.filename);
        this.downloadUrl.set(URL.createObjectURL(result.blob));
        this.loading.set(false);
      },
      error: (err) => {
        this.errorMessage.set(err?.error?.detail ?? err?.message ?? 'Migration failed');
        this.loading.set(false);
      },
    });
  }

  groupedMatches(): MatchGroup[] {
    const r = this.report();
    if (!r) return [];
    const groups: Record<string, SectionMatchReport[]> = {
      'Exact': [],
      'Fuzzy': [],
      'LLM': [],
      'Placeholder': [],
    };
    for (const m of r.matches) {
      if (m.confidence === 'exact') groups['Exact'].push(m);
      else if (m.confidence === 'fuzzy') groups['Fuzzy'].push(m);
      else if (m.confidence.startsWith('llm-')) groups['LLM'].push(m);
      else groups['Placeholder'].push(m);
    }
    return Object.entries(groups)
      .filter(([, v]) => v.length > 0)
      .map(([label, entries]) => ({ label, entries }));
  }
}
