import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore, CaseDocument } from '../case.store';
import { TemplateShiftService } from '../../template-shift/services/template-shift.service';
import { ShiftReport, ShiftResult } from '../../template-shift/models/template-shift.models';

interface RunOutcome {
  report: ShiftReport;
  blobUrl: string;
  filename: string;
}

@Component({
  selector: 'app-migrate-tool',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './migrate-tool.component.html',
  styleUrl: './migrate-tool.component.scss',
})
export class MigrateToolComponent {
  private readonly store = inject(CaseStore);
  private readonly service = inject(TemplateShiftService);

  protected readonly fdId = signal<string | null>(null);
  protected readonly templateId = signal<string | null>(null);
  protected readonly running = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly outcome = signal<RunOutcome | null>(null);

  protected readonly fdOptions = computed(() =>
    this.store.documentsByKind().fd,
  );
  protected readonly templateOptions = computed(() =>
    this.store.documentsByKind().template,
  );

  /** Per-confidence-bucket counts for the mapping summary. */
  protected readonly mappingStats = computed(() => {
    const matches = this.outcome()?.report.matches ?? [];
    const stats = { exact: 0, fuzzy: 0, ai: 0, placeholder: 0 };
    for (const m of matches) {
      if (m.confidence === 'exact') stats.exact++;
      else if (m.confidence === 'fuzzy') stats.fuzzy++;
      else if (m.confidence === 'placeholder') stats.placeholder++;
      else stats.ai++;
    }
    return stats;
  });

  constructor() {
    // Auto-pick first available doc per slot whenever the case changes.
    queueMicrotask(() => {
      if (!this.fdId() && this.fdOptions()[0]) {
        this.fdId.set(this.fdOptions()[0].id);
      }
      if (!this.templateId() && this.templateOptions()[0]) {
        this.templateId.set(this.templateOptions()[0].id);
      }
    });
  }

  protected docName(id: string | null): string {
    if (!id) return '';
    return this.store.documents().find((d) => d.id === id)?.name ?? '';
  }

  protected canRun(): boolean {
    return !!this.fdId() && !!this.templateId() && !this.running();
  }

  private docFile(id: string | null): File | null {
    if (!id) return null;
    return this.store.documents().find((d) => d.id === id)?.file ?? null;
  }

  protected run(): void {
    const fd = this.docFile(this.fdId());
    const tpl = this.docFile(this.templateId());
    if (!fd || !tpl) return;

    this.error.set(null);
    this.outcome.set(null);
    this.running.set(true);

    this.service.migrate(fd, tpl, null).subscribe({
      next: (res: ShiftResult) => {
        this.running.set(false);
        const url = URL.createObjectURL(res.blob);
        this.outcome.set({
          report: res.report,
          blobUrl: url,
          filename: res.filename,
        });
        this.store.setToolResult('migrate', res.report);
      },
      error: (err) => {
        this.running.set(false);
        this.error.set(
          err?.error?.detail || err?.message || 'Migration failed',
        );
      },
    });
  }

  protected download(): void {
    const o = this.outcome();
    if (!o) return;
    const a = document.createElement('a');
    a.href = o.blobUrl;
    a.download = o.filename;
    a.click();
  }

  protected confidenceLabel(c: string): string {
    switch (c) {
      case 'exact':
        return '✅';
      case 'fuzzy':
        return '⚖';
      case 'placeholder':
        return '⛔';
      default:
        return '✨';
    }
  }

  protected onPickFd(event: Event): void {
    this.fdId.set((event.target as HTMLSelectElement).value || null);
  }
  protected onPickTemplate(event: Event): void {
    this.templateId.set((event.target as HTMLSelectElement).value || null);
  }
}
