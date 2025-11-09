const driveForm = document.getElementById('drive-form');
if (driveForm) {
  driveForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const output = document.getElementById('drive-files');
    if (!output) return;
    output.classList.remove('hidden');
    output.innerHTML = '<p>Loading files…</p>';

    const formData = new FormData(driveForm);
    formData.append('csrf_token', driveForm.dataset.csrf ?? '');

    try {
      const response = await fetch('/google-drive/list', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const payload = await response.json();
        output.innerHTML = `<p class="error">${payload.detail ?? 'Unable to list files.'}</p>`;
        return;
      }
      const data = await response.json();
      const files = data.files ?? [];
      if (!files.length) {
        output.innerHTML = '<p>No files available in this folder.</p>';
        return;
      }
      output.innerHTML = '';
      files.forEach((file) => {
        const card = document.createElement('form');
        card.className = 'drive-file';
        card.innerHTML = `
          <div>
            <strong>${file.name}</strong>
            <span>${file.mimeType}</span>
          </div>
          <button type="submit" class="primary">Import</button>
        `;
        const hiddenFields = [
          ['file_id', file.id],
          ['file_name', file.name],
          ['csrf_token', driveForm.dataset.csrf ?? ''],
        ];
        hiddenFields.forEach(([name, value]) => {
          const input = document.createElement('input');
          input.type = 'hidden';
          input.name = name;
          input.value = value;
          card.appendChild(input);
        });
        card.addEventListener('submit', async (evt) => {
          evt.preventDefault();
          const cardData = new FormData(card);
          const result = await fetch('/google-drive/ingest', {
            method: 'POST',
            body: cardData,
          });
          if (result.ok) {
            location.reload();
          } else {
            const payload = await result.json();
            alert(payload.detail ?? 'Failed to ingest file.');
          }
        });
        output.appendChild(card);
      });
    } catch (error) {
      output.innerHTML = `<p class="error">${error}</p>`;
    }
  });
}
