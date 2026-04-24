/**
 * DiffUploadComponent - handles file upload for two PDFs.
 */

import { Component, output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-diff-upload',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './diff-upload.component.html',
  styleUrls: ['./diff-upload.component.scss']
})
export class DiffUploadComponent {
  fileOld: File | null = null;
  fileNew: File | null = null;
  
  filesSelected = output<{ fileOld: File; fileNew: File }>();

  onFileOldSelected(event: any) {
    const file = event.target.files?.[0];
    if (file) {
      this.fileOld = file;
    }
  }

  onFileNewSelected(event: any) {
    const file = event.target.files?.[0];
    if (file) {
      this.fileNew = file;
    }
  }

  onCompare() {
    if (this.fileOld && this.fileNew) {
      this.filesSelected.emit({ fileOld: this.fileOld, fileNew: this.fileNew });
    }
  }

  isReady(): boolean {
    return this.fileOld !== null && this.fileNew !== null;
  }
}
