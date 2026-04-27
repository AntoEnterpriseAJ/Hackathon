/**
 * DiffViewerComponent - displays diffs in GitHub Desktop–style unified format.
 */

import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SectionDiff, LineDiff } from '../../models/diff.models';

@Component({
  selector: 'app-diff-viewer',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './diff-viewer.component.html',
  styleUrls: ['./diff-viewer.component.scss']
})
export class DiffViewerComponent {
  sectionDiffs = input<SectionDiff[]>([]);
  showEqualSections = false;
  showEqualLines = false;

  getVisibleSections(): SectionDiff[] {
    if (this.showEqualSections) {
      return this.sectionDiffs();
    }
    return this.sectionDiffs().filter((section) => section.status !== 'equal');
  }

  getVisibleLines(section: SectionDiff): LineDiff[] {
    const filteredByType = this.showEqualLines
      ? section.lines
      : section.lines.filter((line) => line.type !== 'equal');

    const withoutHeadingDupes = filteredByType.filter((line) => !this.isHeadingDuplicate(section.name, line));

    // Remove only adjacent duplicates to reduce noise while preserving structure.
    const result: LineDiff[] = [];
    let previousKey = '';

    for (const line of withoutHeadingDupes) {
      const key = `${line.type}:${this.normalizeForCompare(this.getPrimaryText(line))}`;
      if (key === previousKey) {
        continue;
      }
      result.push(line);
      previousKey = key;
    }

    return result;
  }

  getHiddenEqualCount(section: SectionDiff): number {
    if (this.showEqualLines) {
      return 0;
    }
    return section.lines.filter((line) => line.type === 'equal').length;
  }

  toggleEqualSections(): void {
    this.showEqualSections = !this.showEqualSections;
  }

  toggleEqualLines(): void {
    this.showEqualLines = !this.showEqualLines;
  }

  private getPrimaryText(line: LineDiff): string {
    if (line.type === 'remove') {
      return line.old_text ?? '';
    }
    return line.new_text ?? line.old_text ?? '';
  }

  private isHeadingDuplicate(sectionName: string, line: LineDiff): boolean {
    const text = this.getPrimaryText(line);
    if (!text) {
      return false;
    }

    const sectionNorm = this.normalizeForCompare(sectionName);
    const lineNorm = this.normalizeForCompare(text);

    if (!sectionNorm || !lineNorm) {
      return false;
    }

    if (sectionNorm === lineNorm) {
      return true;
    }

    return sectionNorm.includes(lineNorm) || lineNorm.includes(sectionNorm);
  }

  private normalizeForCompare(value: string): string {
    return value
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/^\s*\d+(?:\.\d+)*[\)\.]?\s*/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  /** CSS class for each diff row */
  getRowClass(line: LineDiff): string {
    switch (line.type) {
      case 'add': return 'row-add';
      case 'remove': return 'row-remove';
      case 'replace': return 'row-replace';
      default: return 'row-equal';
    }
  }

  trackBySection(index: number): number { return index; }
  trackByLine(index: number): number { return index; }
}
