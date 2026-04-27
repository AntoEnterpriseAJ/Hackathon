import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore } from '../case.store';
import { DocumentPreviewComponent } from '../document-preview/document-preview.component';
import { MigrateToolComponent } from '../migrate-tool/migrate-tool.component';
import { SyncToolComponent } from '../sync-tool/sync-tool.component';
import { ValidateToolComponent } from '../validate-tool/validate-tool.component';
import { DraftToolComponent } from '../draft-tool/draft-tool.component';
import { DiffToolComponent } from '../diff-tool/diff-tool.component';

@Component({
  selector: 'app-tabs-area',
  standalone: true,
  imports: [
    CommonModule,
    DocumentPreviewComponent,
    MigrateToolComponent,
    SyncToolComponent,
    ValidateToolComponent,
    DraftToolComponent,
    DiffToolComponent,
  ],
  templateUrl: './tabs-area.component.html',
  styleUrl: './tabs-area.component.scss',
})
export class TabsAreaComponent {
  protected readonly store = inject(CaseStore);

  protected onTabClick(id: string): void {
    this.store.setActiveTab(id);
  }

  protected onTabClose(event: Event, id: string): void {
    event.stopPropagation();
    this.store.closeTab(id);
  }

  protected loadSampleViaPicker(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files) return;
    for (const f of Array.from(input.files)) {
      this.store.addDocument(f);
    }
    input.value = '';
  }

  protected docName(id: string | undefined): string {
    if (!id) return '';
    return this.store.documents().find((d) => d.id === id)?.name ?? '';
  }
}
