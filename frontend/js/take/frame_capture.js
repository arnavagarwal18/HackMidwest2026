// Grabs one JPEG frame of a playing <video>, small enough for the 2 MB camera-check limit.
const FRAME_WIDTH = 640;
const JPEG_QUALITY = 0.8;

// Resolves a JPEG Blob, or null while the video has no picture yet.
export function captureFrame(video) {
  if (!video.videoWidth || !video.videoHeight) return Promise.resolve(null);
  const canvas = document.createElement('canvas');
  canvas.width = FRAME_WIDTH;
  canvas.height = Math.round((FRAME_WIDTH * video.videoHeight) / video.videoWidth);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The camera frame could not be turned into a JPEG.'))),
      'image/jpeg', JPEG_QUALITY);
  });
}
