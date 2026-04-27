import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CaseStore, CaseDocument } from '../case.store';
import { DraftService } from '../../draft/services/draft.service';
import { ExtractedDocument, PlanCourseListResponse } from '../../draft/models/draft.models';
import { of, switchMap } from 'rxjs';

@Component({
  selector: 'app-draft-tool',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './draft-tool.component.html',
  styleUrl: './draft-tool.component.scss',
})
export class DraftToolComponent {
  private readonly store = inject(CaseStore);
  private readonly service = inject(DraftService);

  protected readonly planId = signal<string | null>(null);
  protected readonly courses = signal<PlanCourseListResponse | null>(null);
  protected readonly courseName = signal<string>('');
  protected readonly useClaude = signal(true);
  protected readonly running = signal(false);
  protected readonly listing = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly downloadUrl = signal<string | null>(null);

  protected readonly planOptions = computed(() => this.store.documentsByKind().plan);

  constructor() {
    queueMicrotask(() => {
      if (!this.planId() && this.planOptions()[0]) this.planId.set(this.planOptions()[0].id);
    });
  }

  protected onPickPlan(e: Event): void {
    this.planId.set((e.target as HTMLSelectElement).value || null);
    this.courses.set(null);
    this.courseName.set('');
  }

  private getParsed(doc: CaseDocument) {
    if (doc.parsed) return of(doc.parsed as ExtractedDocument);
    return this.service.parsePlan(doc.file).pipe(
      switchMap((parsed) => {
        this.store.updateDocument(doc.id, { parsed });
        this.store.setDocumentStatus(doc.id, { parsed: true });
        return of(parsed);
      }),
    );
  }

  protected loadCourses(): void {
    const plan = this.store.documents().find((d) => d.id === this.planId());
    if (!plan) return;
    this.error.set(null);
    this.listing.set(true);
    this.getParsed(plan)
      .pipe(switchMap((parsed) => this.service.listCourses(parsed)))
      .subscribe({
        next: (res) => {
          this.listing.set(false);
          this.courses.set(res);
        },
        error: (err) => {
          this.listing.set(false);
          this.error.set(err?.error?.detail || err?.message || 'Failed to list courses');
        },
      });
  }

  protected canGenerate(): boolean {
    return !!this.planId() && !!this.courseName().trim() && !this.running();
  }

  protected generate(): void {
    const plan = this.store.documents().find((d) => d.id === this.planId());
    if (!plan) return;
    this.error.set(null);
    this.downloadUrl.set(null);
    this.running.set(true);

    this.getParsed(plan)
      .pipe(
        switchMap((parsed) =>
          this.service.draftDocx(parsed, this.courseName().trim(), null, this.useClaude()),
        ),
      )
      .subscribe({
        next: (blob) => {
          this.running.set(false);
          const url = URL.createObjectURL(blob);
          this.downloadUrl.set(url);
          this.store.setToolResult('draft', { course: this.courseName() });
        },
        error: (err) => {
          this.running.set(false);
          this.error.set(err?.error?.detail || err?.message || 'Draft generation failed');
        },
      });
  }

  protected download(): void {
    const url = this.downloadUrl();
    if (!url) return;
    const a = document.createElement('a');
    a.href = url;
    a.download = `fisa_${this.courseName().replace(/\s+/g, '_')}.docx`;
    a.click();
  }
}
