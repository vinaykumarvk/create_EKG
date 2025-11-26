// Password toggle functionality
function initPasswordToggles() {
  document.querySelectorAll('.password-toggle').forEach(toggle => {
    toggle.addEventListener('click', function() {
      const wrapper = this.closest('.password-input-wrapper');
      const input = wrapper ? wrapper.querySelector('input[type="password"], input[type="text"]') : null;
      if (input) {
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        const eyeIcon = this.querySelector('.eye-icon');
        if (eyeIcon) {
          eyeIcon.textContent = isPassword ? '🙈' : '👁️';
        }
      }
    });
  });
}

// Initialize password toggles on page load
document.addEventListener('DOMContentLoaded', initPasswordToggles);

// Vector store management
document.addEventListener('DOMContentLoaded', function() {
  const vectorStoreSelect = document.getElementById('vector-store-select');
  const selectedVectorStoreId = document.getElementById('selected-vector-store-id');
  const refreshStoresBtn = document.getElementById('refresh-stores');
  const createStoreBtn = document.getElementById('create-store');
  const newStoreNameInput = document.getElementById('new-store-name');
  const storeStatus = document.getElementById('store-status');
  const newStoreSection = document.getElementById('new-store-section');
  const uploadForm = document.getElementById('upload-form');
  const uploadButton = document.getElementById('upload-button');

  if (!vectorStoreSelect || !selectedVectorStoreId) {
    return; // Vector store section not present
  }

  // Files in vector store functionality
  const filesSection = document.getElementById('vector-store-files-section');
  const toggleFilesBtn = document.getElementById('toggle-files');
  const filesListContainer = document.getElementById('files-list-container');
  const filesList = document.getElementById('files-list');
  const filesLoading = document.getElementById('files-loading');
  const deleteFilesBtn = document.getElementById('delete-files');
  const filesActionStatus = document.getElementById('files-action-status');
  let filesExpanded = false;
  let currentVectorStoreId = null;
  const selectedFileIds = new Set();

  function showFilesSection() {
    if (filesSection) filesSection.style.display = 'block';
  }

  function hideFilesSection() {
    if (filesSection) filesSection.style.display = 'none';
  }

  function setFilesActionStatus(message, tone = 'muted') {
    if (!filesActionStatus) return;
    filesActionStatus.textContent = message || '';
    let color = 'var(--muted)';
    if (tone === 'success') color = 'var(--success)';
    if (tone === 'error') color = 'var(--danger)';
    if (tone === 'warning') color = 'var(--primary)';
    filesActionStatus.style.color = color;
  }

  function updateDeleteButtonState() {
    if (!deleteFilesBtn) return;
    const count = selectedFileIds.size;
    deleteFilesBtn.disabled = count === 0;
    deleteFilesBtn.textContent = count ? `Delete Selected (${count})` : 'Delete Selected';
  }

  function resetFilesUI(vectorStoreId) {
    currentVectorStoreId = vectorStoreId;
    selectedFileIds.clear();
    updateDeleteButtonState();
    setFilesActionStatus('');
    filesExpanded = false;
    if (filesListContainer) filesListContainer.style.display = 'none';
    if (toggleFilesBtn) toggleFilesBtn.textContent = 'Show Files';
  }

  function loadFilesForStore(vectorStoreId) {
    if (!filesList || !filesLoading) return;
    const wasExpanded = filesExpanded;
    resetFilesUI(vectorStoreId);
    if (wasExpanded) {
      filesExpanded = true;
      if (filesListContainer) filesListContainer.style.display = 'block';
      if (toggleFilesBtn) toggleFilesBtn.textContent = 'Hide Files';
    }

    filesList.innerHTML = '';
    filesLoading.style.display = 'block';
    
    fetch(`/api/vector-stores/${vectorStoreId}/files`)
      .then(response => response.json())
      .then(data => {
        filesLoading.style.display = 'none';
        if (data.error) {
          filesList.innerHTML = `<li style="color: var(--danger); padding: 0.5rem;">Error: ${data.error}</li>`;
          return;
        }
        
        const files = data.files || [];
        if (files.length === 0) {
          filesList.innerHTML = '<li style="color: var(--muted); padding: 0.5rem;">No files in this vector store.</li>';
          return;
        }
        
        files.forEach(file => {
          const li = document.createElement('li');
          li.style.padding = '0.5rem';
          li.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
          li.style.display = 'flex';
          li.style.alignItems = 'center';
          li.style.gap = '1rem';

          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = file.id;
          checkbox.style.marginRight = '0.75rem';
          checkbox.addEventListener('change', function() {
            if (this.checked) {
              selectedFileIds.add(file.id);
            } else {
              selectedFileIds.delete(file.id);
            }
            updateDeleteButtonState();
          });

          const infoWrapper = document.createElement('div');
          infoWrapper.style.display = 'flex';
          infoWrapper.style.alignItems = 'center';
          infoWrapper.style.flex = '1';
          infoWrapper.appendChild(checkbox);

          const fileName = document.createElement('span');
          fileName.textContent = file.filename;
          fileName.style.flex = '1';
          infoWrapper.appendChild(fileName);

          const fileSize = document.createElement('span');
          const sizeKB = (file.bytes / 1024).toFixed(1);
          fileSize.textContent = `${sizeKB} KB`;
          fileSize.style.color = 'var(--muted)';
          fileSize.style.fontSize = '0.85rem';

          li.appendChild(infoWrapper);
          li.appendChild(fileSize);
          filesList.appendChild(li);
        });
      })
      .catch(error => {
        filesLoading.style.display = 'none';
        filesList.innerHTML = `<li style="color: var(--danger); padding: 0.5rem;">Error loading files: ${error.message}</li>`;
        setFilesActionStatus('Failed to load files.', 'error');
      });
  }

  if (toggleFilesBtn && filesListContainer) {
    toggleFilesBtn.addEventListener('click', function() {
      filesExpanded = !filesExpanded;
      filesListContainer.style.display = filesExpanded ? 'block' : 'none';
      toggleFilesBtn.textContent = filesExpanded ? 'Hide Files' : 'Show Files';
    });
  }

  // Sync vector store selection to hidden field
  function syncVectorStoreId() {
    const val = vectorStoreSelect.value;
    if (val === '__new__') {
      selectedVectorStoreId.value = '';
      if (newStoreSection) newStoreSection.style.display = 'block';
      hideFilesSection();
      setFilesActionStatus('');
    } else {
      selectedVectorStoreId.value = val || '';
      if (newStoreSection) newStoreSection.style.display = 'none';
      if (val) {
        showFilesSection();
        loadFilesForStore(val);
      } else {
        hideFilesSection();
      }
    }
    updateDeleteButtonState();
  }

  vectorStoreSelect.addEventListener('change', syncVectorStoreId);
  syncVectorStoreId(); // Initialize

  if (deleteFilesBtn) {
    deleteFilesBtn.addEventListener('click', async function() {
      if (!currentVectorStoreId) {
        alert('Please select a vector store first.');
        return;
      }

      if (selectedFileIds.size === 0) {
        alert('Please select at least one file to delete.');
        return;
      }

      if (!confirm(`Are you sure you want to delete ${selectedFileIds.size} file(s)? This cannot be undone.`)) {
        return;
      }

      const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
      if (!csrfToken) {
        alert('CSRF token not found');
        return;
      }

      deleteFilesBtn.disabled = true;
      deleteFilesBtn.textContent = 'Deleting...';
      setFilesActionStatus('Deleting selected files...', 'warning');

      try {
        const formData = new FormData();
        formData.append('csrf_token', csrfToken);
        selectedFileIds.forEach(id => formData.append('file_ids', id));

        const response = await fetch(`/api/vector-stores/${currentVectorStoreId}/files/delete`, {
          method: 'POST',
          body: formData
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || 'Failed to delete files');
        }

        const deletedCount = (data.deleted || []).length;
        const failedCount = (data.failed || []).length;

        if (deletedCount && !failedCount) {
          setFilesActionStatus(`Deleted ${deletedCount} file(s) successfully.`, 'success');
        } else if (deletedCount && failedCount) {
          setFilesActionStatus(`Deleted ${deletedCount} file(s). ${failedCount} failed.`, 'warning');
        } else {
          setFilesActionStatus('No files were deleted.', 'warning');
        }

        // Reload files list
        loadFilesForStore(currentVectorStoreId);
      } catch (error) {
        console.error(error);
        setFilesActionStatus(`Error deleting files: ${error.message}`, 'error');
      } finally {
        deleteFilesBtn.disabled = true;
        deleteFilesBtn.textContent = 'Delete Selected';
        selectedFileIds.clear();
        updateDeleteButtonState();
      }
    });
  }

  // Refresh vector stores list
  if (refreshStoresBtn) {
    refreshStoresBtn.addEventListener('click', async function() {
      try {
        const response = await fetch('/api/vector-stores');
        if (!response.ok) throw new Error('Failed to fetch stores');
        const stores = await response.json();
        
        // Rebuild dropdown
        const currentValue = vectorStoreSelect.value;
        vectorStoreSelect.innerHTML = '';
        
        // Add default option if exists
        const defaultOption = stores.find(s => s.id === currentValue);
        if (defaultOption) {
          const opt = document.createElement('option');
          opt.value = defaultOption.id;
          opt.textContent = `${defaultOption.name} (${defaultOption.file_count} files) - Default`;
          vectorStoreSelect.appendChild(opt);
        }
        
        // Add other stores
        stores.forEach(store => {
          if (store.id !== currentValue) {
            const opt = document.createElement('option');
            opt.value = store.id;
            opt.textContent = `${store.name} (${store.file_count} files)`;
            vectorStoreSelect.appendChild(opt);
          }
        });
        
        // Add "Create New" option
        const newOpt = document.createElement('option');
        newOpt.value = '__new__';
        newOpt.textContent = '➕ Create New Vector Store...';
        vectorStoreSelect.appendChild(newOpt);
        
        // Restore selection
        vectorStoreSelect.value = currentValue;
        syncVectorStoreId();
        
        if (storeStatus) {
          storeStatus.textContent = 'List refreshed';
          storeStatus.classList.remove('hidden');
          setTimeout(() => storeStatus.classList.add('hidden'), 2000);
        }
      } catch (error) {
        alert('Error refreshing stores: ' + error.message);
      }
    });
  }

  // Create new vector store
  if (createStoreBtn && newStoreNameInput) {
    createStoreBtn.addEventListener('click', async function() {
      const name = newStoreNameInput.value.trim();
      if (!name) {
        alert('Please enter a vector store name');
        return;
      }

      const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
      if (!csrfToken) {
        alert('CSRF token not found');
        return;
      }

      try {
        createStoreBtn.disabled = true;
        createStoreBtn.textContent = 'Creating...';
        if (storeStatus) {
          storeStatus.textContent = 'Creating vector store...';
          storeStatus.classList.remove('hidden');
        }

        const formData = new FormData();
        formData.append('name', name);
        formData.append('csrf_token', csrfToken);

        const response = await fetch('/api/vector-stores/create', {
          method: 'POST',
          body: formData
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || 'Failed to create vector store');
        }

        const newStore = await response.json();
        
        // Add new store to dropdown and select it
        const opt = document.createElement('option');
        opt.value = newStore.id;
        opt.textContent = `${newStore.name} (0 files)`;
        vectorStoreSelect.insertBefore(opt, vectorStoreSelect.lastElementChild);
        vectorStoreSelect.value = newStore.id;
        syncVectorStoreId();

        if (storeStatus) {
          storeStatus.textContent = 'Vector store created successfully!';
          storeStatus.classList.remove('hidden');
        }
        newStoreNameInput.value = '';

        // Reload page after 2 seconds to show flash message
        setTimeout(() => window.location.reload(), 2000);
      } catch (error) {
        alert('Error creating vector store: ' + error.message);
        if (storeStatus) {
          storeStatus.textContent = 'Error: ' + error.message;
          storeStatus.classList.remove('hidden');
        }
      } finally {
        createStoreBtn.disabled = false;
        createStoreBtn.textContent = 'Create';
      }
    });
  }

  // File upload form handling
  const fileInput = document.getElementById('file-input');
  const selectedFilesDiv = document.getElementById('selected-files');
  const uploadProgress = document.getElementById('upload-progress');
  const uploadStatusText = document.getElementById('upload-status-text');
  const uploadProgressPercent = document.getElementById('upload-progress-percent');
  const uploadProgressBar = document.getElementById('upload-progress-bar');
  const uploadFileList = document.getElementById('upload-file-list');

  // Show selected files
  if (fileInput && selectedFilesDiv) {
    fileInput.addEventListener('change', function() {
      const files = Array.from(this.files);
      if (files.length === 0) {
        selectedFilesDiv.textContent = '';
        return;
      }
      
      if (files.length === 1) {
        selectedFilesDiv.textContent = `Selected: ${files[0].name}`;
      } else {
        selectedFilesDiv.textContent = `Selected ${files.length} files: ${files.map(f => f.name).join(', ')}`;
      }
    });
  }

  if (uploadForm) {
    uploadForm.addEventListener('submit', function(e) {
      // Final sync of vector store ID
      syncVectorStoreId();
      
      // Validate file is selected
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        e.preventDefault();
        alert('Please select at least one file to upload');
        return false;
      }

      // Validate vector store is selected (not "__new__")
      if (vectorStoreSelect.value === '__new__') {
        e.preventDefault();
        alert('Please create a new vector store first, or select an existing one.');
        return false;
      }

      // Show upload progress
      const files = Array.from(fileInput.files);
      if (uploadProgress) {
        uploadProgress.style.display = 'block';
      }
      
      if (uploadButton) {
        uploadButton.disabled = true;
        uploadButton.textContent = 'Uploading...';
      }
      
      // Initialize progress display
      if (uploadStatusText) {
        uploadStatusText.textContent = `Uploading ${files.length} file(s)...`;
      }
      if (uploadProgressBar) {
        uploadProgressBar.style.width = '0%';
      }
      if (uploadProgressPercent) {
        uploadProgressPercent.textContent = '0%';
      }
      
      // Show file list
      if (uploadFileList) {
        uploadFileList.innerHTML = files.map((file, index) => 
          `<div style="padding: 0.25rem 0; display: flex; justify-content: space-between;">
            <span>${file.name}</span>
            <span id="file-status-${index}" style="color: var(--muted);">Waiting...</span>
          </div>`
        ).join('');
      }
      
      // Simulate progress (since we can't track actual upload progress with form submission)
      let progress = 0;
      const progressInterval = setInterval(() => {
        progress += 5;
        if (progress > 90) progress = 90; // Don't go to 100% until upload completes
        if (uploadProgressBar) {
          uploadProgressBar.style.width = progress + '%';
        }
        if (uploadProgressPercent) {
          uploadProgressPercent.textContent = Math.round(progress) + '%';
        }
      }, 200);
      
      // Update file statuses
      files.forEach((file, index) => {
        setTimeout(() => {
          const statusEl = document.getElementById(`file-status-${index}`);
          if (statusEl) {
            statusEl.textContent = 'Uploading...';
            statusEl.style.color = 'var(--primary)';
          }
        }, index * 500);
      });
      
      // Store interval to clear on page reload (upload will redirect)
      window.uploadProgressInterval = progressInterval;
      
      // Let form submit naturally - progress will continue until redirect
    });
  }
});
