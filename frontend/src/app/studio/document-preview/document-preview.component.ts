import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { CaseStore } from '../case.store';

@Component({
  selector: 'app-document-preview',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './document-preview.component.html',
  styleUrl: './document-preview.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentPreviewComponent {
  private readonly store = inject(CaseStore);
  private readonly sanitizer = inject(DomSanitizer);

  /** Document id passed in by the parent. */
  readonly documentId = input.required<string>();

  /** Cached blob URLs so we don't recreate them on every change detection. */
  private readonly _blobCache = new Map<string, string>();

  protected readonly doc = computed(() =>
    this.store.documents().find((d) => d.id === this.documentId()) ?? null,
  );

  protected readonly isPdf = computed(() => {
    const d = this.doc();
    if (!d) return false;
    return (
      d.file.type === 'application/pdf' ||
      /\.pdf$/i.test(d.name)
    );
  });

  protected readonly isDocx = computed(() => {
    const d = this.doc();
    if (!d) return false;
    return (
      d.file.type ===
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
      /\.docx$/i.test(d.name)
    );
  });

  protected readonly previewUrl = computed<SafeResourceUrl | null>(() => {
    const d = this.doc();
    if (!d || !this.isPdf()) return null;
    let url = this._blobCache.get(d.id);
    if (!url) {
      url = URL.createObjectURL(d.file);
      this._blobCache.set(d.id, url);
    }
    return this.sanitizer.bypassSecurityTrustResourceUrl(url);
  });

  protected formatBytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }

  protected download(): void {
    const d = this.doc();
    if (!d) return;
    const url = URL.createObjectURL(d.file);
    const a = document.createElement('a');
    a.href = url;
    a.download = d.name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}
