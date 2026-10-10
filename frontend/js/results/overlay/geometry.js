// Mapping normalised track coordinates (0-1 of the video picture) onto the canvas that sits over the <video>.

// Where the picture is inside the element's box, as the browser draws it for CSS object-fit.
// box and intrinsic are { width, height }; returns { x, y, width, height } in box pixels.
export function contentRect(box, intrinsic, fit = 'contain') {
  const whole = { x: 0, y: 0, width: box.width, height: box.height };
  if (fit === 'fill' || !(intrinsic.width > 0 && intrinsic.height > 0)) return whole;
  const containScale = Math.min(box.width / intrinsic.width, box.height / intrinsic.height);
  const scale = {
    cover: Math.max(box.width / intrinsic.width, box.height / intrinsic.height),
    none: 1,
    'scale-down': Math.min(1, containScale),
  }[fit] ?? containScale;
  const width = intrinsic.width * scale;
  const height = intrinsic.height * scale;
  return { x: (box.width - width) / 2, y: (box.height - height) / 2, width, height };
}

export function toCanvas([x, y], rect) {
  return [rect.x + x * rect.width, rect.y + y * rect.height];
}
