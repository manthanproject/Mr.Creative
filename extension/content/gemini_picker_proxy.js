// Installed at document_start in MAIN world — before Gemini captures showOpenFilePicker
(function() {
  const origPicker = window.showOpenFilePicker;
  window.__mcPickerData = null;

  window.showOpenFilePicker = async function(...args) {
    if (window.__mcPickerData) {
      const data = window.__mcPickerData;
      window.__mcPickerData = null;
      console.log('[Mr.Creative] showOpenFilePicker INTERCEPTED! file:', data.fileName);
      const binary = atob(data.base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const file = new File([bytes], data.fileName, { type: data.mimeType });
      console.log('[Mr.Creative] Returning file:', file.name, file.size, 'bytes');
      return [{ kind: 'file', name: data.fileName, getFile: async () => file }];
    }
    return origPicker.apply(this, args);
  };
  console.log('[Mr.Creative] showOpenFilePicker proxy ready (document_start)');
})();
