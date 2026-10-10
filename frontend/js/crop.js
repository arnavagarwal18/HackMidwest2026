// Crop tool: shows a photo on a canvas, lets the learner drag a rectangle around the music,
// and exports that rectangle as a JPEG no wider than MAX_EXPORT_WIDTH.
export const MAX_EXPORT_WIDTH = 2000;
export const MIN_CROP_PX = 20; // a smaller drag counts as a click and is ignored
const DISPLAY_MAX_WIDTH = 900;
const JPEG_QUALITY = 0.9;

// The rectangle spanned by two points, kept inside a width x height area.
export function rectBetween(a, b, width, height) {
  const clamp = (value, max) => Math.min(Math.max(value, 0), max);
  const x1 = clamp(Math.min(a.x, b.x), width);
  const y1 = clamp(Math.min(a.y, b.y), height);
  const x2 = clamp(Math.max(a.x, b.x), width);
  const y2 = clamp(Math.max(a.y, b.y), height);
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}

// Size of the exported picture: the crop itself, scaled down only when wider than maxWidth.
export function exportSize(cropW, cropH, maxWidth = MAX_EXPORT_WIDTH) {
  const scale = Math.min(1, maxWidth / cropW);
  return { width: Math.max(1, Math.round(cropW * scale)), height: Math.max(1, Math.round(cropH * scale)) };
}

export class Cropper {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.image = null; // ImageBitmap
    this.rect = null; // in canvas pixels; null means the whole photo
    this.dragStart = null;
    canvas.style.touchAction = 'none'; // let a finger drag the rectangle instead of scrolling the page
    canvas.addEventListener('pointerdown', (event) => this.#begin(event));
    canvas.addEventListener('pointermove', (event) => this.#move(event));
    canvas.addEventListener('pointerup', (event) => this.#end(event));
    canvas.addEventListener('pointercancel', () => this.#cancel());
  }

  get hasImage() {
    return this.image !== null;
  }

  setImage(bitmap) {
    this.image?.close?.();
    this.image = bitmap;
    const scale = Math.min(1, DISPLAY_MAX_WIDTH / bitmap.width);
    this.canvas.width = Math.round(bitmap.width * scale);
    this.canvas.height = Math.round(bitmap.height * scale);
    this.rect = null;
    this.#draw();
  }

  clearRect() {
    this.rect = null;
    this.#draw();
  }

  // The crop as a File named score.jpg, type image/jpeg, at most MAX_EXPORT_WIDTH wide.
  async exportJpeg() {
    if (!this.image) throw new Error('Choose a photo first.');
    const factor = this.image.width / this.canvas.width;
    const area = this.rect ?? { x: 0, y: 0, w: this.canvas.width, h: this.canvas.height };
    const source = { x: area.x * factor, y: area.y * factor, w: area.w * factor, h: area.h * factor };
    const { width, height } = exportSize(source.w, source.h);
    const out = document.createElement('canvas');
    out.width = width;
    out.height = height;
    out.getContext('2d').drawImage(this.image, source.x, source.y, source.w, source.h, 0, 0, width, height);
    const blob = await new Promise((resolve) => out.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
    if (!blob) throw new Error("This browser couldn't prepare the photo. Try a smaller photo.");
    return new File([blob], 'score.jpg', { type: 'image/jpeg' });
  }

  #point(event) {
    const box = this.canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - box.left) / box.width) * this.canvas.width,
      y: ((event.clientY - box.top) / box.height) * this.canvas.height,
    };
  }

  #begin(event) {
    if (!this.image) return;
    this.canvas.setPointerCapture(event.pointerId);
    this.dragStart = this.#point(event);
  }

  #move(event) {
    if (!this.dragStart) return;
    this.#draw(rectBetween(this.dragStart, this.#point(event), this.canvas.width, this.canvas.height));
  }

  #end(event) {
    if (!this.dragStart) return;
    const dragged = rectBetween(this.dragStart, this.#point(event), this.canvas.width, this.canvas.height);
    this.dragStart = null;
    if (dragged.w >= MIN_CROP_PX && dragged.h >= MIN_CROP_PX) this.rect = dragged;
    this.#draw();
  }

  #cancel() {
    this.dragStart = null;
    this.#draw();
  }

  #draw(live = null) {
    const { ctx, canvas } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!this.image) return;
    ctx.drawImage(this.image, 0, 0, canvas.width, canvas.height);
    const area = live ?? this.rect;
    if (!area) return;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    ctx.fillRect(0, 0, canvas.width, area.y);
    ctx.fillRect(0, area.y + area.h, canvas.width, canvas.height - area.y - area.h);
    ctx.fillRect(0, area.y, area.x, area.h);
    ctx.fillRect(area.x + area.w, area.y, canvas.width - area.x - area.w, area.h);
    ctx.strokeStyle = '#2b59c3';
    ctx.lineWidth = 2;
    ctx.strokeRect(area.x, area.y, area.w, area.h);
  }
}
