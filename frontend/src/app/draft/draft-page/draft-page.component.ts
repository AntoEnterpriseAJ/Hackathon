import { Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { DraftService } from '../services/draft.service';
import {
  ExtractedDocument,
  FdDraft,
  PlanCourseSummary,
} from '../models/draft.models';

type Status = 'idle' | 'parsing' | 'listing' | 'drafting' | 'done' | 'error';

@Component({
  selector: 'app-draft-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './draft-page.component.html',
  styleUrl: './draft-page.component.scss',
})
export class DraftPageComponent {
  planFile = signal<File | null>(null);
  planDoc = signal<ExtractedDocument | null>(null);
  programName = signal<string | null>(null);

  courses = signal<PlanCourseSummary[]>([]);
  selectedCourse = signal<PlanCourseSummary | null>(null);
  filterText = signal<string>('');
  filterYear = signal<number | null>(null);

  useClaude = signal<boolean>(true);

  status = signal<Status>('idle');
  errorMessage = signal<string>('');
  draft = signal<FdDraft | null>(null);

  filteredCourses = computed<PlanCourseSummary[]>(() => {
    const txt = this.filterText().trim().toLowerCase();
    const year = this.filterYear();
    return this.courses().filter((c) => {
      if (year != null && c.year !== year) return false;
      if (!txt) return true;
      return (
        c.course_name.toLowerCase().includes(txt) ||
        (c.course_code ?? '').toLowerCase().includes(txt)
      );
    });
  });

  availableYears = computed<number[]>(() => {
    const set = new Set<number>();
    for (const c of this.courses()) {
      if (c.year != null) set.add(c.year);
    }
    return Array.from(set).sort((a, b) => a - b);
  });

  canParse = computed(() => !!this.planFile() && this.status() === 'idle');
  canDraft = computed(() => !!this.selectedCourse() && this.status() !== 'parsing' && this.status() !== 'drafting');

  constructor(private draftSvc: DraftService) {}

  onPlanSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.planFile.set(input.files?.[0] ?? null);
    this.planDoc.set(null);
    this.courses.set([]);
    this.selectedCourse.set(null);
    this.draft.set(null);
    this.status.set('idle');
    this.errorMessage.set('');
    this.programName.set(null);
  }

  async loadPlan(): Promise<void> {
    const file = this.planFile();
    if (!file) return;
    this.status.set('parsing');
    this.errorMessage.set('');
    try {
      const doc = await firstValueFrom(this.draftSvc.parsePlan(file));
      this.planDoc.set(doc);
      this.status.set('listing');
      const list = await firstValueFrom(this.draftSvc.listCourses(doc));
      this.programName.set(list.program ?? null);
      this.courses.set(list.courses);
      this.status.set('idle');
    } catch (err: unknown) {
      this.errorMessage.set(this.errorDetail(err));
      this.status.set('error');
    }
  }

  selectCourse(course: PlanCourseSummary): void {
    this.selectedCourse.set(course);
    this.draft.set(null);
  }

  async generate(): Promise<void> {
    const plan = this.planDoc();
    const course = this.selectedCourse();
    if (!plan || !course) return;
    this.status.set('drafting');
    this.errorMessage.set('');
    try {
      const result = await firstValueFrom(
        this.draftSvc.draft(plan, course.course_name, course.course_code ?? null, this.useClaude()),
      );
      this.draft.set(result);
      this.status.set('done');
    } catch (err: unknown) {
      this.errorMessage.set(this.errorDetail(err));
      this.status.set('error');
    }
  }

  download(): void {
    const d = this.draft();
    if (!d) return;
    const blob = new Blob([d.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fisa-disciplinei-${this.safeFilename(d.course_name)}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async downloadDocx(): Promise<void> {
    const plan = this.planDoc();
    const course = this.selectedCourse();
    const d = this.draft();
    if (!plan || !course || !d) return;
    this.status.set('drafting');
    this.errorMessage.set('');
    try {
      const blob = await firstValueFrom(
        this.draftSvc.draftDocx(plan, course.course_name, course.course_code ?? null, this.useClaude()),
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `FD_${this.safeFilename(d.course_name)}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      this.status.set('done');
    } catch (err: unknown) {
      this.errorMessage.set(this.errorDetail(err));
      this.status.set('error');
    }
  }

  /** Unicode-aware filename: keeps Romanian diacritics, drops only OS-illegal chars. */
  private safeFilename(name: string): string {
    return (name || 'fisa')
      .replace(/[\\/:*?"<>|]+/g, '_') // Windows-illegal chars
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 80) || 'fisa';
  }

  reset(): void {
    this.planFile.set(null);
    this.planDoc.set(null);
    this.courses.set([]);
    this.selectedCourse.set(null);
    this.draft.set(null);
    this.status.set('idle');
    this.errorMessage.set('');
    this.programName.set(null);
    this.filterText.set('');
    this.filterYear.set(null);
  }

  private errorDetail(err: unknown): string {
    const e = err as { error?: { detail?: unknown }; status?: number; statusText?: string; message?: string; name?: string };
    const backendDetail = e?.error?.detail;
    if (backendDetail) return String(backendDetail);
    if (e?.name === 'TimeoutError') {
      return 'Timeout: serverul nu a răspuns la timp.';
    }
    if (e?.status) return `HTTP ${e.status}: ${e?.statusText || e?.message || 'eroare'}`;
    return e?.message || 'Eroare necunoscută.';
  }
}
