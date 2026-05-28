const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const params = new URLSearchParams(window.location.search);
const jobId = parseInt(params.get("job") || "0", 10);

const size = document.getElementById("size");
const zoomOut = document.getElementById("zoomOut");
const zoomIn = document.getElementById("zoomIn");
const sizeVal = document.getElementById("sizeVal");
const outline = document.getElementById("outline");
const glow = document.getElementById("glow");
const outlineVal = document.getElementById("outlineVal");
const glowVal = document.getElementById("glowVal");
const preview = document.getElementById("preview");
const guideBtn = document.getElementById("guide");
const guideModal = document.getElementById("guideModal");
const guideBackdrop = document.getElementById("guideBackdrop");
const guideClose = document.getElementById("guideClose");
const guideImg = document.getElementById("guideImg");

function updatePreview() {
  const s = parseInt(size.value, 10) || 100;
  const w = outline.value;
  const g = glow.value;
  sizeVal.textContent = s;
  outlineVal.textContent = w;
  glowVal.textContent = g;
  preview.style.transform = `scale(${Math.max(50, Math.min(150, s)) / 100})`;
  preview.style.borderWidth = `${Math.max(1, w)}px`;
  preview.style.boxShadow = `0 0 ${g / 4}px rgba(0, 255, 255, ${g / 100})`;
}

function stepSize(delta) {
  const current = parseInt(size.value, 10) || 100;
  const next = Math.max(50, Math.min(150, current + delta));
  size.value = String(next);
  updatePreview();
}

size.addEventListener("input", updatePreview);
zoomOut.addEventListener("click", () => stepSize(-10));
zoomIn.addEventListener("click", () => stepSize(10));
outline.addEventListener("input", updatePreview);
glow.addEventListener("input", updatePreview);
updatePreview();

function openGuide() {
  guideImg.src = "/content/guide.png";
  guideModal.classList.add("is-open");
  guideModal.setAttribute("aria-hidden", "false");
}

function closeGuide() {
  guideModal.classList.remove("is-open");
  guideModal.setAttribute("aria-hidden", "true");
}

guideBtn.addEventListener("click", openGuide);
guideBackdrop.addEventListener("click", closeGuide);
guideClose.addEventListener("click", closeGuide);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeGuide();
});

document.getElementById("apply").addEventListener("click", () => {
  if (!jobId) {
    tg.showAlert("Missing job id. Open from the bot preview button.");
    return;
  }
  const data = JSON.stringify({
    job_id: jobId,
    subject_scale: parseInt(size.value, 10) || 100,
    outline_width: parseInt(outline.value, 10),
    glow_strength: parseInt(glow.value, 10) || 55,
  });
  tg.sendData(data);
  tg.close();
});

