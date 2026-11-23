(() => {
  const fileInput = document.getElementById("id_avatar");
  const avatarPreview = document.getElementById("avatar-preview");

  if (!fileInput || !avatarPreview) return;

  const clearInput = document.getElementById("id_remove_avatar");
  let previewUrl = null;

  function showFallback() {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }

    const fallback = document.createElement("span");
    fallback.textContent = avatarPreview.dataset.fallback || "?";
    avatarPreview.replaceChildren(fallback);
  }

  function showImage(src, alt) {
    const image = document.createElement("img");
    image.src = src;
    image.alt = alt;
    avatarPreview.replaceChildren(image);
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) {
      if (clearInput?.checked) showFallback();
      return;
    }

    if (clearInput) clearInput.checked = false;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    showImage(previewUrl, "Selected profile photo preview");
  });

  clearInput?.addEventListener("change", () => {
    if (clearInput.checked && !fileInput.files?.length) showFallback();
    if (!clearInput.checked && avatarPreview.querySelector("img") === null) {
      const currentImage = avatarPreview.dataset.currentImage;
      if (currentImage) showImage(currentImage, "Profile photo");
    }
  });

  const currentImage = avatarPreview.querySelector("img");
  if (currentImage) avatarPreview.dataset.currentImage = currentImage.src;
})();
