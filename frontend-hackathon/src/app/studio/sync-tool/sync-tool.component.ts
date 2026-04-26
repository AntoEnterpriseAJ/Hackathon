import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore, CaseDocument } from '../case.store';
import { SyncCheckService } from '../../sync-check/services/sync-check.service';
import {
  BibliographyReport,
  CompetencyMapping,
  CrossValidationResult,
  ExtractedDocument,
  GuardViolation,
  NumericConsistencyReport,
} from '../../sync-check/models/sync.models';
import { forkJoin, of, switchMap } from 'rxjs';

@Component({
  selector: 'app-sync-tool',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sync-tool.component.html',
  styleUrl: './sync-tool.component.scss',
})
export class SyncToolComponent {
  private readonly store = inject(CaseStore);
  private readonly service = inject(SyncCheckService);

  protected readonly fdId = signal<string | null>(null);
  protected readonly planId = signal<string | null>(null);
  protected readonly running = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly result = signal<CrossValidationResult | null>(null);
  protected readonly mapping = signal<CompetencyMapping | null>(null);
  protected readonly mappingError = signal<string | null>(null);
  protected readonly mappingRunning = signal(false);
  protected readonly numericReport = signal<NumericConsistencyReport | null>(null);
  protected readonly bibliographyReport = signal<BibliographyReport | null>(null);

  protected readonly fdOptions = computed(() => this.store.documentsByKind().fd);
  protected readonly planOptions = computed(() => this.store.documentsByKind().plan);

  constructor() {
    queueMicrotask(() => {
      if (!this.fdId() && this.fdOptions()[0]) this.fdId.set(this.fdOptions()[0].id);
      if (!this.planId() && this.planOptions()[0]) this.planId.set(this.planOptions()[0].id);
    });
  }

  protected canRun(): boolean {
    return !!this.fdId() && !!this.planId() && !this.running();
  }

  protected onPickFd(e: Event): void {
    this.fdId.set((e.target as HTMLSelectElement).value || null);
  }
  protected onPickPlan(e: Event): void {
    this.planId.set((e.target as HTMLSelectElement).value || null);
  }

  /** Parse a doc if not already parsed; otherwise return cached. */
  private getParsed(doc: CaseDocument) {
    if (doc.parsed) return of(doc.parsed as ExtractedDocument);
    return this.service.parse(doc.file).pipe(
      switchMap((parsed) => {
        this.store.updateDocument(doc.id, { parsed });
        this.store.setDocumentStatus(doc.id, { parsed: true });
        return of(parsed);
      }),
    );
  }

  protected run(): void {
    const fd = this.store.documents().find((d) => d.id === this.fdId());
    const plan = this.store.documents().find((d) => d.id === this.planId());
    if (!fd || !plan) return;

    this.error.set(null);
    this.result.set(null);
    this.mapping.set(null);
    this.mappingError.set(null);
    this.mappingRunning.set(false);
    this.numericReport.set(null);
    this.bibliographyReport.set(null);
    this.running.set(true);

    forkJoin({ fd: this.getParsed(fd), plan: this.getParsed(plan) })
      .pipe(switchMap(({ fd, plan }) =>
        this.service.crossValidate(fd, plan).pipe(
          switchMap((res) => {
            // Kick off competency mapping in the background — non-blocking.
            this.runMapping(fd, plan);
            this.runNumeric(fd);
            this.runBibliography(fd);
            return of(res);
          }),
        ),
      ))
      .subscribe({
        next: (res) => {
          this.running.set(false);
          this.result.set(res);
          this.store.setToolResult('sync', res);
        },
        error: (err) => {
          this.running.set(false);
          this.error.set(err?.error?.detail || err?.message || 'Sync check failed');
        },
      });
  }

  private runMapping(fd: ExtractedDocument, plan: ExtractedDocument): void {
    this.mappingRunning.set(true);
    // Explicitly opt into Claude suggestions so the AI-recommended block
    // is populated whenever there are plan-only competencies the FD hasn't declared.
    this.service.mapCompetencies(fd, plan, true).subscribe({
      next: (cm) => {
        this.mappingRunning.set(false);
        this.mapping.set(cm);
      },
      error: (err) => {
        this.mappingRunning.set(false);
        this.mappingError.set(err?.error?.detail || err?.message || 'Competency mapping failed');
      },
    });
  }

  protected violationStatus(v: GuardViolation): string {
    return v.code.includes('mismatch') ? '⚠' : '✗';
  }

  private runNumeric(fd: ExtractedDocument): void {
    this.service.checkNumericConsistency(fd).subscribe({
      next: (r) => this.numericReport.set(r),
      error: () => { /* non-fatal */ },
    });
  }

  private runBibliography(fd: ExtractedDocument): void {
    this.service.checkFdBibliography(fd).subscribe({
      next: (r) => this.bibliographyReport.set(r),
      error: () => { /* non-fatal */ },
    });
  }

  protected canDownloadReport(): boolean {
    return !!this.result() && !this.running();
  }

  protected downloadReport(): void {
    const text = this.buildReport();
    if (!text) return;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const fdDoc = this.store.documents().find((d) => d.id === this.fdId());
    const stem = (fdDoc?.name ?? 'fd').replace(/\.pdf$/i, '');
    a.href = url;
    a.download = `sync-report-${stem}-${stamp}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  private buildReport(): string {
    const r = this.result();
    if (!r) return '';
    const fdDoc = this.store.documents().find((d) => d.id === this.fdId());
    const planDoc = this.store.documents().find((d) => d.id === this.planId());
    const lines: string[] = [];
    lines.push('Raport Sync-Check FD ↔ Plan de Învățământ');
    lines.push('='.repeat(60));
    lines.push(`Generat:     ${new Date().toLocaleString('ro-RO')}`);
    lines.push(`FD:          ${fdDoc?.name ?? '—'}`);
    lines.push(`Plan:        ${planDoc?.name ?? '—'}`);
    lines.push('');
    lines.push(`Disciplină:  ${r.fd_course_name ?? '—'}`);
    const statusLabel =
      r.status === 'valid' ? '✅ Aliniat'
      : r.status === 'invalid' ? '⚠ Inconsistent'
      : '❓ Nepotrivit';
    lines.push(`Status:      ${statusLabel}`);
    lines.push('');
    if (r.summary) {
      lines.push(r.summary.trim());
      lines.push('');
    }

    if (r.plan_match) {
      const m = r.plan_match;
      lines.push('Potrivire în Plan');
      lines.push(`  Denumire           : ${m.course_name}`);
      if (m.course_code) lines.push(`  Cod                : ${m.course_code}`);
      if (m.year != null) lines.push(`  An / Semestru      : ${m.year} / ${m.semester ?? '—'}`);
      if (m.credits != null) lines.push(`  Credite (Plan)     : ${m.credits}`);
      if (m.evaluation_form) lines.push(`  Evaluare (Plan)    : ${m.evaluation_form}`);
      lines.push(`  Tip potrivire      : ${m.match_confidence}`);
      lines.push('');
    }

    if (r.field_violations.length) {
      lines.push('⚠ Inconsistențe administrative');
      for (const v of r.field_violations) {
        lines.push(`  - [${v.code}] ${v.message}`);
      }
      lines.push('');
    }

    if (r.competency_violations.length) {
      lines.push('⚠ Competențe nealiniate');
      for (const v of r.competency_violations) {
        lines.push(`  - [${v.code}] ${v.message}`);
      }
      lines.push('');
    }

    if (!r.field_violations.length && !r.competency_violations.length && r.status === 'valid') {
      lines.push('✅ Toate verificările cross-doc au trecut.');
      lines.push('');
    }

    const cm = this.mapping();
    if (cm) {
      lines.push('🎯 Hartă competențe (UC 2.2)');
      lines.push(`  ${cm.summary}`);
      lines.push(`  Declarate corect : ${cm.declared.length}`);
      lines.push(`  Necunoscute      : ${cm.unknown.length}`);
      lines.push(`  Sugerate de AI   : ${cm.recommended.length}`);
      lines.push('');
    }

    const nr = this.numericReport();
    if (nr) {
      lines.push('🔢 Consistență numerică (UC 1.2)');
      lines.push(`  ${nr.summary}`);
      for (const issue of nr.issues) {
        const icon = issue.severity === 'error' ? '⛔' : issue.severity === 'warning' ? '⚠️' : 'ℹ️';
        lines.push(`  ${icon} [${issue.code}] ${issue.message}`);
      }
      lines.push('');
    }

    const br = this.bibliographyReport();
    if (br) {
      lines.push('📚 Bibliografie (UC 3.1)');
      lines.push(`  ${br.summary}`);
      for (const e of br.entries) {
        const yearLabel = e.latest_year !== null
          ? (e.age_years !== null ? `${e.latest_year} (${e.age_years} ani)` : `${e.latest_year}`)
          : 'fără an';
        const flag = e.issues.length > 0 ? '⚠️' : '✓';
        const text = e.text.length > 120 ? e.text.slice(0, 117) + '…' : e.text;
        lines.push(`  ${flag} [${yearLabel}] ${text}`);
      }
      lines.push('');
    }

    lines.push('-'.repeat(60));
    lines.push('Sfârșitul raportului.');
    return lines.join('\n');
  }

  protected counts() {
    const r = this.result();
    if (!r) return { ok: 0, warn: 0, miss: 0 };
    const all = [...r.field_violations, ...r.competency_violations];
    let warn = 0;
    let miss = 0;
    for (const v of all) {
      if (v.code.includes('mismatch')) warn++;
      else miss++;
    }
    return { ok: 0, warn, miss };
  }
}
