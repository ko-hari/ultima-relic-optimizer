const state = { board: null, recommendations: [], selected: 0, image: null };
const ITEMS = ["Boom", "Special Boom", "Lazer X", "Lazer Y"];
const ITEM_META = {
  "Boom": ["B", "3×3 폭발"],
  "Special Boom": ["S", "3×3 · 보상 2배"],
  "Lazer X": ["X", "가로 한 줄"],
  "Lazer Y": ["Y", "세로 한 줄"],
};
const $ = (id) => document.getElementById(id);

function inventoryMarkup() {
  $("inventoryGrid").innerHTML = ITEMS.map((item) => `<div class="inventory-item"><span class="item-symbol">${ITEM_META[item][0]}</span><span class="item-copy"><strong>${item}</strong><small>${ITEM_META[item][1]}</small></span><output class="inventory-count" data-item="${item}" aria-label="${item} 수량">×0</output></div>`).join("");
}

function setError(message = "") { const box = $("errorBox"); box.textContent = message; box.hidden = !message; }

function boardFromResponse(data) {
  state.board = data;
  $("boardSize").textContent = `${data.width} × ${data.height}`;
  $("boardSource").textContent = data.source === "upload" ? "사용자 스크린샷" : "Sample_Board.png";
  $("foundRewards").textContent = data.found_rewards;
  $("remainingRewards").textContent = `남은 보상 ${data.remaining_rewards}`;
  $("unknownCells").textContent = data.unknown_count;
  $("detectorName").textContent = `분석기 ${data.detector}`;
  ITEMS.forEach((item) => { const output = document.querySelector(`[data-item="${item}"]`); if (output) output.textContent = `×${Number(data.inventory?.[item] || 0)}`; });
  $("boardLoading").style.display = "none";
  state.image = new Image();
  state.image.onload = () => drawBoard();
  state.image.src = data.image_data_url;
  drawBoard();
}

async function analyze(imageFile = null) {
  setError(""); $("boardLoading").style.display = "block";
  const form = new FormData();
  if (imageFile) form.append("image", imageFile);
  try { const response = await fetch("/api/analyze", {method: "POST", body: form}); if (!response.ok) throw new Error("이미지 분석 요청이 실패했습니다."); boardFromResponse(await response.json()); await recommend(); }
  catch (error) { setError(error.message); $("boardLoading").style.display = "none"; }
}

function imageFileFromClipboard(clipboardData) {
  const item = [...(clipboardData?.items || [])].find((entry) => entry.kind === "file" && entry.type.startsWith("image/"));
  const blob = item?.getAsFile() || [...(clipboardData?.files || [])].find((entry) => entry.type.startsWith("image/"));
  if (!blob) return null;
  const extension = blob.type.split("/")[1]?.replace("jpeg", "jpg") || "png";
  return new File([blob], `clipboard-${Date.now()}.${extension}`, {type: blob.type || "image/png"});
}

function analyzeUserImage(file, label) {
  $("fileLabel").textContent = label;
  $("pasteHint").textContent = label === "클립보드 캡처 이미지" ? "붙여넣은 이미지를 분석하고 있습니다…" : "선택한 이미지를 분석하고 있습니다…";
  $("uploadZone").classList.add("receiving");
  analyze(file).finally(() => {
    $("uploadZone").classList.remove("receiving");
    $("pasteHint").textContent = "클립보드 이미지는 이 페이지 어디에서나 붙여넣을 수 있습니다.";
  });
}

function getInventory() { return Object.fromEntries([...document.querySelectorAll("[data-item]")].map((output) => [output.dataset.item, Number(output.textContent.replace("×", "")) || 0])); }

async function recommend() {
  if (!state.board) return;
  setError(""); $("recommendButton").disabled = true; $("recommendButton").textContent = "계산 중…";
  const payload = {board: state.board, inventory: getInventory(), objective: $("objective").value, mode: $("mode").value, iterations: Number($("iterations").value) || 1000};
  try { const response = await fetch("/api/recommend", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}); const data = await response.json(); if (!response.ok) throw new Error(data.error || "추천 계산이 실패했습니다."); state.recommendations = data.recommendations; state.selected = 0; renderRecommendations(); drawBoard(); }
  catch (error) { setError(error.message); }
  finally { $("recommendButton").disabled = false; $("recommendButton").innerHTML = "추천 계산 <span>↗</span>"; }
}

function percent(value) { return `${(Number(value) * 100).toFixed(1)}%`; }
function targetText(rec) { return rec.target ? `(${rec.target[0] + 1}, ${rec.target[1] + 1})` : "자동"; }

function renderRecommendations() {
  const list = $("recommendationList"); $("recommendCount").textContent = state.recommendations.length;
  if (!state.recommendations.length) { list.innerHTML = `<div class="empty-state"><span>∅</span><strong>사용 가능한 아이템이 없습니다</strong><small>아이템 수량을 하나 이상 입력하세요.</small></div>`; $("topScore").textContent = "—"; return; }
  list.innerHTML = state.recommendations.map((rec, index) => `<div class="recommendation ${index === state.selected ? "selected" : ""}" data-index="${index}"><div class="rec-top"><span class="rank">0${index + 1}</span><span class="rec-item">${rec.item}</span><span class="rec-target">${targetText(rec)}</span></div><div class="rec-meta"><span>탐색 <b>${Number(rec.expected_newly_explored_cells).toFixed(1)}</b></span><span>보상 <b>${Number(rec.expected_rewards).toFixed(2)}</b></span><span class="rec-score">점수 <b class="rec-score">${Number(rec.score).toFixed(3)}</b></span></div></div>`).join("");
  list.querySelectorAll(".recommendation").forEach((node) => node.addEventListener("click", () => { state.selected = Number(node.dataset.index); renderRecommendations(); drawBoard(); }));
  const top = state.recommendations[state.selected]; $("topScore").textContent = Number(top.score).toFixed(3); $("topItem").textContent = `${top.item} · ${targetText(top)}`; $("reasonTitle").textContent = `${top.item} · 표적 ${targetText(top)}`; $("reasonText").textContent = top.reason; $("atLeastOne").textContent = percent(top.probability_of_at_least_one_reward); $("completion").textContent = percent(top.probability_of_completion); $("boardMessage").textContent = top.target ? `빨간 박스: ${top.item} 추천 표적 ${targetText(top)} · 옅은 빨강: 실제 효과 범위` : `빨간 박스: ${top.item} 자동 적용 범위`;
}

function cellRect(x, y, board, scale = 1) { const r = board.region; return [r.left + x * (r.right - r.left) / board.width, r.top + y * (r.bottom - r.top) / board.height, (r.right - r.left) / board.width, (r.bottom - r.top) / board.height].map((v) => v * scale); }
function effectCells(rec, board) {
  if (!rec || !rec.target) return [];
  const [x, y] = rec.target, output = [];
  if (rec.item === "Boom" || rec.item === "Special Boom" || rec.item === "Gunpowder Barrel") for (let yy = y - 1; yy <= y + 1; yy++) for (let xx = x - 1; xx <= x + 1; xx++) if (xx >= 0 && yy >= 0 && xx < board.width && yy < board.height) output.push([xx, yy]);
  if (rec.item === "Lazer X") for (let xx = 0; xx < board.width; xx++) output.push([xx, y]);
  if (rec.item === "Lazer Y") for (let yy = 0; yy < board.height; yy++) output.push([x, yy]);
  return output.filter(([xx, yy]) => board.states[yy * board.width + xx] === "unknown");
}

function drawBoard() {
  const board = state.board, canvas = $("boardCanvas"), ctx = canvas.getContext("2d");
  if (!board) return;
  const image = state.image;
  canvas.width = image?.naturalWidth || 390; canvas.height = image?.naturalHeight || 474; ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (image?.complete && image.naturalWidth) ctx.drawImage(image, 0, 0); else { ctx.fillStyle = "#76563f"; ctx.fillRect(0, 0, canvas.width, canvas.height); }
  // Canvas and detector coordinates both use the uploaded image's natural
  // pixel space. Applying a second width ratio here shifted overlays on
  // screenshots whose width differed from the 390px sample.
  const scale = 1, r = board.region, cellW = (r.right - r.left) / board.width, cellH = (r.bottom - r.top) / board.height, left = r.left, top = r.top;
  ctx.lineWidth = Math.max(1, scale); ctx.strokeStyle = "rgba(238,220,172,.16)";
  for (let x = 0; x <= board.width; x++) { ctx.beginPath(); ctx.moveTo(left + x * cellW, top); ctx.lineTo(left + x * cellW, top + board.height * cellH); ctx.stroke(); }
  for (let y = 0; y <= board.height; y++) { ctx.beginPath(); ctx.moveTo(left, top + y * cellH); ctx.lineTo(left + board.width * cellW, top + y * cellH); ctx.stroke(); }
  const rec = state.recommendations[state.selected];
  if (!rec) return;
  ctx.fillStyle = "rgba(255,70,70,.19)";
  ctx.strokeStyle = "rgba(255,88,82,.78)";
  ctx.lineWidth = Math.max(1, scale);
  effectCells(rec, board).forEach(([x, y]) => { const [cx, cy, w, h] = cellRect(x, y, board, scale); ctx.fillRect(cx + 1, cy + 1, w - 2, h - 2); ctx.strokeRect(cx + 1.5, cy + 1.5, w - 3, h - 3); });
  ctx.save(); ctx.strokeStyle = "#ff3f3f"; ctx.lineWidth = Math.max(3, scale * 3); ctx.shadowColor = "rgba(255,45,45,.9)"; ctx.shadowBlur = 8 * scale;
  if (rec.target) {
    const [x, y, w, h] = cellRect(rec.target[0], rec.target[1], board, scale); ctx.strokeRect(x + 1.5, y + 1.5, w - 3, h - 3); ctx.restore();
    const label = `#${state.selected + 1}  ${rec.item}  ${targetText(rec)}`, fontSize = Math.max(9, 10 * scale); ctx.font = `bold ${fontSize}px DM Mono`; const labelWidth = ctx.measureText(label).width + 12 * scale, labelHeight = 18 * scale; const labelX = Math.min(x, canvas.width - labelWidth - 3); const labelY = Math.max(3, y - labelHeight - 3); ctx.fillStyle = "#ed3434"; ctx.fillRect(labelX, labelY, labelWidth, labelHeight); ctx.fillStyle = "#fff"; ctx.fillText(label, labelX + 6 * scale, labelY + 12.5 * scale);
  } else {
    ctx.strokeRect(left, top, board.width * cellW, board.height * cellH); ctx.restore(); ctx.fillStyle = "#ed3434"; ctx.fillRect(left + 4, top + 4, 106 * scale, 19 * scale); ctx.fillStyle = "#fff"; ctx.font = `bold ${Math.max(9, 10 * scale)}px DM Mono`; ctx.fillText(`#${state.selected + 1}  AUTO TARGET`, left + 10 * scale, top + 17 * scale);
  }
}

$("imageInput").addEventListener("change", (event) => { const file = event.target.files[0]; if (file) analyzeUserImage(file, file.name); });
document.addEventListener("paste", (event) => {
  const file = imageFileFromClipboard(event.clipboardData);
  if (!file) return;
  event.preventDefault();
  analyzeUserImage(file, "클립보드 캡처 이미지");
});
$("sampleButton").addEventListener("click", () => { $("fileLabel").textContent = "샘플 보드 사용 중"; $("imageInput").value = ""; analyze(); });
$("recommendButton").addEventListener("click", recommend);
$("mode").addEventListener("change", () => $("iterationWrap").classList.toggle("visible", $("mode").value === "monte_carlo"));
window.addEventListener("resize", drawBoard);
inventoryMarkup(); analyze();
